import logging
import time
from typing import Optional, Union
import numpy as np

from .schemas import Frame, Detection, Track

logger = logging.getLogger(__name__)


class MultiObjectTracker:
    """M03 - Multi-Object Tracking.

    Maintains identity persistence over time using ByteTrack or BoT-SORT backend.
    Maintains a rolling history of bounding boxes (N frames) and center positions.
    Computes image-space velocity (pixels/second) via finite differences.
    Monitors track age, track loss, duplicate IDs, and logs ID switch events.
    Enforces strict architectural rule: M03 outputs tracks forward only,
    never triggering haptics, alerts, or collision risk scoring.
    """

    def __init__(
        self,
        backend: str = "bytetrack",  # "bytetrack" or "botsort"
        history_length: int = 10,
        max_missed_frames: int = 15,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = 0.4,
        class_filter: Optional[list[str]] = None,
    ):
        self.backend = backend.lower()
        if self.backend not in ["bytetrack", "botsort"]:
            logger.warning(f"Unknown tracker backend '{backend}', defaulting to 'bytetrack'")
            self.backend = "bytetrack"

        self.history_length = history_length
        self.max_missed_frames = max_missed_frames
        self.confidence_threshold = confidence_threshold
        self.class_filter = [c.lower() for c in class_filter] if class_filter else None
        self.model_path = model_path

        # Internal active track records
        # track_id -> dict with track history, age, last_seen, etc.
        self._tracks: dict[int, dict] = {}
        self.current_frame_id = 0
        self.status = "OK"

        # ID switch detection metrics
        self.id_switch_events: list[dict] = []
        self._last_centers_by_class: dict[str, list[tuple[int, tuple[float, float]]]] = {}

        # Tracking model instance
        self._model = None
        self._load_tracker()

    def _load_tracker(self):
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
            self.status = "OK"
            logger.info(f"Loaded tracker with backend: {self.backend}")
        except Exception as e:
            self.status = "DEGRADED"
            logger.error(f"Failed to initialize tracker: {e}")
            raise e

    def track(
        self,
        frame: Union[Frame, np.ndarray],
        detections: Optional[list[Detection]] = None,
        camera_motion_compensation: Optional[dict] = None,  # Parameter slot for future M05 IMU
    ) -> list[Track]:
        """Update multi-object tracking for the current frame.

        Args:
            frame: Input Frame object or raw numpy image.
            detections: Pre-computed Detection objects from M02 (optional).
            camera_motion_compensation: Optional rotation/motion parameters (reserved for M05).

        Returns:
            list[Track]: Currently active persistent tracks.
        """
        img = frame.image if isinstance(frame, Frame) else frame
        frame_id = frame.frame_id if isinstance(frame, Frame) else self.current_frame_id
        timestamp = frame.t_capture if isinstance(frame, Frame) else time.monotonic()
        self.current_frame_id = frame_id

        tracker_yaml = "bytetrack.yaml" if self.backend == "bytetrack" else "botsort.yaml"

        try:
            results = self._model.track(
                source=img,
                persist=True,
                tracker=tracker_yaml,
                conf=self.confidence_threshold,
                verbose=False,
            )
        except Exception as e:
            logger.error(f"Tracking error on frame {frame_id}: {e}")
            self.status = "DEGRADED"
            return []

        self.status = "OK"
        active_track_ids_this_frame: set[int] = set()
        current_tracks: list[Track] = []

        for r in results:
            boxes = r.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for i in range(len(boxes)):
                # If Ultralytics tracker hasn't assigned an ID yet, skip
                if boxes.id is None:
                    continue

                track_id = int(boxes.id[i].cpu().numpy())
                xyxy = boxes.xyxy[i].cpu().numpy().tolist()
                conf = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())
                cls_name = str(self._model.names.get(cls_id, f"class_{cls_id}"))

                # Apply class filter if specified
                if self.class_filter is not None and cls_name.lower() not in self.class_filter:
                    continue

                bbox_tuple = (float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3]))
                center_x = (bbox_tuple[0] + bbox_tuple[2]) / 2.0
                center_y = (bbox_tuple[1] + bbox_tuple[3]) / 2.0
                center_pt = (center_x, center_y)

                # Check duplicate IDs in the same frame
                if track_id in active_track_ids_this_frame:
                    logger.error(f"DUPLICATE TRACK ID DETECTED in frame {frame_id}: ID {track_id}")
                    assert track_id not in active_track_ids_this_frame, f"Duplicate track ID {track_id} in frame {frame_id}"

                active_track_ids_this_frame.add(track_id)

                # Initialize or update track history
                if track_id not in self._tracks:
                    self._detect_potential_id_switch(frame_id, track_id, cls_name, center_pt)
                    self._tracks[track_id] = {
                        "class_name": cls_name,
                        "bbox_history": [bbox_tuple],
                        "center_history": [center_pt],
                        "timestamps": [timestamp],
                        "track_age": 1,
                        "track_confidence": conf,
                        "last_seen_frame_id": frame_id,
                    }
                else:
                    t_record = self._tracks[track_id]
                    t_record["class_name"] = cls_name
                    t_record["bbox_history"].append(bbox_tuple)
                    t_record["center_history"].append(center_pt)
                    t_record["timestamps"].append(timestamp)
                    t_record["track_age"] += 1
                    t_record["track_confidence"] = conf
                    t_record["last_seen_frame_id"] = frame_id

                    # Enforce max history length
                    if len(t_record["bbox_history"]) > self.history_length:
                        t_record["bbox_history"].pop(0)
                        t_record["center_history"].pop(0)
                        t_record["timestamps"].pop(0)

                # Calculate estimated image velocity (pixels/sec) via finite differences
                t_record = self._tracks[track_id]
                image_velocity = self._compute_velocity(
                    t_record["center_history"], t_record["timestamps"]
                )

                current_tracks.append(
                    Track(
                        track_id=track_id,
                        class_name=cls_name,
                        bbox_history=list(t_record["bbox_history"]),
                        center_history=list(t_record["center_history"]),
                        estimated_image_velocity=image_velocity,
                        track_age=t_record["track_age"],
                        track_confidence=conf,
                        last_seen_frame_id=frame_id,
                    )
                )

        # Evict tracks that have been missed for more than max_missed_frames
        dead_tracks = [
            tid
            for tid, t_data in self._tracks.items()
            if (frame_id - t_data["last_seen_frame_id"]) > self.max_missed_frames
        ]
        for tid in dead_tracks:
            del self._tracks[tid]

        return current_tracks

    def _compute_velocity(
        self, centers: list[tuple[float, float]], timestamps: list[float]
    ) -> tuple[float, float]:
        """Compute finite-difference image velocity in pixels per second."""
        if len(centers) < 2 or len(timestamps) < 2:
            return (0.0, 0.0)

        dt = timestamps[-1] - timestamps[0]
        if dt <= 1e-6:
            return (0.0, 0.0)

        dx = centers[-1][0] - centers[0][0]
        dy = centers[-1][1] - centers[0][1]

        vx = dx / dt
        vy = dy / dt
        return (float(vx), float(vy))

    def _detect_potential_id_switch(
        self, frame_id: int, new_track_id: int, class_name: str, center: tuple[float, float]
    ):
        """Record potential ID switch events when a new track spawns very close to a recently lost track of the same class."""
        recent_candidates = self._last_centers_by_class.get(class_name, [])
        for old_id, old_center in recent_candidates:
            if old_id != new_track_id:
                dist = np.hypot(center[0] - old_center[0], center[1] - old_center[1])
                # If new track starts within 50px of an old track location
                if dist < 50.0:
                    event = {
                        "frame_id": frame_id,
                        "old_track_id": old_id,
                        "new_track_id": new_track_id,
                        "class_name": class_name,
                        "distance_px": float(dist),
                    }
                    self.id_switch_events.append(event)
                    logger.info(f"Potential ID switch event: {event}")
                    break

        if class_name not in self._last_centers_by_class:
            self._last_centers_by_class[class_name] = []
        self._last_centers_by_class[class_name].append((new_track_id, center))
        if len(self._last_centers_by_class[class_name]) > 20:
            self._last_centers_by_class[class_name].pop(0)
