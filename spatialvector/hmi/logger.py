"""M12 — Session Logger (Safety-Net Recording Harness).

Records complete, synchronized timelines for every module's output during
live or synthetic runs in structured JSONL format.

Rules:
1. One session_id, synchronized timestamps using time.monotonic().
2. Structured header record with schema_version: 1.
3. Records enough state to reproduce decisions offline deterministically.
4. Non-blocking buffered writes so disk I/O does not degrade frame rates.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import logging
from pathlib import Path
import queue
import threading
import time
from typing import Any, Dict, Optional, Union

from spatialvector.hmi.schemas import SessionRecord

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _sanitize_payload(obj: Any) -> Any:
    """Recursively converts dataclasses, numpy types, and tuples into serializable types."""
    if is_dataclass(obj):
        return _sanitize_payload(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _sanitize_payload(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_payload(x) for x in obj]
    if hasattr(obj, "item"):  # numpy scalars
        return obj.item()
    if hasattr(obj, "tolist"):  # numpy arrays
        return obj.tolist()
    return obj


class SessionLogger:
    """Buffered, non-blocking session recorder writing JSONL records."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        base_dir: Union[str, Path] = "sessions",
        config_snapshot: Optional[Dict[str, Any]] = None,
        buffer_size: int = 1000,
    ):
        self.session_id = session_id or f"session_{int(time.time())}"
        self.base_dir = Path(base_dir)
        self.session_dir = self.base_dir / self.session_id
        self.session_file = self.session_dir / "session.jsonl"
        self.schema_version = SCHEMA_VERSION

        self.session_dir.mkdir(parents=True, exist_ok=True)

        self._queue: queue.Queue[Optional[str]] = queue.Queue(maxsize=buffer_size)
        self._stop_event = threading.Event()
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True, name="SessionWriter")
        self._writer_thread.start()

        # Write session header
        header_payload = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "created_at": time.time(),
            "created_monotonic": time.monotonic(),
            "config": _sanitize_payload(config_snapshot or {}),
        }
        self.log(SessionRecord(
            session_id=self.session_id,
            record_type="header",
            ts=time.monotonic(),
            frame_id=None,
            payload=header_payload,
        ))

        logger.info(f"[M12] SessionLogger recording to {self.session_file}")

    def log(self, record: SessionRecord) -> None:
        """Enqueues a SessionRecord for non-blocking write."""
        if self._stop_event.is_set():
            return
        payload_sanitized = _sanitize_payload(record.payload)
        record_dict = {
            "session_id": record.session_id,
            "record_type": record.record_type,
            "ts": record.ts,
            "frame_id": record.frame_id,
            "payload": payload_sanitized,
        }
        json_line = json.dumps(record_dict) + "\n"
        try:
            self._queue.put_nowait(json_line)
        except queue.Full:
            logger.warning("[M12] Logger buffer full — dropping record")

    def log_event(
        self,
        record_type: str,
        payload: Any,
        frame_id: Optional[int] = None,
        ts: Optional[float] = None,
    ) -> None:
        """Convenience method for logging arbitrary module outputs."""
        self.log(SessionRecord(
            session_id=self.session_id,
            record_type=record_type,
            ts=ts if ts is not None else time.monotonic(),
            frame_id=frame_id,
            payload=_sanitize_payload(payload),
        ))

    def close(self) -> None:
        """Flushes remaining records and closes file cleanly."""
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)  # Sentinel to terminate writer loop
        except queue.Full:
            pass
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)
        logger.info(f"[M12] SessionLogger closed. File size: {self.session_file.stat().st_size if self.session_file.exists() else 0} bytes")

    def _writer_loop(self):
        with open(self.session_file, "a", encoding="utf-8") as f:
            while True:
                try:
                    item = self._queue.get(timeout=0.2)
                except queue.Empty:
                    if self._stop_event.is_set():
                        break
                    continue

                if item is None:
                    break

                f.write(item)
                f.flush()

            # Drain any remaining records before exiting
            while not self._queue.empty():
                try:
                    item = self._queue.get_nowait()
                    if item:
                        f.write(item)
                except queue.Empty:
                    break
            f.flush()
