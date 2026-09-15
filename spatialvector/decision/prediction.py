"""
M07 — Collision Prediction: TTC + CPA + Intersection

Pure geometry module. No hardware, no threads, no I/O. No ML.
Input:  ObjectGeometry (M06) + Track (M03) per active track.
Output: Prediction per track — three separate, separately-computed geometric answers.

IMPORTANT: This module answers geometry questions only. It does NOT label anything
as "dangerous." Risk classification is M08's job.

Linear-motion assumption (documented):
  All trajectory extrapolation assumes constant velocity. This is a known limitation
  for the first prototype — pedestrians, cyclists, and vehicles are modelled as
  point-masses moving at their current estimated velocity. Non-linear motion (turns,
  acceleration, deceleration) is accepted as out-of-scope for this build.
  Implication: TTC and CPA accuracy degrades in proportion to how non-linear the
  actual motion is. For objects undergoing significant direction changes, treat
  prediction_confidence as an upper bound on reliability.

Three separate questions (never collapse into one number):
  1. CPA  — closest point of approach (distance), regardless of whether paths cross.
             Computed from: cpa_time = -dot(rel_pos, rel_vel) / dot(rel_vel, rel_vel)
             cpa_distance = |rel_pos + rel_vel * cpa_time|
  2. TTC  — time until relative distance crosses the contact threshold.
             Defined only when intersection_flag is True and the contact crossing
             occurs within the configured horizon. Otherwise ttc_s = None.
  3. Intersection — do projected paths actually cross within corridor_width_normalized
             AND within horizon_s AND in the future (cpa_time > 0)?

Config values (from config/default.yaml, section "prediction"):
  horizon_s:                    5.0   — beyond this, treat as "no near-term concern"
  contact_threshold_normalized: 0.05  — "collision" distance in normalized units
  corridor_width_normalized:    0.12  — how wide a corridor is for intersection_flag

Near-zero relative velocity handling:
  When |rel_vel| < _REL_VEL_EPSILON, objects are effectively parallel or co-moving.
  In this case: no TTC (None), intersection_flag = False, cpa = current distance.
  This is NOT treated as an error — it is a valid safe outcome.

Ego-motion note:
  The user is treated as the stationary reference frame. Ego-motion compensation
  (M05) has already been applied upstream in MotionState.corrected_flow; there is
  no second ego-motion subtraction here.
"""

from __future__ import annotations

import math
import logging
from typing import Optional

import numpy as np

from spatialvector.motion.schemas import ObjectGeometry
from spatialvector.perception.schemas import Track
from spatialvector.decision.schemas import Prediction

logger = logging.getLogger(__name__)

# Guard for near-zero relative velocity (normalized units/frame)
# Below this, trajectories are treated as parallel/co-moving.
_REL_VEL_EPSILON = 1e-6

# Default config values — override by passing kwargs to CollisionPredictor.__init__
_DEFAULT_HORIZON_S = 5.0
_DEFAULT_CONTACT_THRESHOLD_NORM = 0.05
_DEFAULT_CORRIDOR_WIDTH_NORM = 0.12

# Assumed frame rate for converting velocity units to time.
# ObjectGeometry uses normalized-per-second units (vx/W, vy/H per second).
# For now we treat geometry units as "distance units" and velocity as "distance/second."
_ASSUMED_FPS = 30.0


