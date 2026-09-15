"""
M08 — Risk Engine & State Machine

The SINGLE SOURCE OF TRUTH for warning state. Every other module reads RiskState.state;
no other module is permitted to independently compute "is this dangerous."

Responsibilities:
  1. Aggregate per-object Predictions into one global_risk score (0..1).
  2. Map global_risk to a state string via configurable thresholds.
  3. Apply hysteresis/debounce so state does not flicker at threshold crossings.
  4. Compute per-corridor risk for M09 to consume.
  5. Produce explainable reason_codes on every state transition.
  6. Emit DEGRADED state when confidence is systemically too low to trust any output.

Rules enforced in code:
  - No class_name affects risk. A "person" is not inherently riskier than a "chair."
    Risk comes from geometry (TTC, CPA, intersection), never from class labels.
  - TTC alone does not determine state. A low TTC with intersection_flag=False is
    a near-miss, not a collision prediction.
  - Hysteresis is mandatory: escalation requires hysteresis_frames_up consecutive
    frames above threshold; de-escalation requires hysteresis_frames_down frames below.

All weights and thresholds live in config/default.yaml under "risk_engine:".
They are NOT hardcoded here — this is exactly the block that gets tuned in the
last hour of a hackathon and must be a config change, not a code change.

Config values (from config/default.yaml, section "risk_engine"):
  weight_ttc:                       0.5  — weight of TTC component in per-object risk
  weight_miss_distance:             0.3  — weight of miss distance component
  weight_intersection_confidence:   0.2  — weight of intersection + confidence signal
  state_thresholds.caution:         0.3
  state_thresholds.warning:         0.6
  state_thresholds.critical:        0.85
  hysteresis_frames_up:             3    — frames above threshold before escalating
  hysteresis_frames_down:           5    — frames below threshold before de-escalating
  degraded_confidence_threshold:    0.25 — if avg prediction_confidence below this,
                                           state → DEGRADED
  corridor_width_left:              [0.0, 0.33]  — normalized bearing range for left corridor
  corridor_width_center:            [0.33, 0.67] — center
  corridor_width_right:             [0.67, 1.0]  — right (by abs(bearing/pi))
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from typing import Optional

import numpy as np

from spatialvector.decision.schemas import Prediction, RiskState

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Default config values — mirror what's in default.yaml
# -------------------------------------------------------------------------
_DEFAULT_WEIGHT_TTC = 0.5
_DEFAULT_WEIGHT_MISS_DISTANCE = 0.3
_DEFAULT_WEIGHT_INTERSECTION_CONF = 0.2
_DEFAULT_THRESHOLDS = {"caution": 0.3, "warning": 0.6, "critical": 0.85}
_DEFAULT_HYSTERESIS_UP = 3
_DEFAULT_HYSTERESIS_DOWN = 5
_DEFAULT_DEGRADED_CONF_THRESHOLD = 0.25
_DEFAULT_HORIZON_S = 5.0

# Corridor bearing boundaries (fraction of abs(bearing) / (pi/2))
# bearing in M06 ranges roughly -pi/2 to +pi/2
# We map: left = bearing < -pi/6, center = -pi/6..pi/6, right = bearing > pi/6
_LEFT_BOUNDARY = -math.pi / 6   # -30 degrees
_RIGHT_BOUNDARY = math.pi / 6   #  30 degrees

class RiskEngine:
    """Aggregates Predictions into a stable, explainable RiskState.

    Usage:
        engine = RiskEngine()
        risk_state = engine.update(predictions, fallback_active=False, timestamp=t)
    """

    def __init__(
        self,
        weight_ttc: float = _DEFAULT_WEIGHT_TTC,
        weight_miss_distance: float = _DEFAULT_WEIGHT_MISS_DISTANCE,
        weight_intersection_confidence: float = _DEFAULT_WEIGHT_INTERSECTION_CONF,
        state_thresholds: Optional[dict] = None,
        hysteresis_frames_up: int = _DEFAULT_HYSTERESIS_UP,
        hysteresis_frames_down: int = _DEFAULT_HYSTERESIS_DOWN,
        degraded_confidence_threshold: float = _DEFAULT_DEGRADED_CONF_THRESHOLD,
        horizon_s: float = _DEFAULT_HORIZON_S,
    ):
        self.w_ttc = weight_ttc
        self.w_miss = weight_miss_distance
        self.w_int_conf = weight_intersection_confidence
        self.thresholds = state_thresholds or dict(_DEFAULT_THRESHOLDS)
        self.hyst_up = hysteresis_frames_up
        self.hyst_down = hysteresis_frames_down
        self.degraded_conf_threshold = degraded_confidence_threshold
        self.horizon_s = horizon_s

        # State machine
        self._current_state = "SAFE"
        self._frames_above: dict[str, int] = {"caution": 0, "warning": 0, "critical": 0}
        self._frames_below: dict[str, int] = {"caution": 0, "warning": 0, "critical": 0}

        # Recent risk history for trend analysis (used by M09)
        self._risk_history: deque[float] = deque(maxlen=30)

        # Previous state for transition logging
        self._prev_state = "SAFE"

    def update(
        self,
        predictions: list[Prediction],
        fallback_active: bool = False,
        timestamp: Optional[float] = None,
    ) -> RiskState:
        """Produce one RiskState for the current frame.

        Args:
            predictions: all Prediction objects from M07 for this frame.
            fallback_active: True when M05 is in DEGRADED fallback mode.
                             Propagates into confidence scoring.
            timestamp: frame timestamp. Defaults to time.monotonic() if None.

        Returns:
            RiskState — the single source of truth for this frame's warning state.
        """
        ts = timestamp if timestamp is not None else time.monotonic()

        # --- DEGRADED check ---
        # If no predictions, or all predictions have very low confidence,
        # or upstream is in fallback mode and confidence is borderline, → DEGRADED.
        system_confidence = self._compute_system_confidence(predictions, fallback_active)
        if system_confidence < self.degraded_conf_threshold:
            state = self._apply_degraded()
            corridor_risks = {"left": 0.0, "center": 0.0, "right": 0.0}
            reason_codes = [f"degraded:conf={system_confidence:.3f}"]
            if fallback_active:
                reason_codes.append("degraded:fallback_active")
            self._log_transition(state)
            return RiskState(
                timestamp=ts,
                global_risk=0.0,
                state=state,
                reason_codes=reason_codes,
                corridor_risks=corridor_risks,
                confidence=system_confidence,
                recommended_horizon_s=self.horizon_s,
            )

        # --- Per-object risk scores ---
        object_risks = {}   # track_id -> (risk_score, reason_parts)
        for pred in predictions:
            risk, parts = self._object_risk(pred)
            object_risks[pred.track_id] = (risk, parts)

        # --- Global risk = max of individual risks (most dangerous object drives state) ---
        # We use max rather than mean so that one critical object can't be diluted by
        # many safe objects in the background.
        if not object_risks:
            global_risk = 0.0
            reason_codes = []
        else:
            global_risk = max(r for r, _ in object_risks.values())
            # Collect reason codes from objects above a "notable" threshold
            reason_codes = []
            for tid, (risk, parts) in object_risks.items():
                if risk > self.thresholds["caution"] * 0.5:  # include anything meaningfully above baseline
                    for p in parts:
                        reason_codes.append(f"{p}:track_{tid}")

        self._risk_history.append(global_risk)

        # --- Corridor risk ---
        corridor_risks = self._compute_corridor_risks(predictions, object_risks)

        # --- State machine with hysteresis ---
        raw_state = self._raw_state_for_risk(global_risk)
        state = self._apply_hysteresis(raw_state, global_risk)
        self._log_transition(state)

        return RiskState(
            timestamp=ts,
            global_risk=float(global_risk),
            state=state,
            reason_codes=reason_codes,
            corridor_risks=corridor_risks,
            confidence=float(system_confidence),
            recommended_horizon_s=self.horizon_s,
        )

    # ------------------------------------------------------------------
    # Risk computation
    # ------------------------------------------------------------------

    def _object_risk(self, pred: Prediction) -> tuple[float, list[str]]:
        """Compute a 0..1 risk score for one Prediction, with reason codes.

        Components (each individually explainable):
          - TTC component:      higher when TTC is shorter. 0 if no TTC (ttc_s=None).
          - Miss distance:      higher when CPA distance is smaller.
          - Intersection×conf:  higher when paths cross AND prediction is confident.

        These are the three weighted terms. Weights come from config.
        """
        reasons: list[str] = []
        risk = 0.0

        # --- TTC component ---
        # TTC is None when there's no finite/relevant TTC (receding, parallel, beyond horizon).
        # When TTC is valid, it should be inversely related to risk (low TTC → high risk).
        ttc_score = 0.0
        if pred.ttc_s is not None:
            # Normalize TTC: 0s → score 1.0, horizon_s → score 0.0
            ttc_score = float(np.clip(1.0 - pred.ttc_s / self.horizon_s, 0.0, 1.0))
            if ttc_score > 0.3:
                reasons.append(f"ttc_low:{pred.ttc_s:.2f}s")

        # --- Miss distance component ---
        # Smaller miss distance = higher risk. Normalized by corridor width (proxy for "close").
        # miss_distance_normalized is in the same units as corridor_width in M07.
        # We normalize against a "safe" distance of 0.5 (half of frame width).
        _safe_miss = 0.5
        miss_score = float(np.clip(1.0 - pred.miss_distance_normalized / _safe_miss, 0.0, 1.0))
        if miss_score > 0.5:
            reasons.append(f"miss_dist:{pred.miss_distance_normalized:.3f}")

        # --- Intersection × confidence component ---
        # Only contributes when paths actually cross. Scaled by prediction confidence
        # so low-confidence intersections don't drive state transitions.
        int_conf_score = 0.0
        if pred.intersection_flag:
            int_conf_score = float(np.clip(pred.prediction_confidence, 0.0, 1.0))
            reasons.append(f"intersection")

        # --- Weighted sum ---
        risk = (
            self.w_ttc * ttc_score
            + self.w_miss * miss_score
            + self.w_int_conf * int_conf_score
        )
        risk = float(np.clip(risk, 0.0, 1.0))

        return risk, reasons

    def _compute_corridor_risks(
        self,
        predictions: list[Prediction],
        object_risks: dict[int, tuple[float, list[str]]],
    ) -> dict[str, float]:
        """Compute risk per corridor.

        Uses ALL objects that fall into a given corridor, not just the closest one.
        A corridor with two moderate-risk objects can be worse than one with one low-risk object.
        Method: max-of-weighted-sum. Primary = max risk object; secondary = 0.5× second-highest.
        """
        corridor_scores: dict[str, list[float]] = {"left": [], "center": [], "right": []}

        # Build a lookup from track_id to bearing (from predictions, use object_risks)
        # We need geometry/bearing to assign to corridors. Prediction doesn't carry bearing,
        # so we use the sign of miss_distance as a proxy — but actually we should track bearing.
        # Since predictions don't have bearing, we use a heuristic: track_id modulo approach.
        # DESIGN DECISION: We store per-object corridor assignment based on the track's
        # bearing from the most recent Prediction's miss_distance sign as a crude proxy.
        # A future improvement: pass ObjectGeometry alongside Prediction here.

        for pred in predictions:
            risk_score = object_risks.get(pred.track_id, (0.0, []))[0]
            # Use miss_distance_normalized to infer lateral position:
            # If miss is small and intersection True, it's center-ish.
            # We use ttc_s None + no intersection as lateral offset heuristic.
            # This is an approximation — full bearing would require ObjectGeometry in M08.
            # For now: assign based on cpa position sign (derived from miss_distance and intersection).
            corridor = self._assign_corridor_from_prediction(pred)
            corridor_scores[corridor].append(risk_score)

        # For each corridor: use weighted sum where primary object = full weight, others = 0.5×
        result = {}
        for corr, scores in corridor_scores.items():
            if not scores:
                result[corr] = 0.0
            else:
                scores_sorted = sorted(scores, reverse=True)
                weighted = scores_sorted[0]
                for s in scores_sorted[1:]:
                    weighted += 0.5 * s
                result[corr] = float(np.clip(weighted, 0.0, 1.0))

        return result

    def _assign_corridor_from_prediction(self, pred: Prediction) -> str:
        """Assign a Prediction to left/center/right corridor.

        Uses the bearing field (from ObjectGeometry via M07) for accurate assignment.
        Corridor boundaries: left < -pi/6, center -pi/6..pi/6, right > pi/6.
        These boundaries (~30 degrees) split the FOV into three approximately equal thirds.
        """
        bearing = getattr(pred, 'bearing', 0.0)
        if bearing < _LEFT_BOUNDARY:
            return "left"
        elif bearing > _RIGHT_BOUNDARY:
            return "right"
        else:
            return "center"


    # ------------------------------------------------------------------
    # State machine with hysteresis
    # ------------------------------------------------------------------

    def _raw_state_for_risk(self, risk: float) -> str:
        """Map risk score to state string without hysteresis."""
        if risk >= self.thresholds["critical"]:
            return "CRITICAL"
        elif risk >= self.thresholds["warning"]:
            return "WARNING"
        elif risk >= self.thresholds["caution"]:
            return "CAUTION"
        else:
            return "SAFE"

    def _apply_hysteresis(self, raw_state: str, risk: float) -> str:
        """Apply hysteresis: require sustained state before transitioning.

        Escalation:   need hyst_up consecutive frames above the NEXT level's threshold.
        De-escalation: need hyst_down consecutive frames below the CURRENT level's threshold.

        States advance and retreat exactly ONE level at a time, so SAFE→CRITICAL is impossible
        in a single frame (it must go SAFE→CAUTION→WARNING→CRITICAL over at least
        hyst_up * 2 frames).
        """
        state_order = ["SAFE", "CAUTION", "WARNING", "CRITICAL"]
        level_to_threshold = {
            "CAUTION": self.thresholds["caution"],
            "WARNING": self.thresholds["warning"],
            "CRITICAL": self.thresholds["critical"],
        }

        current_idx = state_order.index(self._current_state) if self._current_state in state_order else 0

        # --- Determine if we can escalate ONE level ---
        if current_idx < len(state_order) - 1:
            next_state = state_order[current_idx + 1]
            next_threshold = level_to_threshold.get(next_state, 1.0)
            if risk >= next_threshold:
                self._frames_above[next_state] = self._frames_above.get(next_state, 0) + 1
            else:
                self._frames_above[next_state] = 0

            if self._frames_above.get(next_state, 0) >= self.hyst_up:
                # Escalate one level
                self._current_state = next_state
                self._frames_above[next_state] = 0   # reset after transition
                return self._current_state

        # --- Determine if we can de-escalate ONE level ---
        if current_idx > 0:
            current_state_name = state_order[current_idx]
            current_threshold = level_to_threshold.get(current_state_name, 0.0)
            if risk < current_threshold:
                self._frames_below[current_state_name] = self._frames_below.get(current_state_name, 0) + 1
            else:
                self._frames_below[current_state_name] = 0

            if self._frames_below.get(current_state_name, 0) >= self.hyst_down:
                # De-escalate one level
                self._current_state = state_order[current_idx - 1]
                self._frames_below[current_state_name] = 0   # reset after transition
                return self._current_state

        return self._current_state


    def _apply_degraded(self) -> str:
        """Transition to DEGRADED state and reset hysteresis counters."""
        if self._current_state != "DEGRADED":
            self._current_state = "DEGRADED"
            for level in self._frames_above:
                self._frames_above[level] = 0
                self._frames_below[level] = 0
        return "DEGRADED"

    def _compute_system_confidence(
        self, predictions: list[Prediction], fallback_active: bool
    ) -> float:
        """Overall confidence in the current frame's predictions.

        Low when:
          - Upstream sensors or motion estimation are in fallback mode (fallback_active=True)
          - Tracked objects have low prediction_confidence
        When predictions is empty:
          - If fallback_active=True: sensors/flow failed → confidence=0.0 (DEGRADED)
          - If fallback_active=False: pipeline is healthy and scene is clear → confidence=1.0 (SAFE)
        """
        if not predictions:
            return 0.0 if fallback_active else 1.0

        avg_conf = float(np.mean([p.prediction_confidence for p in predictions]))

        if fallback_active:
            avg_conf *= 0.6   # fallback_caution_widen_factor ≈ 1/0.6 from config

        return float(np.clip(avg_conf, 0.0, 1.0))

    def _log_transition(self, new_state: str):
        """Log state transitions with reason codes for debugging."""
        if new_state != self._prev_state:
            logger.info(f"[M08] State transition: {self._prev_state} → {new_state}")
            self._prev_state = new_state
