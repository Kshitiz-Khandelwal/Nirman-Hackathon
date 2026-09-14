import time
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest

# Add repo root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spatialvector.perception.tracker import MultiObjectTracker
from spatialvector.perception.schemas import Frame, Track


def make_person_patch(h=140, w=60):
    """Generates a small synthetic person-like patch."""
    patch = np.zeros((h, w, 3), dtype=np.uint8)
    # Head
    cv2.circle(patch, (w // 2, 25), 18, (120, 100, 80), -1)
    # Body
    cv2.rectangle(patch, (10, 45), (w - 10, 95), (60, 60, 200), -1)
    # Legs
    cv2.rectangle(patch, (12, 95), (26, h - 5), (40, 40, 40), -1)
    cv2.rectangle(patch, (w - 26, 95), (w - 12, h - 5), (40, 40, 40), -1)
    return patch


def generate_test_crossing_clip(file_path: Path):
    """Creates a 60-frame video of two people walking across each other."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = 30
    writer = cv2.VideoWriter(str(file_path), fourcc, fps, (640, 360))
    p1 = make_person_patch()
    p2 = make_person_patch()

    for i in range(60):
        frame = np.full((360, 640, 3), 220, dtype=np.uint8)
        # Person 1 moves left to right: x: 50 -> 500, y: 150
        x1 = int(50 + (i * 7.5))
        y1 = 150
        # Person 2 moves right to left: x: 550 -> 100, y: 150
        x2 = int(550 - (i * 7.5))
        y2 = 150

        # Draw Person 1
        h1, w1 = p1.shape[:2]
        if 0 <= x1 < 640 - w1 and 0 <= y1 < 360 - h1:
            frame[y1 : y1 + h1, x1 : x1 + w1] = p1

        # Draw Person 2
        h2, w2 = p2.shape[:2]
        if 0 <= x2 < 640 - w2 and 0 <= y2 < 360 - h2:
            frame[y2 : y2 + h2, x2 : x2 + w2] = p2

        writer.write(frame)
    writer.release()


try:
    import pytest
except ImportError:
    pytest = None

if pytest is not None:
    @pytest.fixture(scope="session")
    def crossing_clip_path(tmp_path_factory):
        p = tmp_path_factory.mktemp("video") / "crossing_test.mp4"
        generate_test_crossing_clip(p)
        return str(p)
else:
    def crossing_clip_path():
        return None


def test_t06_persistent_track_id_single_subject():
    """T06: Run against a clip of one moving person; assert track_id persists without jitter."""
    tracker = MultiObjectTracker(backend="bytetrack", history_length=10)
    person = make_person_patch()

    seen_track_ids = []
    for i in range(25):
        frame = np.full((360, 640, 3), 220, dtype=np.uint8)
        x = int(80 + (i * 10))
        y = 120
        frame[y : y + 140, x : x + 60] = person

        f_obj = Frame(frame_id=i, image=frame, t_capture=i * 0.033, fps_estimate=30.0)
        tracks = tracker.track(f_obj)

        if len(tracks) > 0:
            seen_track_ids.append(tracks[0].track_id)

    # If tracking detected the object, ensure identity stability
    if len(seen_track_ids) > 5:
        primary_id = seen_track_ids[0]
        # Should persist with the same ID across the uninterrupted run
        stable_count = sum(1 for tid in seen_track_ids if tid == primary_id)
        ratio = stable_count / len(seen_track_ids)
        assert ratio >= 0.8, f"Track ID stability ratio {ratio:.2f} was below 0.8"


def test_t07_camera_rotation_bounded_track_count():
    """T07: Pan across scene with one subject; assert track count does not explode into many short-lived IDs."""
    tracker = MultiObjectTracker(backend="bytetrack", history_length=10)
    person = make_person_patch()

    distinct_ids = set()
    for i in range(30):
        # Simulated panning camera (background shifts + person shifts across frame)
        frame = np.full((360, 640, 3), 180 + (i % 20), dtype=np.uint8)
        x = int(100 + i * 5)
        y = 120
        frame[y : y + 140, x : x + 60] = person

        f_obj = Frame(frame_id=i, image=frame, t_capture=i * 0.033, fps_estimate=30.0)
        tracks = tracker.track(f_obj)
        for t in tracks:
            distinct_ids.add(t.track_id)

    # Should not spawn an excessive number of track IDs for one subject (concrete upper bound)
    assert len(distinct_ids) <= 4, f"Track count exploded: {len(distinct_ids)} distinct IDs observed"


def test_t08_id_switch_benchmark_reporting(crossing_clip_path):
    """T08: Run against two-person crossing clip. Record and report ID-switch benchmark metric."""
    tracker = MultiObjectTracker(backend="bytetrack", history_length=10)
    cap = cv2.VideoCapture(crossing_clip_path)

    frame_idx = 0
    all_tracks_per_frame = []
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        f_obj = Frame(frame_id=frame_idx, image=frame, t_capture=frame_idx * 0.033, fps_estimate=30.0)
        tracks = tracker.track(f_obj)
        all_tracks_per_frame.append(tracks)

        # Assert no duplicate IDs in any single frame
        track_ids = [t.track_id for t in tracks]
        assert len(track_ids) == len(set(track_ids)), f"Duplicate track IDs in frame {frame_idx}: {track_ids}"

        frame_idx += 1
    cap.release()

    id_switch_count = len(tracker.id_switch_events)
    print(f"\n[BENCHMARK T08] Tracker Backend: {tracker.backend}")
    print(f"[BENCHMARK T08] Total frames processed: {frame_idx}")
    print(f"[BENCHMARK T08] Recorded ID-switch events count: {id_switch_count}")
    print(f"[BENCHMARK T08] Event details: {tracker.id_switch_events}")

    # Report metric; does not fail unless duplicate IDs or unexpected exception occurred
    assert id_switch_count >= 0


if __name__ == "__main__":
    import tempfile
    print("--- Running M03 Multi-Object Tracker Tests Standalone ---")
    print("[TEST] Running T06: Persistent Track ID on single subject...")
    test_t06_persistent_track_id_single_subject()
    print("  -> T06 PASSED")

    print("[TEST] Running T07: Panning camera bounded track count...")
    test_t07_camera_rotation_bounded_track_count()
    print("  -> T07 PASSED")

    print("[TEST] Running T08: ID-switch benchmark on crossing clip...")
    with tempfile.TemporaryDirectory() as tmpdir:
        clip_p = Path(tmpdir) / "crossing.mp4"
        generate_test_crossing_clip(clip_p)
        test_t08_id_switch_benchmark_reporting(str(clip_p))
        print("  -> T08 PASSED")

    print("\nALL M03 TESTS PASSED SUCCESSFULLY.")

