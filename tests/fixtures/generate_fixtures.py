import cv2
import numpy as np
from pathlib import Path
import urllib.request
from ultralytics import YOLO

fixtures_dir = Path(__file__).resolve().parent / "fixtures"
fixtures_dir.mkdir(parents=True, exist_ok=True)
fixtures_dir = Path(__file__).resolve().parent

def make_figure(color=(60, 60, 220), head_color=(120, 100, 80)):
    patch = np.zeros((160, 70, 3), dtype=np.uint8)
    # Head
    cv2.circle(patch, (35, 30), 20, head_color, -1)
    # Torso
    cv2.rectangle(patch, (10, 55), (60, 110), color, -1)
    # Legs
    cv2.rectangle(patch, (15, 110), (30, 155), (30, 30, 30), -1)
    cv2.rectangle(patch, (40, 110), (55, 155), (30, 30, 30), -1)
    return patch
def ensure_person_crops():
    """Ensure person_1.png and person_2.png exist as realistic pedestrian patches."""
    p1_path = fixtures_dir / "person_1.png"
    p2_path = fixtures_dir / "person_2.png"
    if p1_path.exists() and p2_path.exists():
        return cv2.imread(str(p1_path)), cv2.imread(str(p2_path))

    bus_path = fixtures_dir / "bus.jpg"
    if not bus_path.exists():
        url = "https://ultralytics.com/images/bus.jpg"
        urllib.request.urlretrieve(url, str(bus_path))

    model = YOLO("yolov8n.pt")
    img = cv2.imread(str(bus_path))
    res = model(img)[0]
    person_crops = []
    for b in res.boxes:
        cls = int(b.cls[0])
        conf = float(b.conf[0])
        if model.names[cls] == "person" and conf > 0.7:
            xyxy = [int(v) for v in b.xyxy[0]]
            crop = img[xyxy[1]:xyxy[3], xyxy[0]:xyxy[2]]
            person_crops.append(crop)

    if len(person_crops) >= 2:
        cv2.imwrite(str(p1_path), person_crops[0])
        cv2.imwrite(str(p2_path), person_crops[1])
        return person_crops[0], person_crops[1]
    raise RuntimeError("Failed to extract realistic person crops from sample image")

def generate_walking_clip():
    out_path = fixtures_dir / "test_walking.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, 30, (640, 360))
    fig = make_figure()

    p1_raw, _ = ensure_person_crops()
    h, w = 180, int(180 * (p1_raw.shape[1] / p1_raw.shape[0]))
    p1 = cv2.resize(p1_raw, (w, h))

    for i in range(90):
        frame = np.full((360, 640, 3), (210, 215, 220), dtype=np.uint8)
        # Background pavement/lines
        cv2.line(frame, (0, 300), (640, 300), (160, 160, 160), 2)
        x = int(30 + i * 6)
        y = 140
        h, w = fig.shape[:2]
        x = int(20 + i * 5.5)
        y = 120
        if 0 <= x < 640 - w:
            frame[y : y + h, x : x + w] = fig
            frame[y : y + h, x : x + w] = p1
        writer.write(frame)
    writer.release()
    print(f"Generated: {out_path}")

def generate_crossing_clip():
    out_path = fixtures_dir / "test_crossing.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, 30, (640, 360))
    p1 = make_figure(color=(40, 180, 40))
    p2 = make_figure(color=(180, 40, 40))

    p1_raw, p2_raw = ensure_person_crops()
    h1, w1 = 180, int(180 * (p1_raw.shape[1] / p1_raw.shape[0]))
    p1 = cv2.resize(p1_raw, (w1, h1))

    h2, w2 = 180, int(180 * (p2_raw.shape[1] / p2_raw.shape[0]))
    p2 = cv2.resize(p2_raw, (w2, h2))

    for i in range(90):
        frame = np.full((360, 640, 3), (220, 220, 220), dtype=np.uint8)
        cv2.line(frame, (0, 320), (640, 320), (150, 150, 150), 2)
        # Person 1: left -> right
        x1 = int(30 + i * 6.5)
        x1 = int(20 + i * 6.0)
        # Person 2: right -> left
        x2 = int(570 - i * 6.5)
        y = 140
        h1, w1 = p1.shape[:2]
        x2 = int(580 - i * 6.0)
        y = 120
        if 0 <= x1 < 640 - w1:
            frame[y : y + h1, x1 : x1 + w1] = p1
        h2, w2 = p2.shape[:2]
        if 0 <= x2 < 640 - w2:
            frame[y : y + h2, x2 : x2 + w2] = p2
        writer.write(frame)
    writer.release()
    print(f"Generated: {out_path}")

if __name__ == "__main__":
    generate_walking_clip()
    generate_crossing_clip()