class CollisionPredictor:
    """Computes TTC, CPA, and intersection flag for one track per frame.

    Treats the user as the stationary reference frame (ego-motion already compensated
    by M05 upstream). Objects' velocities in ObjectGeometry are already corrected.

    Usage:
        predictor = CollisionPredictor()
        prediction = predictor.predict(geometry, track, frame_id)
    """

    def __init__(
        self,
        horizon_s: float = _DEFAULT_HORIZON_S,
        contact_threshold_normalized: float = _DEFAULT_CONTACT_THRESHOLD_NORM,
        corridor_width_normalized: float = _DEFAULT_CORRIDOR_WIDTH_NORM,
    ):
        """
        Args:
            horizon_s: finite TTC horizon. Beyond this, treat as no near-term concern.
                       Configured value: 5.0 seconds.
            contact_threshold_normalized: "collision" distance in normalized units.
                       Configured value: 0.05 (5% of frame width).
            corridor_width_normalized: corridor half-width for intersection_flag.
                       Configured value: 0.12 (12% of frame width).
        """
        self.horizon_s = horizon_s
        self.contact_threshold = contact_threshold_normalized
        self.corridor_width = corridor_width_normalized

    def predict(
        self,
        geometry: ObjectGeometry,
        track: Track,
        frame_id: int,
    ) -> Prediction:
        """Compute collision prediction for one track.

        Args:
            geometry: ObjectGeometry from M06 for this track+frame.
            track: Track from M03 for this track.
            frame_id: current frame index.

        Returns:
            Prediction with ttc_s, cpa_normalized, miss_distance_normalized,
            intersection_flag, and prediction_confidence.
        """
        # User position is (0, 0) in normalized image space — stationary reference.
        # Object position: bearing (horizontal) + normalized velocity from M06.
        # We work in a 2D normalized plane: x = horizontal (bearing proxy), y = depth proxy.
        #
        # Position: use bearing as x, approximate y from velocity direction (objects
        # coming toward image center are "ahead"). For a prototype, bearing and
        # the x-component of relative_image_velocity are sufficient for left/center/right
        # corridor decisions.
        #
        # rel_pos = object_position - user_position = (bearing_x, approach_y)
        # rel_vel = object_velocity - user_velocity = object_velocity (user is stationary)

        # Object position in normalized 2D plane
        bearing = geometry.bearing          # horizontal offset, radians (~= normalized x)
        # Convert bearing to an approximate normalized horizontal offset
        obj_x = math.sin(bearing)           # ranges -1..1, ~= normalized x position
        obj_y = 0.5                         # objects are treated as "in front" at fixed depth

        # User at origin
        user_x, user_y = 0.0, 0.0

        # Relative position (object relative to user)
        rel_pos = np.array([obj_x - user_x, obj_y - user_y], dtype=np.float64)

        # Object velocity in normalized units/second from M06
        vx, vy = geometry.relative_image_velocity
        # Sign convention: positive vy = moving down in image = moving away (receding)
        # negative vy = moving up in image = approaching
        rel_vel = np.array([vx, -vy], dtype=np.float64)   # flip vy: up = approaching = negative depth

        # --- CPA computation ---
        ttc_s, cpa_norm, miss_norm, intersection_flag = self._compute_cpa_ttc_intersection(
            rel_pos, rel_vel
        )

        # --- Prediction confidence ---
        # Derived from geometry_confidence (M06) and track stability.
        # Young tracks and low geometry confidence both reduce prediction confidence.
        pred_conf = self._compute_prediction_confidence(geometry, track)

        prediction = Prediction(
            track_id=track.track_id,
            frame_id=frame_id,
            ttc_s=ttc_s,
            cpa_normalized=cpa_norm,
            miss_distance_normalized=miss_norm,
            intersection_flag=intersection_flag,
            prediction_confidence=pred_conf,
            bearing=geometry.bearing,
        )

        logger.debug(
            f"[M07] track={track.track_id} frame={frame_id} "
            f"ttc={ttc_s} cpa={cpa_norm:.4f} intersect={intersection_flag} "
            f"conf={pred_conf:.3f}"
        )
        return prediction

    def predict_batch(
        self,
        geometries: list[ObjectGeometry],
        tracks: list[Track],
        frame_id: int,
    ) -> list[Prediction]:
        """Predict for all active tracks. Convenience wrapper."""
        track_by_id = {t.track_id: t for t in tracks}
        results = []
        for geom in geometries:
            track = track_by_id.get(geom.track_id)
            if track is None:
                continue   # track disappeared between M06 and M07; skip silently
            results.append(self.predict(geom, track, frame_id))
        return results

    # ------------------------------------------------------------------
    # Internal helpers — pure functions
    # ------------------------------------------------------------------

    def _compute_cpa_ttc_intersection(
        self,
        rel_pos: np.ndarray,
        rel_vel: np.ndarray,
    ) -> tuple[Optional[float], float, float, bool]:
        """
        Compute CPA time, CPA distance, miss distance, and intersection flag.

        Returns (ttc_s, cpa_normalized, miss_distance_normalized, intersection_flag).
        ttc_s = None when there is no finite/relevant TTC (receding, parallel, or beyond horizon).

        The three computations are independent:
          CPA answers: how close would the closest approach be?
          TTC answers: when would they actually touch (if they do)?
          Intersection answers: do the paths actually cross within the corridor?
        """
        vel_sq = float(np.dot(rel_vel, rel_vel))

        # Current distance (will be cpa_normalized if effectively static)
        current_dist = float(np.linalg.norm(rel_pos))

        if vel_sq < _REL_VEL_EPSILON:
            # Near-zero relative velocity: objects are co-moving or stationary.
            # Valid safe outcome — not an error.
            return None, current_dist, current_dist, False

        # --- CPA time ---
        # t_cpa = -dot(rel_pos, rel_vel) / dot(rel_vel, rel_vel)
        # This is the time at which d/dt(|rel_pos + rel_vel * t|²) = 0
        t_cpa = -float(np.dot(rel_pos, rel_vel)) / vel_sq

        if t_cpa <= 0.0:
            # CPA is in the past — objects are moving apart NOW
            # Receding motion: intersection_flag = False, ttc_s = None
            return None, current_dist, current_dist, False

        # --- CPA distance ---
        pos_at_cpa = rel_pos + rel_vel * t_cpa
        cpa_dist = float(np.linalg.norm(pos_at_cpa))

        # --- Intersection flag ---
        # True only if:
        #   (a) CPA distance is below corridor_width (paths come close enough)
        #   (b) CPA time is within the configured horizon
        within_corridor = cpa_dist < self.corridor_width
        within_horizon = t_cpa <= self.horizon_s
        intersection_flag = within_corridor and within_horizon

        # --- TTC ---
        # TTC = time at which |rel_pos + rel_vel * t| first drops below contact_threshold.
        # Only computed (and only valid) when intersection_flag is True.
        # We solve the quadratic |rel_pos + rel_vel*t|² = contact_threshold² for t.
        ttc_s: Optional[float] = None
        if intersection_flag:
            ttc_s = self._solve_contact_time(rel_pos, rel_vel, vel_sq)
            if ttc_s is not None and ttc_s > self.horizon_s:
                ttc_s = None   # contact beyond horizon — treat as no near-term concern

        # miss_distance = cpa_dist when no intersection
        miss_dist = cpa_dist if not intersection_flag else 0.0

        return ttc_s, cpa_dist, miss_dist, intersection_flag

    def _solve_contact_time(
        self,
        rel_pos: np.ndarray,
        rel_vel: np.ndarray,
        vel_sq: float,
    ) -> Optional[float]:
        """Solve for the first positive time t when |rel_pos + rel_vel*t| = contact_threshold.

        Quadratic: a*t² + b*t + c = 0
          a = |rel_vel|²
          b = 2 * dot(rel_pos, rel_vel)
          c = |rel_pos|² - contact_threshold²

        Returns the smaller positive root, or None if no real positive root exists.
        """
        a = vel_sq
        b = 2.0 * float(np.dot(rel_pos, rel_vel))
        c = float(np.dot(rel_pos, rel_pos)) - self.contact_threshold ** 2

        discriminant = b * b - 4.0 * a * c
        if discriminant < 0.0:
            return None  # no real solution — paths never get that close

        sqrt_d = math.sqrt(discriminant)
        t1 = (-b - sqrt_d) / (2.0 * a)
        t2 = (-b + sqrt_d) / (2.0 * a)

        # Return the smallest positive root
        candidates = [t for t in (t1, t2) if t > 0.0]
        if not candidates:
            return None
        return min(candidates)

    def _compute_prediction_confidence(
        self,
        geometry: ObjectGeometry,
        track: Track,
    ) -> float:
        """0..1 confidence in the prediction values.

        Inherits geometry_confidence from M06 (which already encodes flow quality,
        fallback_active, and FOE confidence). Additional penalty for track instability:
        a track with highly erratic velocity estimates is less predictable.
        """
        # Start from geometry_confidence — the upstream signal
        conf = float(np.clip(geometry.geometry_confidence, 0.0, 1.0))

        # Track age penalty: very young tracks have unreliable velocity estimates
        if track.track_age < 3:
            conf *= 0.4
        elif track.track_age < 5:
            conf *= 0.7

        # Velocity consistency check: if the velocity estimate has changed drastically
        # in recent frames (noisy), penalize. Proxy: use bbox history variance as track
        # stability measure (already penalized in geometry_confidence, but worth double-
        # weighting for the prediction use case).
        if len(track.center_history) >= 4:
            centers = np.array(track.center_history[-4:], dtype=np.float64)
            frame_deltas = np.diff(centers, axis=0)
            velocity_variance = float(np.var(frame_deltas))
            # Penalize when velocity varies by more than 15px² across recent frames
            if velocity_variance > 225.0:   # 15px std dev squared
                stability_factor = max(0.3, 1.0 - velocity_variance / 3000.0)
                conf *= stability_factor

        return float(np.clip(conf, 0.0, 1.0))
