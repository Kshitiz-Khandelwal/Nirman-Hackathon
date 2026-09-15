"""Shared data contracts for HMI and Output/Safety-Net Chain (M10, M11, M12).

Modules:
- M10: ArduinoStatus
- M11: TelemetryMessage
- M12: SessionRecord
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ArduinoStatus:
    """M10 status, polled or pushed from the firmware side."""
    connected: bool = False
    last_ack_t: Optional[float] = None        # time.monotonic() of last ACK received
    last_command_sent: Optional[str] = None   # pattern_id of the last command actually written to serial
    motor_test_result: Optional[Dict[str, str]] = None  # per-motor pass/fail from startup self-test

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TelemetryMessage:
    """M11 output — one JSON message per frame, sent to the phone over WebSocket."""
    session_id: str
    ts: float
    frame_id: int
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    risk_state: Dict[str, Any] = field(default_factory=dict)
    haptic: Dict[str, Any] = field(default_factory=dict)
    pipeline_health: Dict[str, str] = field(default_factory=lambda: {
        "camera": "OK",
        "imu": "OK",
        "arduino": "OK",
    })
    frame_width: int = 640
    frame_height: int = 480

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_track_telemetry(tracks: List[Any], pred_map: Dict[int, Any]) -> List[Dict[str, Any]]:
    """Builds the full per-track telemetry payload — every field the dashboard reads.
    
    Includes:
    - track_id, class_name, bbox ([x1, y1, x2, y2]), track_confidence
    - cpa, ttc_s, intersect (bool), pred_conf, bearing
    - relative_velocity: (vx, vy) image velocity in px/sec
    """
    result = []
    for t in tracks:
        pred = pred_map.get(t.track_id)
        result.append({
            "track_id": t.track_id,
            "class_name": t.class_name,
            "bbox": list(t.bbox_history[-1]) if getattr(t, "bbox_history", None) else None,
            "track_confidence": getattr(t, "track_confidence", 0.0),
            "cpa": getattr(pred, "cpa_normalized", None),
            "ttc_s": getattr(pred, "ttc_s", None),
            "intersect": bool(getattr(pred, "intersection_flag", False)),
            "pred_conf": getattr(pred, "prediction_confidence", None),
            "bearing": getattr(pred, "bearing", None),
            "relative_velocity": getattr(t, "estimated_image_velocity", (0.0, 0.0)),
        })
    return result


@dataclass
class SessionRecord:
    """M12 — one line in the JSONL session log."""
    session_id: str
    record_type: str  # "header" | "frame" | "detection" | "track" | "motion" | "prediction" | "risk" | "haptic" | "imu"
    ts: float
    frame_id: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
