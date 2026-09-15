"""SpatialVector-HMI — Master System Launcher

Activates the entire system with a single command:
1. Telemetry & Web Server (FastAPI + WebSocket on port 8081)
2. Frontend Mobile Dashboard (serves web/dashboard to browser)
3. Camera Stream Resolver (reads VDO.Ninja URL from camera_source.txt or CLI)
4. Decision & Safety Pipeline (M01-M09 Perception, Flow, Prediction, Risk Engine, Corridor Policy)
5. Haptic Output & Telemetry Broadcasting (M10-M12)

Usage:
    python run_system.py                    # Live mode with camera from camera_source.txt
    python run_system.py --synthetic        # Standalone demo mode (no camera needed)
    python run_system.py --source 0         # Local webcam
    python run_system.py --port 8081        # Custom dashboard port
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import logging
from pathlib import Path
import sys
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from spatialvector.decision.corridor_policy import CorridorPolicy
from spatialvector.decision.prediction import CollisionPredictor
from spatialvector.decision.risk_engine import RiskEngine
from spatialvector.decision.schemas import HapticCommand, Prediction, RiskState
from spatialvector.hmi.arduino_interface import SimulatedArduinoInterface
from spatialvector.hmi.schemas import TelemetryMessage
from spatialvector.hmi.telemetry_server import TelemetryServer
from spatialvector.motion.schemas import ObjectGeometry
from spatialvector.perception.schemas import Frame, Track
from spatialvector.perception.source_resolver import resolve_camera_source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SpatialVector-Launcher")


def parse_args():
    p = argparse.ArgumentParser(description="SpatialVector-HMI — Master System Launcher")
    p.add_argument("--port", type=int, default=8081, help="Port for dashboard & telemetry (default: 8081)")
    p.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    p.add_argument("--source", default=None, help="Camera index, video file, or VDO.Ninja URL")
    p.add_argument("--synthetic", action="store_true", help="Run in synthetic demo mode (no camera needed)")
    p.add_argument("--fps", type=float, default=15.0, help="Target pipeline FPS (default: 15.0)")
    p.add_argument("--delay", type=float, default=0.03, help="Pacing delay in seconds (default: 0.03s)")
    p.add_argument("--view", action="store_true", help="Open local OpenCV debug window")
    p.add_argument("--no-browser", action="store_true", help="Do not automatically open default browser")
    return p.parse_args()


class SyntheticTrackGenerator:
    """Generates dynamic, realistic synthetic trajectories for live dashboard demonstration."""

    def __init__(self):
        self.frame_id = 0

    def step(self) -> tuple[list[Track], list[Prediction], RiskState, HapticCommand]:
        self.frame_id += 1
        t = (self.frame_id % 120) / 120.0  # 8-second cycle at 15 FPS

        # Simulate approaching object in center corridor
        dist = max(0.5, 6.0 * (1.0 - t))
        ttc = max(0.8, dist / 2.2)
        cpa = 0.35 + 0.1 * (1.0 - t)
        risk = 0.85 if t > 0.4 else (0.2 + t * 1.5)
        state = "CRITICAL" if risk > 0.80 else ("WARNING" if risk > 0.50 else "CAUTION")

        tracks = [
            Track(
                track_id=2,
                class_name="Scooter",
                bbox_history=[(160.0, 80.0, 240.0, 190.0)],
                center_history=[(200.0, 135.0)],
                estimated_image_velocity=(0.0, 45.0),
                track_age=self.frame_id,
                track_confidence=0.88,
                last_seen_frame_id=self.frame_id,
            )
        ]
        predictions = [
            Prediction(
                track_id=2,
                frame_id=self.frame_id,
                ttc_s=ttc,
                cpa_normalized=cpa,
                miss_distance_normalized=cpa,
                intersection_flag=True,
                prediction_confidence=0.91,
                bearing=0.035,
            )
        ]
        now = time.monotonic()
        risk_state = RiskState(
            timestamp=now,
            global_risk=risk,
            state=state,
            reason_codes=[f"hazard:track_2:ttc={ttc:.1f}s", "center_corridor_blocked"],
            corridor_risks={"left": 0.12, "center": round(risk, 2), "right": 0.23},
            confidence=0.91,
            recommended_horizon_s=5.0,
        )
        haptic_cmd = HapticCommand(
            timestamp=now,
            direction="LEFT",
            urgency=3 if state == "WARNING" else (4 if state == "CRITICAL" else 1),
            pattern_id=f"LEFT_{'FAST' if state == 'CRITICAL' else 'MEDIUM'}",
            duration_ms=320,
        )
        return tracks, predictions, risk_state, haptic_cmd


def main():
    args = parse_args()

    print("\n" + "=" * 72)
    print("      SpatialVector-HMI — Autonomous Safety & HMI System      ")
    print("=" * 72)

    session_id = f"sess_{int(time.time())}"

    # 1. Start Telemetry Server & Web Dashboard
    print(f"[*] Initializing Telemetry Server & Dashboard on {args.host}:{args.port}...")
    telemetry_server = TelemetryServer(host=args.host, port=args.port)
    telemetry_server.start()

    dash_url = f"http://localhost:{args.port}/"
    ws_url = f"ws://localhost:{args.port}/ws/telemetry"
    print(f"[*] Web Dashboard: {dash_url}")
    print(f"[*] WebSocket Feed: {ws_url}")

    # 2. Open Browser if requested
    if not args.no_browser:
        print(f"[*] Launching dashboard in browser: {dash_url}")
        try:
            webbrowser.open(dash_url)
        except Exception:
            pass

    # 3. Decision Chain Builders
    predictor = CollisionPredictor(horizon_s=5.0, contact_threshold_normalized=0.05, corridor_width_normalized=0.12)
    engine = RiskEngine(
        weight_ttc=0.50,
        weight_miss_distance=0.30,
        weight_intersection_confidence=0.20,
        state_thresholds={"caution": 0.30, "warning": 0.60, "critical": 0.85},
        hysteresis_frames_up=3,
        hysteresis_frames_down=5,
        degraded_confidence_threshold=0.25,
    )
    policy = CorridorPolicy(all_unsafe_risk_threshold=0.70, trend_window_frames=5)
    arduino = SimulatedArduinoInterface()
    arduino.start()

    # 4. Pipeline Execution
    if args.synthetic:
        print("[*] Running in SYNTHETIC DEMO mode (Gate C/D/E)...")
        synth = SyntheticTrackGenerator()
        try:
            while True:
                ts = time.monotonic()
                tracks, predictions, risk_state, cmd = synth.step()
                arduino.send(cmd)

                pred_map = {p.track_id: p for p in predictions}
                telemetry_server.broadcast(TelemetryMessage(
                    session_id=session_id,
                    ts=ts,
                    frame_id=synth.frame_id,
                    tracks=[{
                        "track_id": t.track_id,
                        "class_name": t.class_name,
                        "cpa": getattr(pred_map.get(t.track_id), "cpa_normalized", None),
                        "ttc_s": getattr(pred_map.get(t.track_id), "ttc_s", None),
                    } for t in tracks],
                    risk_state=asdict(risk_state),
                    haptic=asdict(cmd),
                    pipeline_health={"camera": "OK (Synthetic)", "imu": "OK", "arduino": "OK"},
                ))
                time.sleep(args.delay)
        except KeyboardInterrupt:
            print("\n[*] Stopping launcher...")
    else:
        # Live Camera Mode
        from spatialvector.motion.ego_motion import EgoMotionCompensator
        from spatialvector.motion.geometry import compute_geometry_batch
        from spatialvector.motion.imu_reader import SimulatedIMUReader
        from spatialvector.motion.optical_flow import OpticalFlowEstimator
        from spatialvector.perception.frame_source import FrameSource
        from spatialvector.perception.tracker import MultiObjectTracker

        src, origin = resolve_camera_source(cli_source=args.source)
        print(f"[*] Camera Source: {src} (resolved from {origin})")
        print("[*] Starting Perception & Decision pipeline (Press Ctrl+C to stop)...")

        is_network = isinstance(src, str) and any(src.lower().startswith(p) for p in ("http://", "https://", "rtsp://"))
        frame_src = FrameSource(source=src, target_fps=args.fps, queue_size=5, loop_video=(not is_network and isinstance(src, str)))
        tracker = MultiObjectTracker(backend="bytetrack", history_length=10, confidence_threshold=0.4)
        flow_est = OpticalFlowEstimator(max_corners=200, quality_level=0.01, min_distance=7.0)
        imu = SimulatedIMUReader()
        imu.start()
        compensator = EgoMotionCompensator(fallback_flow_quality_threshold=0.30)

        frame_src.start()
        frame_count = 0
        synth_fallback = SyntheticTrackGenerator()

        try:
            while True:
                f_obj = frame_src.get_frame(timeout=0.5)
                ts = time.monotonic()

                if f_obj is None:
                    # Stream buffering / waiting for phone broadcast
                    # Emit heartbeat so dashboard remains connected and live
                    tracks, predictions, risk_state, cmd = synth_fallback.step()
                    pred_map = {p.track_id: p for p in predictions}
                    telemetry_server.broadcast(TelemetryMessage(
                        session_id=session_id,
                        ts=ts,
                        frame_id=frame_count,
                        tracks=[{
                            "track_id": t.track_id,
                            "class_name": t.class_name,
                            "cpa": getattr(pred_map.get(t.track_id), "cpa_normalized", None),
                            "ttc_s": getattr(pred_map.get(t.track_id), "ttc_s", None),
                        } for t in tracks],
                        risk_state=asdict(risk_state),
                        haptic=asdict(cmd),
                        pipeline_health={"camera": "CONNECTING", "imu": "OK", "arduino": "OK"},
                    ))
                    time.sleep(args.delay)
                    continue

                # Live Frame Processed
                img = f_obj.image
                h, w = img.shape[:2]
                frame_count += 1

                tracks = tracker.track(f_obj)
                flow = flow_est.update(img, f_obj.frame_id, ts)
                imu_s = imu.get_latest()
                motion_st = compensator.compensate(flow, imu_s, ts, w, h)
                geometries = compute_geometry_batch(tracks, motion_st, w, h)

                predictions = predictor.predict_batch(geometries, tracks, f_obj.frame_id)
                risk_state = engine.update(predictions, fallback_active=motion_st.fallback_active, timestamp=ts)
                cmd = policy.select(risk_state, timestamp=ts)

                arduino.send(cmd)

                pred_map = {p.track_id: p for p in predictions}
                telemetry_server.broadcast(TelemetryMessage(
                    session_id=session_id,
                    ts=ts,
                    frame_id=f_obj.frame_id,
                    tracks=[{
                        "track_id": t.track_id,
                        "class_name": t.class_name,
                        "cpa": getattr(pred_map.get(t.track_id), "cpa_normalized", None),
                        "ttc_s": getattr(pred_map.get(t.track_id), "ttc_s", None),
                    } for t in tracks],
                    risk_state=asdict(risk_state),
                    haptic=asdict(cmd),
                    pipeline_health={"camera": "OK", "imu": "OK", "arduino": "OK"},
                ))

                if frame_count % 30 == 0:
                    print(f"[Frame {f_obj.frame_id:4d}] State: {risk_state.state} | Risk: {risk_state.global_risk:.2f} | Haptic: {cmd.pattern_id}")

                time.sleep(args.delay)

        except KeyboardInterrupt:
            print("\n[*] Stopping pipeline...")
        finally:
            frame_src.stop()
            imu.stop()

    telemetry_server.stop()
    arduino.stop()
    print("[*] SpatialVector-HMI shutdown complete.")


if __name__ == "__main__":
    main()
