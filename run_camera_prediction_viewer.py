"""SpatialVector-HMI — Standalone Camera Prediction Engine Viewer

Direct camera and prediction engine execution without web dashboard:
- Visualizes M01-M09 directly inside a high-visibility OpenCV AR window.
- Auto-scales camera feed to fit window dimensions dynamically (zero dead gray space).
- Real-time YOLOv8 object detection + ByteTrack tracking.
- Velocity vectors, FOE, and ego-motion compensation.
- Collision prediction: Time-to-Collision (TTC), Closest Point of Approach (CPA), Path Intersection.
- M08 Risk Engine state machine (SAFE, CAUTION, WARNING, CRITICAL, DEGRADED).
- M09 Corridor Policy selection (Left / Center / Right) and M10 Haptic command synthesis.

Hotkeys:
    [Q] / [ESC]  - Quit
    [SPACE]      - Pause / Resume frame playback
    [H]          - Toggle AR HUD overlay (boxes, corridors, vectors)
    [T]          - Toggle technical telemetry overlay panel
    [1] - [5]    - Switch instantly to benchmark demo scenes (S1-S5)
    [C]          - Switch back to live camera / VDO.Ninja source
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Tuple, Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from spatialvector.decision.corridor_policy import CorridorPolicy
from spatialvector.decision.prediction import CollisionPredictor
from spatialvector.decision.risk_engine import RiskEngine, RiskEngineConfig
from spatialvector.decision.schemas import HapticCommand, Prediction, RiskState
from spatialvector.motion.ego_motion import EgoMotionCompensator
from spatialvector.motion.geometry import compute_geometry_batch
from spatialvector.motion.imu_reader import SimulatedIMUReader
from spatialvector.motion.optical_flow import OpticalFlowEstimator
from spatialvector.perception.frame_source import FrameSource
from spatialvector.perception.schemas import Frame, Track
from spatialvector.perception.source_resolver import resolve_camera_source
from spatialvector.perception.tracker import MultiObjectTracker

FIXTURES_DIR = ROOT / "tests" / "fixtures"

BENCHMARK_SCENES = {
    "1": ("Scene 1: Baseline (Open Corridor)", FIXTURES_DIR / "demo_scene1_baseline.mp4"),
    "2": ("Scene 2: Parallel Wall (Proximity without Collision)", FIXTURES_DIR / "demo_scene2_parallel_wall.mp4"),
    "3": ("Scene 3: Turn Toward Wall (Collision Warning)", FIXTURES_DIR / "demo_scene3_turn_toward_wall.mp4"),
    "4": ("Scene 4: Crossing Person (Lateral Collision Course)", FIXTURES_DIR / "demo_scene4_crossing_person.mp4"),
    "5": ("Scene 5: Safe Passing (Adjacent Corridor Clear)", FIXTURES_DIR / "demo_scene5_safe_passing.mp4"),
}


def parse_args():
    parser = argparse.ArgumentParser(description="SpatialVector-HMI Standalone Camera Prediction Engine Viewer")
    parser.add_argument("--source", type=str, default=None, help="Camera index (e.g. 0), video file, or URL (VDO.Ninja)")
    parser.add_argument("--scene", type=str, choices=["1", "2", "3", "4", "5"], default=None, help="Directly open benchmark scene 1-5")
    parser.add_argument("--fps", type=float, default=20.0, help="Target processing FPS")
    parser.add_argument("--conf", type=float, default=0.35, help="YOLO detection confidence threshold")
    parser.add_argument("--tracker", type=str, choices=["bytetrack", "sort"], default="bytetrack", help="Tracker algorithm")
    return parser.parse_args()


class PredictionViewer:
    def __init__(self, source_str: str, target_fps: float = 20.0, det_conf: float = 0.35, tracker_type: str = "bytetrack"):
        self.target_fps = target_fps
        self.det_conf = det_conf
        self.tracker_type = tracker_type

        # Interactive state
        self.paused = False
        self.show_hud = True
        self.show_telemetry = True    # Rich telemetry visible by default
        self.is_fullscreen = False
        self.win_name = "SpatialVector-HMI — Camera Perception & Prediction Engine"
        self.current_source_label = str(source_str)
        self.primary_source = source_str

        # Pipeline modules
        self.init_source(source_str)
        self.tracker = MultiObjectTracker(backend=tracker_type, history_length=10, confidence_threshold=det_conf)
        self.flow_est = OpticalFlowEstimator(max_corners=200, quality_level=0.01, min_distance=7.0)
        self.imu = SimulatedIMUReader(gyro_fn=lambda t: (0.0, 0.0, 0.0), rate_hz=100.0)
        self.imu.start()
        self.compensator = EgoMotionCompensator(fallback_flow_quality_threshold=0.30)

        # Decision modules
        self.predictor = CollisionPredictor(horizon_s=5.0, contact_threshold_normalized=0.05, corridor_width_normalized=0.12)
        self.engine = RiskEngine(
            weight_ttc=0.50,
            weight_miss_distance=0.30,
            weight_intersection_confidence=0.20,
            state_thresholds={"caution": 0.30, "warning": 0.60, "critical": 0.85},
            hysteresis_frames_up=2,
            hysteresis_frames_down=4,
            degraded_confidence_threshold=0.05,   # Graceful threshold for camera/phone streams
        )
        self.policy = CorridorPolicy(all_unsafe_risk_threshold=0.70, trend_window_frames=5)

        self.last_frame = None
        self.fps_history = []
        self.last_time = time.monotonic()

    def init_source(self, src: str | int):
        is_network = isinstance(src, str) and any(src.lower().startswith(p) for p in ("http://", "https://", "rtsp://"))
        self.frame_src = FrameSource(
            source=src,
            target_fps=self.target_fps,
            queue_size=5,
            loop_video=(not is_network and isinstance(src, str)),
        )
        self.frame_src.start()
        self.current_source_label = str(src)

    def switch_source(self, new_source: str | int, label: str):
        print(f"\n[*] Switching input source to: {label}")
        self.frame_src.stop()
        self.init_source(new_source)
        self.current_source_label = label

    def run(self):
        win_name = self.win_name
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(win_name, cv2.WND_PROP_ASPECT_RATIO, cv2.WINDOW_FREERATIO)
        cv2.resizeWindow(win_name, 1280, 720)

        print("\n" + "=" * 74)
        print("   SpatialVector-HMI — Standalone Camera Prediction Engine Viewer   ")
        print("=" * 74)
        print(f"[*] Input Source: {self.current_source_label}")
        print("[*] Hotkeys:")
        print("    [SPACE]   Pause / Resume")
        print("    [F]       Toggle Fullscreen Mode")
        print("    [H]       Toggle HUD Overlay")
        print("    [T]       Toggle Telemetry Panel")
        print("    [1] - [5] Benchmark Scenes S1–S5")
        print("    [C]       Return to Live Camera")
        print("    [Q]/[ESC] Quit\n")

        consecutive_misses = 0

        try:
            while True:
                t_start = time.monotonic()

                if not self.paused:
                    f_obj = self.frame_src.get_frame(timeout=0.3)
                    if f_obj is None:
                        consecutive_misses += 1
                        if consecutive_misses > 20 and self.last_frame is None:
                            # Draw waiting placeholder in full 1280x720 HD
                            blank = np.full((720, 1280, 3), 18, dtype=np.uint8)
                            cv2.rectangle(blank, (0, 0), (1280, 52), (32, 32, 36), -1)
                            cv2.putText(blank, "SPATIALVECTOR-HMI // PREDICTION ENGINE", (24, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 220, 255), 2, cv2.LINE_AA)
                            
                            # Center card
                            cv2.rectangle(blank, (340, 240), (940, 480), (28, 28, 34), -1)
                            cv2.rectangle(blank, (340, 240), (940, 480), (55, 55, 65), 1)
                            cv2.putText(blank, "CONNECTING TO CAMERA SOURCE...", (380, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (240, 240, 240), 2, cv2.LINE_AA)
                            cv2.putText(blank, f"Source: {self.current_source_label[:48]}", (380, 355), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (140, 200, 140), 1, cv2.LINE_AA)
                            cv2.putText(blank, "Press [1] - [5] to test with recorded video scenes", (380, 405), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 200, 255), 1, cv2.LINE_AA)
                            cv2.putText(blank, "Press [Q] or [ESC] to exit", (380, 440), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1, cv2.LINE_AA)
                            
                            cv2.imshow(win_name, blank)
                            key = cv2.waitKey(30) & 0xFF
                            if self.handle_key(key):
                                break
                        time.sleep(0.02)
                        continue

                    consecutive_misses = 0
                    self.last_frame = f_obj
                else:
                    f_obj = self.last_frame
                    if f_obj is None:
                        time.sleep(0.05)
                        continue

                # Process Frame Through Prediction Engine
                img = f_obj.image
                orig_h, orig_w = img.shape[:2]
                ts = time.monotonic()

                tracks = self.tracker.track(f_obj)
                flow = self.flow_est.update(img, f_obj.frame_id, ts)
                imu_s = self.imu.get_latest()
                motion_st = self.compensator.compensate(flow, imu_s, ts, orig_w, orig_h)
                geometries = compute_geometry_batch(tracks, motion_st, orig_w, orig_h)

                predictions = self.predictor.predict_batch(geometries, tracks, f_obj.frame_id)
                risk_state = self.engine.update(predictions, fallback_active=motion_st.fallback_active, timestamp=ts)
                cmd = self.policy.select(risk_state, timestamp=ts)

                # Measure actual FPS
                t_end = time.monotonic()
                fps_instant = 1.0 / max(0.001, t_end - self.last_time)
                self.last_time = t_end
                self.fps_history.append(fps_instant)
                if len(self.fps_history) > 15:
                    self.fps_history.pop(0)
                mean_fps = sum(self.fps_history) / len(self.fps_history)

                # Determine dynamic window size to eliminate gray margins when maximized/resized
                target_w, target_h = 1280, 720
                try:
                    rect = cv2.getWindowImageRect(win_name)
                    if rect is not None and len(rect) == 4 and rect[2] > 320 and rect[3] > 240:
                        target_w, target_h = int(rect[2]), int(rect[3])
                except Exception:
                    pass

                # Render Visual AR Overlay at crisp target resolution
                rendered = self.render_overlay(
                    img=img,
                    tracks=tracks,
                    predictions=predictions,
                    risk=risk_state,
                    cmd=cmd,
                    motion=motion_st,
                    fps=mean_fps,
                    frame_id=f_obj.frame_id,
                    target_w=target_w,
                    target_h=target_h,
                )
                cv2.imshow(win_name, rendered)

                # Key Handling
                key = cv2.waitKey(1) & 0xFF
                if self.handle_key(key):
                    break

        finally:
            self.frame_src.stop()
            self.imu.stop()
            cv2.destroyAllWindows()
            print("\n[*] Camera Prediction Engine closed cleanly.")

    def handle_key(self, key: int) -> bool:
        if key in (ord('q'), ord('Q'), 27):
            return True
        elif key == ord(' '):
            self.paused = not self.paused
            print(f"[*] {'PAUSED' if self.paused else 'RESUMED'}")
        elif key in (ord('f'), ord('F')):
            self.is_fullscreen = not self.is_fullscreen
            if self.is_fullscreen:
                cv2.setWindowProperty(self.win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                print("[*] Fullscreen: ON")
            else:
                cv2.setWindowProperty(self.win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(self.win_name, 1280, 720)
                print("[*] Fullscreen: OFF (1280x720)")
        elif key in (ord('h'), ord('H')):
            self.show_hud = not self.show_hud
            print(f"[*] HUD Overlay: {'ON' if self.show_hud else 'OFF'}")
        elif key in (ord('t'), ord('T')):
            self.show_telemetry = not self.show_telemetry
            print(f"[*] Telemetry Panel: {'ON' if self.show_telemetry else 'OFF'}")
        elif chr(key) in BENCHMARK_SCENES:
            title, path = BENCHMARK_SCENES[chr(key)]
            if path.exists():
                self.switch_source(str(path), title)
            else:
                print(f"[!] Fixture video not found at: {path}")
        elif key in (ord('c'), ord('C')):
            self.switch_source(self.primary_source, "Live Camera Source")
        return False

    def render_overlay(
        self,
        img: np.ndarray,
        tracks: List[Track],
        predictions: List[Prediction],
        risk: RiskState,
        cmd: HapticCommand,
        motion: Any,
        fps: float,
        frame_id: int,
        target_w: int = 1280,
        target_h: int = 720,
    ) -> np.ndarray:
        orig_h, orig_w = img.shape[:2]
        
        # 1. Strict Aspect Ratio Preservation (Zero Stretching)
        top_bar_h = 44
        bot_bar_h = 44
        avail_w = target_w
        avail_h = max(100, target_h - top_bar_h - bot_bar_h)

        scale = min(avail_w / float(orig_w), avail_h / float(orig_h))
        vw = int(orig_w * scale)
        vh = int(orig_h * scale)
        ox = (target_w - vw) // 2
        oy = top_bar_h + (avail_h - vh) // 2

        # Base Studio Canvas
        canvas = np.full((target_h, target_w, 3), (16, 18, 22), dtype=np.uint8)

        # Place Un-stretched Camera Frame
        cam_resized = cv2.resize(img, (vw, vh), interpolation=cv2.INTER_LINEAR)
        canvas[oy:oy + vh, ox:ox + vw] = cam_resized

        # Subtle frame border
        cv2.rectangle(canvas, (ox, oy), (ox + vw, oy + vh), (50, 54, 64), 1)

        # 2. Ground Perspective Corridors (Clipped strictly within camera viewport)
        if self.show_hud:
            overlay = canvas.copy()
            vanish_y = oy + int(vh * 0.54)
            vanish_x = ox + int(vw * 0.50)

            # Center Corridor
            c_pts = np.array([
                [vanish_x - int(vw * 0.035), vanish_y],
                [vanish_x + int(vw * 0.035), vanish_y],
                [ox + int(vw * 0.67), oy + vh],
                [ox + int(vw * 0.33), oy + vh]
            ], np.int32)
            c_risk = risk.corridor_risks.get("center", 0.0)
            c_color = (30, 30, 220) if c_risk > 0.55 else (40, 180, 50)
            cv2.fillPoly(overlay, [c_pts], c_color)

            # Left Corridor
            l_pts = np.array([
                [vanish_x - int(vw * 0.10), vanish_y],
                [vanish_x - int(vw * 0.035), vanish_y],
                [ox + int(vw * 0.33), oy + vh],
                [ox + int(vw * 0.05), oy + vh]
            ], np.int32)
            l_risk = risk.corridor_risks.get("left", 0.0)
            l_color = (30, 30, 220) if l_risk > 0.55 else (40, 180, 50)
            cv2.fillPoly(overlay, [l_pts], l_color)

            # Right Corridor
            r_pts = np.array([
                [vanish_x + int(vw * 0.035), vanish_y],
                [vanish_x + int(vw * 0.10), vanish_y],
                [ox + int(vw * 0.95), oy + vh],
                [ox + int(vw * 0.67), oy + vh]
            ], np.int32)
            r_risk = risk.corridor_risks.get("right", 0.0)
            r_color = (30, 30, 220) if r_risk > 0.55 else (40, 180, 50)
            cv2.fillPoly(overlay, [r_pts], r_color)

            # Blend corridor fill
            cv2.addWeighted(overlay, 0.20, canvas, 0.80, 0, canvas)

            # Draw crisp corridor separator lines
            cv2.polylines(canvas, [c_pts], isClosed=False, color=(210, 230, 210), thickness=1, lineType=cv2.LINE_AA)
            cv2.polylines(canvas, [l_pts], isClosed=False, color=(210, 230, 210), thickness=1, lineType=cv2.LINE_AA)
            cv2.polylines(canvas, [r_pts], isClosed=False, color=(210, 230, 210), thickness=1, lineType=cv2.LINE_AA)

            # Corridor Risk Pills inside camera viewport
            badge_y = oy + 22
            def draw_pill(text: str, cx: int, cy: int, score: float):
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
                pw, ph = tw + 16, th + 8
                bx1, by1 = cx - pw // 2, cy - ph // 2
                bx2, by2 = bx1 + pw, by1 + ph
                bg = (20, 20, 220) if score > 0.55 else (20, 24, 20)
                cv2.rectangle(canvas, (bx1, by1), (bx2, by2), bg, -1)
                cv2.rectangle(canvas, (bx1, by1), (bx2, by2), (80, 85, 95), 1)
                cv2.putText(canvas, text, (bx1 + 8, by2 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (240, 240, 240), 1, cv2.LINE_AA)

            draw_pill(f"LEFT: {l_risk:.2f}", ox + int(vw * 0.19), badge_y, l_risk)
            draw_pill(f"CENTER: {c_risk:.2f}", ox + int(vw * 0.50), badge_y, c_risk)
            draw_pill(f"RIGHT: {r_risk:.2f}", ox + int(vw * 0.81), badge_y, r_risk)

        # 3. Tracks, Precision Bounding Boxes & Kinematic Vectors
        pred_map = {p.track_id: p for p in predictions}

        for t in tracks:
            if not t.bbox_history:
                continue
            rx1, ry1, rx2, ry2 = t.bbox_history[-1]
            x1 = int(ox + np.clip(rx1 * scale, 0, vw - 1))
            y1 = int(oy + np.clip(ry1 * scale, 0, vh - 1))
            x2 = int(ox + np.clip(rx2 * scale, 0, vw - 1))
            y2 = int(oy + np.clip(ry2 * scale, 0, vh - 1))

            pred = pred_map.get(t.track_id)
            is_intersect = bool(pred and pred.intersection_flag)
            ttc = pred.ttc_s if pred else None
            cpa = pred.cpa_normalized if pred else None
            prox_risk = getattr(pred, "proximity_risk", 0.0) if pred else 0.0
            exp_rate = getattr(pred, "expansion_rate", 0.0) if pred else 0.0

            # Color scheme: Red (Threat/Proximity), Amber (Caution), Emerald (Safe)
            if is_intersect or prox_risk > 0.40 or (pred and getattr(pred, 'is_threat', False)):
                box_color = (30, 30, 235)      # Red
            elif (cpa is not None and cpa < 0.25) or prox_risk > 0.20 or exp_rate > 0.15:
                box_color = (0, 145, 255)      # Amber
            else:
                box_color = (0, 210, 120)      # Emerald

            # Modern tech corner brackets
            cv2.rectangle(canvas, (x1, y1), (x2, y2), box_color, 1, cv2.LINE_AA)
            b_len = min(18, max(5, int(min(x2 - x1, y2 - y1) / 4)))
            cv2.line(canvas, (x1, y1), (x1 + b_len, y1), box_color, 3, cv2.LINE_AA)
            cv2.line(canvas, (x1, y1), (x1, y1 + b_len), box_color, 3, cv2.LINE_AA)
            cv2.line(canvas, (x2, y1), (x2 - b_len, y1), box_color, 3, cv2.LINE_AA)
            cv2.line(canvas, (x2, y1), (x2, y1 + b_len), box_color, 3, cv2.LINE_AA)
            cv2.line(canvas, (x1, y2), (x1 + b_len, y2), box_color, 3, cv2.LINE_AA)
            cv2.line(canvas, (x1, y2), (x1, y2 - b_len), box_color, 3, cv2.LINE_AA)
            cv2.line(canvas, (x2, y2), (x2 - b_len, y2), box_color, 3, cv2.LINE_AA)
            cv2.line(canvas, (x2, y2), (x2, y2 - b_len), box_color, 3, cv2.LINE_AA)

            # Velocity Vector Arrow from Box Center
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            vx, vy = getattr(t, "estimated_image_velocity", (0.0, 0.0))
            if abs(vx) > 0.4 or abs(vy) > 0.4:
                end_x = int(cx + np.clip(vx * scale * 0.35, -70, 70))
                end_y = int(cy + np.clip(vy * scale * 0.35, -70, 70))
                cv2.arrowedLine(canvas, (cx, cy), (end_x, end_y), (0, 240, 255), 2, tipLength=0.25, line_type=cv2.LINE_AA)
                cv2.circle(canvas, (cx, cy), 3, (0, 240, 255), -1, cv2.LINE_AA)

            # Structured Badge Label
            ttc_str = f"TTC:{ttc:.1f}s" if ttc is not None else "TTC:--"
            cpa_str = f"CPA:{cpa:.2f}" if cpa is not None else ""
            hazard_tag = ""
            if is_intersect:
                hazard_tag = " !COLLISION!"
            elif prox_risk > 0.35:
                hazard_tag = " !PROXIMITY!"
            elif exp_rate > 0.20:
                hazard_tag = " !LOOMING!"

            label = f"#{t.track_id} {t.class_name.upper()} | {ttc_str} | {cpa_str}{hazard_tag}".strip(" |")

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
            lbl_y = y1 - 6 if y1 - 6 > oy + 14 else y2 + th + 10
            cv2.rectangle(canvas, (x1, lbl_y - th - 5), (x1 + tw + 8, lbl_y + 4), (18, 18, 22), -1)
            cv2.rectangle(canvas, (x1, lbl_y - th - 5), (x1 + tw + 8, lbl_y + 4), box_color, 1)
            cv2.putText(canvas, label, (x1 + 4, lbl_y - 1), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA)

        # 4. Top Telemetry Header Bar
        cv2.rectangle(canvas, (0, 0), (target_w, top_bar_h), (18, 20, 24), -1)
        cv2.line(canvas, (0, top_bar_h), (target_w, top_bar_h), (45, 48, 56), 1)

        state = risk.state
        state_colors = {
            "SAFE": (35, 170, 60),
            "CAUTION": (0, 180, 230),
            "WARNING": (0, 130, 245),
            "CRITICAL": (25, 30, 235),
            "DEGRADED": (180, 50, 180),
        }
        st_color = state_colors.get(state, (120, 120, 120))

        # State Pill Badge
        state_label = f" {state} "
        (stw, sth), _ = cv2.getTextSize(state_label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(canvas, (14, 7), (14 + stw + 10, 37), st_color, -1)
        cv2.putText(canvas, state_label, (18, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

        # Risk Score + Visual Meter Bar
        meter_x = 24 + stw + 14
        meter_w = 110
        meter_h = 12
        meter_y = 16
        risk_pct = float(np.clip(risk.global_risk, 0.0, 1.0))

        risk_txt = f"RISK: {risk.global_risk:.2f}"
        cv2.putText(canvas, risk_txt, (meter_x, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 230), 1, cv2.LINE_AA)
        
        (rtw, _), _ = cv2.getTextSize(risk_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
        bar_x1 = meter_x + rtw + 10
        cv2.rectangle(canvas, (bar_x1, meter_y), (bar_x1 + meter_w, meter_y + meter_h), (35, 38, 46), -1)
        fill_w = int(meter_w * risk_pct)
        if fill_w > 0:
            fill_color = (35, 170, 60) if risk_pct < 0.35 else ((0, 140, 240) if risk_pct < 0.65 else (30, 30, 230))
            cv2.rectangle(canvas, (bar_x1, meter_y), (bar_x1 + fill_w, meter_y + meter_h), fill_color, -1)
        cv2.rectangle(canvas, (bar_x1, meter_y), (bar_x1 + meter_w, meter_y + meter_h), (75, 80, 90), 1)

        # System Confidence
        conf_txt = f"CONF: {risk.confidence * 100:.0f}%"
        cv2.putText(canvas, conf_txt, (bar_x1 + meter_w + 16, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (180, 185, 195), 1, cv2.LINE_AA)

        # Right side: FPS & Frame ID
        right_info = f"FPS: {fps:.1f} | Frame #{frame_id} | Hotkeys: [F] Fullscreen  [H] HUD  [T] Telemetry  [1-5] Scenes"
        (rw, _), _ = cv2.getTextSize(right_info, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        cv2.putText(canvas, right_info, (max(target_w - rw - 14, bar_x1 + meter_w + 140), 26), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 205, 215), 1, cv2.LINE_AA)

        # 5. Bottom Directional Guidance Banner (Clean ASCII arrows)
        cv2.rectangle(canvas, (0, target_h - bot_bar_h), (target_w, target_h), (18, 20, 24), -1)
        cv2.line(canvas, (0, target_h - bot_bar_h), (target_w, target_h - bot_bar_h), (45, 48, 56), 1)

        if cmd.direction == "LEFT":
            dir_symbol = "<< MOVE LEFT"
            dir_color = (0, 180, 255)
        elif cmd.direction == "RIGHT":
            dir_symbol = ">> MOVE RIGHT"
            dir_color = (0, 180, 255)
        elif cmd.direction == "STOP":
            dir_symbol = "|| STOP IMMINENT ||"
            dir_color = (35, 35, 235)
        else:
            dir_symbol = "^^ PATH CLEAR ^^"
            dir_color = (40, 190, 70)

        guidance_lead = f"GUIDANCE: [{dir_symbol}]"
        cv2.putText(canvas, guidance_lead, (16, target_h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.50, dir_color, 2, cv2.LINE_AA)

        (gw, _), _ = cv2.getTextSize(guidance_lead, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 2)
        haptic_txt = (
            f"  |  HAPTIC: {cmd.pattern_id} (Urgency {cmd.urgency}/5, {cmd.duration_ms}ms)"
            f"  |  REASONS: {', '.join(risk.reason_codes[:2]) if risk.reason_codes else 'clear path'}"
        )
        cv2.putText(canvas, haptic_txt, (16 + gw, target_h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (210, 215, 225), 1, cv2.LINE_AA)

        # 6. Rich Information Sidebar Panels (Utilizing pillarbox margins or floating card)
        if self.show_telemetry:
            # Check if there is comfortable space on sides (pillarbox margin >= 200px)
            if ox >= 200:
                # LEFT SIDEBAR: Motion & Sensors
                lw = ox - 16
                lx1, ly1 = 12, top_bar_h + 12
                lx2, ly2 = lx1 + lw, target_h - bot_bar_h - 12
                cv2.rectangle(canvas, (lx1, ly1), (lx2, ly2), (22, 25, 32), -1)
                cv2.rectangle(canvas, (lx1, ly1), (lx2, ly2), (55, 60, 72), 1)

                cv2.putText(canvas, "MOTION & SENSORS", (lx1 + 10, ly1 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 220, 255), 1, cv2.LINE_AA)
                cv2.line(canvas, (lx1 + 10, ly1 + 28), (lx2 - 10, ly1 + 28), (45, 50, 60), 1)

                fq = getattr(motion, 'flow_quality', 0.0)
                foe_c = getattr(motion, 'foe_confidence', 0.0)
                calib = getattr(self.predictor, "calibrator", None)
                l_thresh = calib.current_threshold if calib else 0.05
                max_exp = max([getattr(p, "expansion_rate", 0.0) for p in predictions], default=0.0)
                left_lines = [
                    f"Resolution: {orig_w}x{orig_h}",
                    f"Tracker: {self.tracker_type.upper()}",
                    f"Active Tracks: {len(tracks)}",
                    f"Predictions: {len(predictions)}",
                    f"Ego-Fallback: {motion.fallback_active}",
                    f"Flow Quality: {fq:.2f}",
                    f"FOE Conf: {foe_c:.2f}",
                    f"Adapt Thresh: {l_thresh:.2f}/s",
                    f"Max Expansion: {max_exp:+.2f}/s",
                ]
                for i, line in enumerate(left_lines):
                    cv2.putText(canvas, line, (lx1 + 10, ly1 + 46 + i * 19), cv2.FONT_HERSHEY_SIMPLEX, 0.39, (215, 220, 230), 1, cv2.LINE_AA)

                # RIGHT SIDEBAR: Risk & Haptic Decision Engine
                rw = ox - 16
                rx1, ry1 = ox + vw + 12, top_bar_h + 12
                rx2, ry2 = rx1 + rw, target_h - bot_bar_h - 12
                cv2.rectangle(canvas, (rx1, ry1), (rx2, ry2), (22, 25, 32), -1)
                cv2.rectangle(canvas, (rx1, ry1), (rx2, ry2), (55, 60, 72), 1)

                cv2.putText(canvas, "DECISION & RISK ENGINE", (rx1 + 10, ry1 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 220, 255), 1, cv2.LINE_AA)
                cv2.line(canvas, (rx1 + 10, ry1 + 28), (rx2 - 10, ry1 + 28), (45, 50, 60), 1)

                max_prox = max([getattr(p, "proximity_risk", 0.0) for p in predictions], default=0.0)
                right_lines = [
                    f"State: {risk.state}",
                    f"Global Risk: {risk.global_risk:.2f}",
                    f"Proximity Risk: {max_prox:.2f}",
                    f"Confidence: {risk.confidence*100:.0f}%",
                    f"Corridor Left: {l_risk:.2f}",
                    f"Corridor Center: {c_risk:.2f}",
                    f"Corridor Right: {r_risk:.2f}",
                    f"Guidance: {cmd.direction}",
                    f"Pattern: {cmd.pattern_id}",
                    f"Urgency: {cmd.urgency}/5 ({cmd.duration_ms}ms)",
                ]
                for i, line in enumerate(right_lines):
                    cv2.putText(canvas, line, (rx1 + 10, ry1 + 46 + i * 19), cv2.FONT_HERSHEY_SIMPLEX, 0.39, (215, 220, 230), 1, cv2.LINE_AA)

            else:
                # Floating overlay card when video fills entire width
                panel_w = 260
                panel_h = 190
                px1 = target_w - panel_w - 14
                py1 = top_bar_h + 14
                px2 = px1 + panel_w
                py2 = py1 + panel_h

                sub = canvas[py1:py2, px1:px2]
                dark = np.zeros_like(sub)
                cv2.addWeighted(dark, 0.80, sub, 0.20, 0, sub)
                canvas[py1:py2, px1:px2] = sub
                cv2.rectangle(canvas, (px1, py1), (px2, py2), (70, 75, 85), 1)

                cv2.putText(canvas, "PREDICTION ENGINE TELEMETRY", (px1 + 10, py1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 220, 255), 1, cv2.LINE_AA)
                cv2.line(canvas, (px1 + 10, py1 + 26), (px2 - 10, py1 + 26), (60, 65, 75), 1)

                lines = [
                    f"Resolution: {orig_w}x{orig_h}",
                    f"Active Tracks: {len(tracks)}",
                    f"Predictions: {len(predictions)}",
                    f"Ego-motion Fallback: {motion.fallback_active}",
                    f"Flow Quality: {getattr(motion, 'flow_quality', 0.0):.2f}",
                    f"FOE Confidence: {getattr(motion, 'foe_confidence', 0.0):.2f}",
                    f"Tracker: {self.tracker_type.upper()}",
                    f"State: {risk.state} (Risk: {risk.global_risk:.2f})",
                ]
                for i, line in enumerate(lines):
                    cv2.putText(canvas, line, (px1 + 10, py1 + 45 + i * 16), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 225, 230), 1, cv2.LINE_AA)

        return canvas


def main():
    args = parse_args()

    # Determine camera source
    if args.scene:
        title, path = BENCHMARK_SCENES[args.scene]
        source = str(path)
        print(f"[*] Starting directly with Benchmark {title}")
    else:
        source, origin = resolve_camera_source(cli_source=args.source)
        print(f"[*] Camera source resolved from: {origin}")

    viewer = PredictionViewer(
        source_str=source,
        target_fps=args.fps,
        det_conf=args.conf,
        tracker_type=args.tracker,
    )
    viewer.run()


if __name__ == "__main__":
    main()
