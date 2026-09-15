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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
