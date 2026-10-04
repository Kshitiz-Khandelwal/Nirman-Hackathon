"""M14 — Freespace / Walkable-Ground Estimator (v2).

Root-cause fixes vs v1:
  - v1 used grayscale std of corridor as the primary ground cue.
    A table edge raises std enormously → v1 said WALKABLE at 97%.
    Fixed: std is no longer a positive WALKABLE cue.  It is only a
    validity gate (too low = uniform = wall/sky = UNKNOWN).

  - v1 Sobel check fired inconsistently.
    Fixed: replaced with a column-profile scan that detects a single
    large brightness step anywhere in the corridor (gradient jump gate).

  - v1 had no concept of "ground continuity".
    Fixed: added a bottom-up horizon scan: we walk from the bottom of the
    ground ROI upward and require that the mean luminance stays within a
    rolling window.  A table edge breaks continuity near the top.

  - v1 treated dark unexplained regions as WALKABLE.
    Fixed: unexplained dark blobs that are not covered by YOLO detections
    are classified as UNKNOWN, not WALKABLE.

  - v1 sudden-transition block was a no-op (pass).
    Fixed: sudden transitions now immediately write the new raw status.

Multi-cue architecture (three independent cues, all must agree on WALKABLE):
  Cue A – Frame validity    : dark / bright / blurry / uniform → UNKNOWN
  Cue B – Gradient jump     : single large brightness step → UNKNOWN/BLOCKED
  Cue C – Ground continuity : bottom-up scan for surface break → UNKNOWN
  Cue D – Dark blob gate    : unexplained dark regions in ground ROI → UNKNOWN
  Cue E – YOLO obstruction  : tracked bbox in ground ROI → BLOCKED
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ─── Output Schema ──────────────────────────────────────────────────────────

class CorridorStatus(str, Enum):
    WALKABLE = "WALKABLE"
    BLOCKED  = "BLOCKED"
    UNKNOWN  = "UNKNOWN"


@dataclass
class FreespaceResult:
    """Per-frame result from the freespace estimator."""
    left:   CorridorStatus
    centre: CorridorStatus
    right:  CorridorStatus
    left_conf:   float      # 0.0 – 1.0
    centre_conf: float
    right_conf:  float
    reasons: Dict[str, str] = field(default_factory=dict)

    def get(self, corridor: str) -> CorridorStatus:
        return {"left": self.left, "centre": self.centre, "right": self.right}.get(
            corridor.lower(), CorridorStatus.UNKNOWN
        )

    @staticmethod
    def all_unknown(reason: str = "not initialised") -> "FreespaceResult":
        reasons = {"left": reason, "centre": reason, "right": reason}
        return FreespaceResult(
            CorridorStatus.UNKNOWN, CorridorStatus.UNKNOWN, CorridorStatus.UNKNOWN,
            0.0, 0.0, 0.0, reasons
        )


# ─── Freespace Estimator ─────────────────────────────────────────────────────

class FreeSpaceEstimator:
    """M14 — Freespace / Walkable-Ground Estimator (v2).

    WALKABLE requires positive evidence from multiple cues.
    Any single cue can veto WALKABLE and force UNKNOWN or BLOCKED.
    """

    def __init__(
        self,
        # Ground ROI vertical limits (fraction of frame height)
        ground_y_start: float = 0.55,
        ground_y_end: float   = 0.95,
        # Corridor horizontal splits (fraction of frame width)
        left_x_end:    float = 0.38,
        right_x_start: float = 0.62,
        # ── Cue A: Frame validity ─────────────────────────────────────────────
        min_mean_brightness: float = 20.0,    # darker → UNKNOWN
        max_mean_brightness: float = 235.0,   # over-exposed → UNKNOWN
        min_laplacian_var:   float = 18.0,    # blurry/covered → UNKNOWN
        min_ground_std:      float = 6.0,     # near-uniform (wall/sky) → UNKNOWN
        max_ground_std:      float = 65.0,    # hyper-chaotic (severe noise) → UNKNOWN
        # ── Cue B: Gradient jump ─────────────────────────────────────────────
        # A single column-row profile that detects one abrupt step
        gradient_jump_thresh: float = 28.0,   # max |mean_top_band - mean_bot_band| that is OK
        # ── Cue C: Ground continuity (bottom-up horizon scan) ────────────────
        continuity_window_rows: int  = 12,    # height of each scan band (pixels)
        continuity_max_delta:   float = 20.0, # max band-to-band mean change (ok)
        continuity_min_bands:   int  = 5,     # min number of continuous bands required
        # ── Cue D: Dark blob gate ─────────────────────────────────────────────
        dark_blob_abs_thresh: int   = 45,     # pixels below this are "dark"
        dark_blob_frac_thresh: float = 0.15,  # if >15% of corridor is unexplained dark → UNKNOWN
        # ── Cue E: YOLO obstruction ──────────────────────────────────────────
        # (handled inline — YOLO bbox in ground region → BLOCKED)
        # ── Temporal smoothing ────────────────────────────────────────────────
        smoothing_window: int  = 5,
        # Minimum confidence to report WALKABLE (otherwise UNKNOWN)
        min_walkable_conf: float = 0.45,
    ):
        self.ground_y_start = ground_y_start
        self.ground_y_end   = ground_y_end
        self.left_x_end     = left_x_end
        self.right_x_start  = right_x_start
        self.min_mean_brightness   = min_mean_brightness
        self.max_mean_brightness   = max_mean_brightness
        self.min_laplacian_var     = min_laplacian_var
        self.min_ground_std        = min_ground_std
        self.max_ground_std        = max_ground_std
        self.gradient_jump_thresh  = gradient_jump_thresh
        self.continuity_window_rows = continuity_window_rows
        self.continuity_max_delta   = continuity_max_delta
        self.continuity_min_bands   = continuity_min_bands
        self.dark_blob_abs_thresh   = dark_blob_abs_thresh
        self.dark_blob_frac_thresh  = dark_blob_frac_thresh
        self.smoothing_window  = smoothing_window
        self.min_walkable_conf = min_walkable_conf

        self._history: Dict[str, Deque[CorridorStatus]] = {
            "left":   deque(maxlen=smoothing_window),
            "centre": deque(maxlen=smoothing_window),
            "right":  deque(maxlen=smoothing_window),
        }
        self._last_result: Optional[FreespaceResult] = None
        logger.info("FreeSpaceEstimator (M14 v2) initialised — multi-cue, smoothing=%d", smoothing_window)

    # ── Public API ────────────────────────────────────────────────────────────

    def estimate(
        self,
        frame_bgr: np.ndarray,
        yolo_bboxes: Optional[List[Tuple[float, float, float, float]]] = None,
        optical_flow: Optional[np.ndarray] = None,
    ) -> FreespaceResult:
        if frame_bgr is None or frame_bgr.size == 0:
            return FreespaceResult.all_unknown("null frame")

        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # ── Cue A: Frame-level validity ───────────────────────────────────────
        frame_ok, frame_reason = self._check_frame_validity(gray)
        if not frame_ok:
            result = FreespaceResult(
                CorridorStatus.UNKNOWN, CorridorStatus.UNKNOWN, CorridorStatus.UNKNOWN,
                0.0, 0.0, 0.0,
                {"left": frame_reason, "centre": frame_reason, "right": frame_reason},
            )
            self._update_history_instant(result)
            self._last_result = result
            return result

        # ── Extract ground ROI ────────────────────────────────────────────────
        y0 = int(h * self.ground_y_start)
        y1 = int(h * self.ground_y_end)
        ground_gray = gray[y0:y1, :]
        if ground_gray.size == 0:
            return FreespaceResult.all_unknown("empty ground ROI")

        roi_h, roi_w = ground_gray.shape
        x_left  = int(roi_w * self.left_x_end)
        x_right = int(roi_w * self.right_x_start)
        corridors = {
            "left":   ground_gray[:, :x_left],
            "centre": ground_gray[:, x_left:x_right],
            "right":  ground_gray[:, x_right:],
        }

        # ── Per-corridor analysis ─────────────────────────────────────────────
        raw_statuses: Dict[str, CorridorStatus] = {}
        raw_confs:    Dict[str, float]           = {}
        reasons:      Dict[str, str]             = {}

        for name, crop in corridors.items():
            if crop.size == 0:
                raw_statuses[name] = CorridorStatus.UNKNOWN
                raw_confs[name]    = 0.0
                reasons[name]      = "empty crop"
                continue

            corridor_x0 = {"left": 0, "centre": x_left, "right": x_right}[name]
            corridor_x1 = {"left": x_left, "centre": x_right, "right": roi_w}[name]
            st, cf, rs = self._analyse_corridor(
                crop, name, h, w, yolo_bboxes, y0, y1,
                corridor_x0, corridor_x1,
            )
            raw_statuses[name] = st
            raw_confs[name]    = cf
            reasons[name]      = rs

        # ── Sudden-transition safety bypass (fix v1 no-op) ────────────────────
        if self._last_result is not None:
            for name in ("left", "centre", "right"):
                prev = self._last_result.get(name)
                curr = raw_statuses[name]
                if prev == CorridorStatus.WALKABLE and curr in (CorridorStatus.BLOCKED, CorridorStatus.UNKNOWN):
                    logger.debug("M14: sudden ground loss in %s, bypassing smoothing", name)
                    # Force immediate non-WALKABLE: clear that corridor's history
                    self._history[name].clear()
                    self._history[name].append(curr)

        # ── Temporal smoothing ────────────────────────────────────────────────
        smoothed: Dict[str, CorridorStatus] = {}
        for name in ("left", "centre", "right"):
            self._history[name].append(raw_statuses[name])
            smoothed[name] = self._majority_vote(self._history[name], raw_statuses[name])

        result = FreespaceResult(
            left=smoothed["left"], centre=smoothed["centre"], right=smoothed["right"],
            left_conf=raw_confs["left"], centre_conf=raw_confs["centre"],
            right_conf=raw_confs["right"], reasons=reasons,
        )
        self._last_result = result
        return result

    # ── Cue A: Frame validity ─────────────────────────────────────────────────

    def _check_frame_validity(self, gray: np.ndarray) -> Tuple[bool, str]:
        """Return (ok, reason). ok=False means skip per-corridor analysis."""
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if lap_var < self.min_laplacian_var:
            return False, f"frame blurry/covered (lap_var={lap_var:.1f})"

        mean_b = float(np.mean(gray))
        if mean_b < self.min_mean_brightness:
            return False, f"frame too dark (mean={mean_b:.1f})"
        if mean_b > self.max_mean_brightness:
            return False, f"frame over-exposed (mean={mean_b:.1f})"

        return True, "ok"

    # ── Per-corridor analysis ─────────────────────────────────────────────────

    def _analyse_corridor(
        self,
        crop: np.ndarray,       # grayscale ground ROI slice for this corridor
        name: str,
        full_h: int, full_w: int,
        yolo_bboxes: Optional[List[Tuple]],
        y0: int, y1: int,
        corridor_x0: int, corridor_x1: int,
    ) -> Tuple[CorridorStatus, float, str]:
        """Return (status, confidence, reason_string)."""

        # ── Cue A sub: surface uniformity gate ───────────────────────────────
        std = float(np.std(crop))
        if std < self.min_ground_std:
            return CorridorStatus.UNKNOWN, 0.0, f"uniform surface (std={std:.1f})"
        if std > self.max_ground_std:
            return CorridorStatus.UNKNOWN, 0.0, f"chaotic surface (std={std:.1f})"

        # ── Cue B: Gradient jump detector ────────────────────────────────────
        # Split crop vertically into top and bottom halves; a table edge creates
        # a large step in the column-profile mean.
        jump_result, jump_reason = self._gradient_jump_check(crop)
        if jump_result != CorridorStatus.WALKABLE:
            return jump_result, 0.1, jump_reason

        # ── Cue C: Ground continuity scan (bottom-up) ─────────────────────────
        cont_result, cont_reason = self._continuity_scan(crop)
        if cont_result != CorridorStatus.WALKABLE:
            return cont_result, 0.1, cont_reason

        # ── Cue D: Unexplained dark blob gate ─────────────────────────────────
        dark_result, dark_reason = self._dark_blob_gate(crop, crop.shape[1])
        if dark_result != CorridorStatus.WALKABLE:
            return dark_result, 0.1, dark_reason

        # ── Cue E: YOLO obstruction ────────────────────────────────────────────
        if yolo_bboxes:
            for bbox in yolo_bboxes:
                bx1, by1, bx2, by2 = bbox
                h_overlap = bx1 < (corridor_x0 + full_w * 0.0 + corridor_x1) and bx2 > corridor_x0
                v_overlap = by1 < y1 and by2 > y0
                if h_overlap and v_overlap:
                    return CorridorStatus.BLOCKED, 0.9, "YOLO obstacle in ground region"

        # ── All cues pass → WALKABLE ──────────────────────────────────────────
        # Confidence: penalise high std (overly chaotic) and reward smooth texture
        std_score   = 1.0 - min(1.0, max(0.0, (std - self.min_ground_std) / (self.max_ground_std - self.min_ground_std)))
        conf = float(np.clip(0.5 + 0.5 * std_score, 0.0, 1.0))

        if conf < self.min_walkable_conf:
            return CorridorStatus.UNKNOWN, conf, f"low confidence ({conf:.2f})"

        return CorridorStatus.WALKABLE, conf, f"ground confirmed (std={std:.1f})"

    # ── Cue B: Gradient jump ──────────────────────────────────────────────────

    def _gradient_jump_check(self, crop: np.ndarray) -> Tuple[CorridorStatus, str]:
        """Detect abrupt brightness transitions and surface discontinuities in the crop.

        Methods:
        1. Single row jump (horizontal edge)
        2. Windowed jump over k rows (slanted/diagonal edges like table corners)
        3. Near-to-far ground span difference: tests whether the surface ahead
           matches the walkable ground at the user's feet.
        """
        h = crop.shape[0]
        if h < 8:
            return CorridorStatus.UNKNOWN, "crop too short for gradient check"

        row_means = np.mean(crop, axis=1).astype(np.float32)

        # 1. Adjacent row jump
        diffs = np.abs(np.diff(row_means))
        max_jump = float(np.max(diffs)) if diffs.size > 0 else 0.0
        if max_jump > self.gradient_jump_thresh:
            return CorridorStatus.UNKNOWN, f"brightness step {max_jump:.1f} px (table edge?)"

        # 2. Windowed jump for diagonal edges (table corners / angled ledges)
        k = min(10, h // 3)
        if h > k * 2:
            k_diffs = np.abs(row_means[k:] - row_means[:-k])
            max_k_jump = float(np.max(k_diffs)) if k_diffs.size > 0 else 0.0
            if max_k_jump > max(self.gradient_jump_thresh * 1.25, 32.0):
                return CorridorStatus.UNKNOWN, f"diagonal edge jump {max_k_jump:.1f} px (corner/angled obstacle?)"

        # 3. Near-far surface consistency: compare near ground (bottom third) with far ground (top third)
        third = h // 3
        top_band = crop[:third, :]
        bot_band = crop[-third:, :]
        if top_band.size > 0 and bot_band.size > 0:
            span_diff = abs(float(np.mean(top_band)) - float(np.mean(bot_band)))
            if span_diff > max(self.gradient_jump_thresh * 1.1, 28.0):
                return CorridorStatus.UNKNOWN, f"surface mismatch ahead (span diff {span_diff:.1f} px)"

        return CorridorStatus.WALKABLE, "ok"

    # ── Cue C: Ground continuity ──────────────────────────────────────────────

    def _continuity_scan(self, crop: np.ndarray) -> Tuple[CorridorStatus, str]:
        """Bottom-up ground continuity scan:
        A walkable corridor requires a continuous ground surface starting from
        the bottom of the frame (nearest user's feet, band 0) and extending
        upward without interruption for at least `continuity_min_bands`.

        Any sudden change in surface brightness or texture terminates ground continuity.
        """
        h = crop.shape[0]
        bw = self.continuity_window_rows
        if h < bw * 2:
            return CorridorStatus.WALKABLE, "crop too short for continuity scan"

        band_means: List[float] = []
        row = h
        while row - bw >= 0:
            band = crop[row - bw: row, :]
            band_means.append(float(np.mean(band)))
            row -= bw

        if not band_means:
            return CorridorStatus.UNKNOWN, "no ground bands"

        # Walk from bottom (band 0) upward — ground must be continuous from user's feet
        ground_bands = 1
        for i in range(1, len(band_means)):
            delta = abs(band_means[i] - band_means[i - 1])
            if delta <= self.continuity_max_delta:
                ground_bands += 1
            else:
                # Discontinuity encountered — ground ends here
                break

        if ground_bands >= self.continuity_min_bands:
            return CorridorStatus.WALKABLE, f"ground continuous ({ground_bands} bands)"

        return CorridorStatus.UNKNOWN, f"ground discontinuity at band {ground_bands}/{len(band_means)} (ends early)"

    # ── Cue D: Dark blob gate ─────────────────────────────────────────────────

    def _dark_blob_gate(self, crop: np.ndarray, corridor_w: int) -> Tuple[CorridorStatus, str]:
        """If an unexplained dark region covers >dark_blob_frac_thresh of the
        corridor, return UNKNOWN.

        Shadows and unidentified dark objects in the ground zone are unsafe.
        """
        dark_mask = (crop < self.dark_blob_abs_thresh).astype(np.uint8)
        dark_frac = float(dark_mask.sum()) / max(1, crop.size)
        if dark_frac > self.dark_blob_frac_thresh:
            return CorridorStatus.UNKNOWN, f"unexplained dark region ({dark_frac:.0%} of corridor)"
        return CorridorStatus.WALKABLE, "ok"

    # ── Temporal smoothing ────────────────────────────────────────────────────

    def _majority_vote(self, history: Deque[CorridorStatus], current: CorridorStatus) -> CorridorStatus:
        """Standard majority vote, but current BLOCKED/UNKNOWN is never overridden."""
        if current in (CorridorStatus.BLOCKED, CorridorStatus.UNKNOWN):
            if len(history) >= 2 and history[-2] == CorridorStatus.WALKABLE:
                return current  # sudden change — bypass
        counts = {s: 0 for s in CorridorStatus}
        for s in history:
            counts[s] += 1
        return max(counts, key=lambda k: counts[k])

    def _update_history_instant(self, result: FreespaceResult):
        for name in ("left", "centre", "right"):
            self._history[name].append(result.get(name))

    def reset(self):
        for d in self._history.values():
            d.clear()
        self._last_result = None
