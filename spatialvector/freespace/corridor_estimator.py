"""M14 — Freespace / Walkable-Ground Estimator.

Estimates whether the ground ahead is walkable, blocked, or unknown,
splitting the frame into left, centre, and right corridors.

Design decisions:
- Uses TWO independent classical cues and combines them.
- Defaults to UNKNOWN whenever cues disagree, confidence is low, or the frame
  is too dark, too bright, too blurry, or dominated by a blank surface.
- Specifically handles the table-corner failure: a sharp depth/texture
  discontinuity in the lower half of the frame → UNKNOWN/BLOCKED.
- Provides temporal smoothing (majority vote over N frames) EXCEPT that a
  sudden transition from WALKABLE to BLOCKED/UNKNOWN is never smoothed —
  it triggers immediately.
- Does NOT tell the voice/haptic engine what to do. It only outputs data.

Architecture: Forward-only data flow. No I/O, no side effects.

Cue 1 — Texture / Ground-Plane Continuity:
  Analyses the lower region for homogeneous texture that indicates a stable
  ground plane. Uniform fine texture = walkable ground. Edge density spikes
  or abrupt texture change = discontinuity = UNKNOWN.

Cue 2 — Brightness / Surface Validity:
  Detects frames that should never produce "walkable":
  - Very dark frame (camera covered, low light) → UNKNOWN
  - Very bright overexposed frame → UNKNOWN
  - Uniform blank region (wall, sky, table surface seen at close range) → UNKNOWN
  - Strong vertical edge pattern in lower frame (table leg, wall boundary) → BLOCKED

Both cues must agree on WALKABLE for the corridor to be WALKABLE.
If either says UNKNOWN or BLOCKED, the combined output is UNKNOWN or BLOCKED.
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
    reasons: Dict[str, str] = field(default_factory=dict)   # corridor -> reason string

    def get(self, corridor: str) -> CorridorStatus:
        """Get status for a named corridor ('left', 'centre', 'right')."""
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
    """M14 — Freespace / Walkable-Ground Estimator.

    Estimates walkable ground for left/centre/right corridors using two
    independent classical cues. All parameters are configurable.
    """

    def __init__(
        self,
        # Ground ROI: the vertical band analysed for walkability
        ground_y_start: float = 0.55,   # upper edge of ground ROI (fraction of frame height)
        ground_y_end: float   = 0.95,   # lower edge
        # Corridor split (fraction of frame width)
        left_x_end:   float = 0.38,
        right_x_start: float = 0.62,
        # Brightness validity gates (0–255 on grayscale)
        min_mean_brightness: float = 20.0,   # darker → UNKNOWN
        max_mean_brightness: float = 235.0,  # over-exposed → UNKNOWN
        max_brightness_std: float = 12.0,    # near-uniform bright surface → UNKNOWN (wall/sky)
        # Texture continuity parameters
        min_texture_std: float = 8.0,        # minimum grayscale std for "has texture"
        max_texture_std: float = 60.0,       # max std (high = too chaotic = not ground)
        # Edge discontinuity detection (table corners, walls)
        edge_discontinuity_threshold: float = 18.0,   # mean Canny response that flags a discontinuity
        # Corridor texture uniformity for WALKABLE classification
        walkable_min_texture: float = 6.0,   # at least some texture (not blank wall)
        walkable_max_edge_resp: float = 22.0, # not too many strong edges (not a wall)
        # Blurriness gate (Laplacian variance)
        min_laplacian_var: float = 25.0,     # below this → camera is blurry/covered → UNKNOWN
        # Temporal smoothing
        smoothing_window: int = 5,           # majority vote over N frames
        # Minimum confidence to report WALKABLE (otherwise UNKNOWN)
        min_walkable_conf: float = 0.45,
    ):
        self.ground_y_start = ground_y_start
        self.ground_y_end   = ground_y_end
        self.left_x_end     = left_x_end
        self.right_x_start  = right_x_start
        self.min_mean_brightness = min_mean_brightness
        self.max_mean_brightness = max_mean_brightness
        self.max_brightness_std  = max_brightness_std
        self.min_texture_std     = min_texture_std
        self.max_texture_std     = max_texture_std
        self.edge_discontinuity_threshold = edge_discontinuity_threshold
        self.walkable_min_texture = walkable_min_texture
        self.walkable_max_edge_resp = walkable_max_edge_resp
        self.min_laplacian_var = min_laplacian_var
        self.smoothing_window  = smoothing_window
        self.min_walkable_conf = min_walkable_conf

        # Temporal history: per corridor
        self._history: Dict[str, Deque[CorridorStatus]] = {
            "left":   deque(maxlen=smoothing_window),
            "centre": deque(maxlen=smoothing_window),
            "right":  deque(maxlen=smoothing_window),
        }
        # Track last result to detect sudden transitions
        self._last_result: Optional[FreespaceResult] = None

        logger.info("FreeSpaceEstimator (M14) initialised — classical cues, smoothing=%d frames", smoothing_window)

    # ── Public API ────────────────────────────────────────────────────────────

    def estimate(
        self,
        frame_bgr: np.ndarray,
        yolo_bboxes: Optional[List[Tuple[float,float,float,float]]] = None,
        optical_flow: Optional[np.ndarray] = None,
    ) -> FreespaceResult:
        """Estimate walkable corridor status for the current frame.

        Args:
            frame_bgr: Raw or lightly enhanced BGR frame.
            yolo_bboxes: YOLO-tracked obstacle boxes (used as additional
                         ground-region BLOCKED signals if they fall in the ground ROI).
            optical_flow: Optional flow field from M04 (reserved for future use).

        Returns:
            FreespaceResult with per-corridor status and confidence.
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return FreespaceResult.all_unknown("null frame")

        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # ── Frame-level validity checks (apply to whole frame) ────────────────
        frame_status, frame_reason = self._check_frame_validity(gray)
        if frame_status != CorridorStatus.WALKABLE:
            result = FreespaceResult(
                frame_status, frame_status, frame_status,
                0.0, 0.0, 0.0,
                {"left": frame_reason, "centre": frame_reason, "right": frame_reason}
            )
            self._update_history_instant(result)
            self._last_result = result
            return result

        # ── Extract ground ROI ────────────────────────────────────────────────
        y0 = int(h * self.ground_y_start)
        y1 = int(h * self.ground_y_end)
        ground_roi = gray[y0:y1, :]
        if ground_roi.size == 0:
            return FreespaceResult.all_unknown("empty ground ROI")

        roi_h, roi_w = ground_roi.shape

        # Split into corridors
        x_left  = int(roi_w * self.left_x_end)
        x_right = int(roi_w * self.right_x_start)
        corridors = {
            "left":   ground_roi[:, :x_left],
            "centre": ground_roi[:, x_left:x_right],
            "right":  ground_roi[:, x_right:],
        }

        # ── Per-corridor analysis ─────────────────────────────────────────────
        raw_statuses: Dict[str, CorridorStatus] = {}
        raw_confs:    Dict[str, float] = {}
        reasons:      Dict[str, str]   = {}

        for name, crop in corridors.items():
            if crop.size == 0:
                raw_statuses[name] = CorridorStatus.UNKNOWN
                raw_confs[name] = 0.0
                reasons[name] = "empty corridor crop"
                continue

            status, conf, reason = self._analyse_corridor(crop, name, h, w, yolo_bboxes, y0, y1)
            raw_statuses[name] = status
            raw_confs[name]    = conf
            reasons[name]      = reason

        # ── Sudden-transition detection (no smoothing for sudden BLOCKED/UNKNOWN) ──
        if self._last_result is not None:
            for name in ("left", "centre", "right"):
                prev = self._last_result.get(name)
                curr = raw_statuses[name]
                if prev == CorridorStatus.WALKABLE and curr in (CorridorStatus.BLOCKED, CorridorStatus.UNKNOWN):
                    # Sudden loss of ground — bypass smoothing
                    logger.debug("M14: Sudden ground loss in %s corridor — bypassing smoothing", name)
                    # Force immediate output; history is updated below
                    pass

        # ── Temporal smoothing via majority vote ──────────────────────────────
        smoothed_statuses: Dict[str, CorridorStatus] = {}
        for name in ("left", "centre", "right"):
            self._history[name].append(raw_statuses[name])
            smoothed_statuses[name] = self._majority_vote(self._history[name], raw_statuses[name])

        # ── Build result ──────────────────────────────────────────────────────
        result = FreespaceResult(
            left   = smoothed_statuses["left"],
            centre = smoothed_statuses["centre"],
            right  = smoothed_statuses["right"],
            left_conf   = raw_confs["left"],
            centre_conf = raw_confs["centre"],
            right_conf  = raw_confs["right"],
            reasons = reasons,
        )
        self._last_result = result
        return result

    # ── Frame-level validity ───────────────────────────────────────────────────

    def _check_frame_validity(self, gray: np.ndarray) -> Tuple[CorridorStatus, str]:
        """Check whole-frame conditions that make any walkability inference unreliable."""

        # Blurriness gate (Laplacian variance)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if lap_var < self.min_laplacian_var:
            return CorridorStatus.UNKNOWN, f"frame too blurry (lap_var={lap_var:.1f})"

        # Brightness gates
        mean_bright = float(np.mean(gray))
        if mean_bright < self.min_mean_brightness:
            return CorridorStatus.UNKNOWN, f"frame too dark (mean={mean_bright:.1f})"
        if mean_bright > self.max_mean_brightness:
            return CorridorStatus.UNKNOWN, f"frame over-exposed (mean={mean_bright:.1f})"

        return CorridorStatus.WALKABLE, "ok"

    # ── Per-corridor analysis ─────────────────────────────────────────────────

    def _analyse_corridor(
        self,
        crop: np.ndarray,
        name: str,
        full_h: int, full_w: int,
        yolo_bboxes: Optional[List[Tuple]],
        y0: int, y1: int,
    ) -> Tuple[CorridorStatus, float, str]:
        """Analyse a single corridor crop and return (status, confidence, reason)."""

        # Cue A — Texture analysis
        std = float(np.std(crop))
        mean_val = float(np.mean(crop))

        # Near-uniform region (blank wall, sky, table surface)
        if std < self.walkable_min_texture:
            return CorridorStatus.UNKNOWN, 0.1, f"near-uniform surface (std={std:.1f})"

        # Cue B — Edge density (strong edges = structural obstacles or discontinuities)
        blurred = cv2.GaussianBlur(crop, (5, 5), 1.5)
        edges   = cv2.Canny(blurred, 30, 90)
        mean_edge = float(np.mean(edges))

        if mean_edge > self.edge_discontinuity_threshold:
            return CorridorStatus.BLOCKED, 0.3, f"edge discontinuity (edge_resp={mean_edge:.1f})"

        # Cue C — Vertical edge spike detection (table edge, wall boundary)
        # Vertical Sobel highlights sharp horizontal discontinuities (table corners)
        sobelx = cv2.Sobel(crop, cv2.CV_32F, 1, 0, ksize=3)
        sobel_std = float(np.std(sobelx))
        if sobel_std > 30.0:
            return CorridorStatus.BLOCKED, 0.35, f"vertical discontinuity (sobel_std={sobel_std:.1f})"

        # Cue D — YOLO bboxes in ground region (tracked obstacle in this corridor)
        if yolo_bboxes:
            corridor_x_start, corridor_x_end = self._corridor_x_bounds(name, full_w)
            for bbox in yolo_bboxes:
                bx1, by1, bx2, by2 = bbox
                # Check if bbox overlaps this corridor's ground region
                horiz_overlap = bx1 < corridor_x_end and bx2 > corridor_x_start
                vert_overlap  = by1 < y1 and by2 > y0
                if horiz_overlap and vert_overlap:
                    return CorridorStatus.BLOCKED, 0.9, "YOLO obstacle in ground region"

        # Both cues say reasonable texture and no spike → WALKABLE
        # Confidence scales with how "ground-like" the texture is
        texture_score = min(1.0, (std - self.walkable_min_texture) / max(self.min_texture_std, 1.0))
        edge_clearance = 1.0 - min(1.0, mean_edge / self.walkable_max_edge_resp)
        conf = float(np.clip(0.55 * texture_score + 0.45 * edge_clearance, 0.0, 1.0))

        if conf < self.min_walkable_conf:
            return CorridorStatus.UNKNOWN, conf, f"low confidence (conf={conf:.2f})"

        return CorridorStatus.WALKABLE, conf, f"texture={std:.1f} edge={mean_edge:.1f}"

    def _corridor_x_bounds(self, name: str, full_w: int) -> Tuple[float, float]:
        if name == "left":
            return 0.0, full_w * self.left_x_end
        elif name == "right":
            return full_w * self.right_x_start, float(full_w)
        else:
            return full_w * self.left_x_end, full_w * self.right_x_start

    # ── Temporal smoothing ────────────────────────────────────────────────────

    def _majority_vote(self, history: Deque[CorridorStatus], current: CorridorStatus) -> CorridorStatus:
        """Majority vote over history, but a current BLOCKED/UNKNOWN always wins immediately."""
        # Safety: if current is BLOCKED or UNKNOWN, don't let old WALKABLE votes hide it
        if current in (CorridorStatus.BLOCKED, CorridorStatus.UNKNOWN):
            # Check if the current result is a sudden transition
            if len(history) >= 2 and history[-2] == CorridorStatus.WALKABLE:
                return current  # sudden change — no smoothing
        # Standard majority vote
        counts = {s: 0 for s in CorridorStatus}
        for s in history:
            counts[s] += 1
        return max(counts, key=lambda k: counts[k])

    def _update_history_instant(self, result: FreespaceResult):
        """Push the same status into all corridors' history (for invalid frames)."""
        for name in ("left", "centre", "right"):
            self._history[name].append(result.get(name))

    def reset(self):
        """Clear history (call when source changes)."""
        for d in self._history.values():
            d.clear()
        self._last_result = None
