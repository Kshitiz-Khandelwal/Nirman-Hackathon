"""Generate realistic fixture images for the SpatialVector evaluation harness.

Produces synthetic fixtures that closely simulate the camera feeds encountered in real deployment:
- Persons standing at 2m (feet on ground ROI)
- Table edge, table corner, desk with laptop
- Clear corridor, outdoor footpath
- Real-like asphalt road with irregular pothole and manhole
- Covered lens and dark room
"""
import json
from pathlib import Path
import cv2
import numpy as np

OUT = Path(__file__).parent
rng = np.random.default_rng(42)


def save(name: str, img: np.ndarray, label: dict):
    cv2.imwrite(str(OUT / f"{name}.png"), img)
    (OUT / f"{name}.json").write_text(json.dumps(label, indent=2))


def noise(h: int, w: int, lo: int = 0, hi: int = 15) -> np.ndarray:
    return rng.integers(lo, hi, (h, w, 3), dtype=np.uint8)


def textured_floor(h: int, w: int, base: int = 140, var: int = 25) -> np.ndarray:
    img = rng.integers(max(0, base - var), min(255, base + var), (h, w, 3), dtype=np.uint8)
    # Add subtle tile / pavement texture
    tile_h, tile_w = 40, 40
    for y in range(0, h, tile_h):
        img[y:min(h, y + 1), :] = np.clip(img[y:min(h, y + 1), :].astype(int) - 15, 0, 255)
    for x in range(0, w, tile_w):
        img[:, x:min(w, x + 1)] = np.clip(img[:, x:min(w, x + 1)].astype(int) - 15, 0, 255)
    return np.clip(img.astype(np.int16) + rng.integers(-5, 5, (h, w, 3)), 0, 255).astype(np.uint8)


def add_standing_person(frame: np.ndarray, cx: int, ground_y: int = 435, height: int = 350, dark: bool = False):
    """Draw a realistic standing pedestrian centered at cx, with feet touching ground_y."""
    fh, fw = frame.shape[:2]
    person_path = Path(__file__).resolve().parent.parent / "person_1.png"
    if person_path.is_file():
        p1 = cv2.imread(str(person_path))
        pw = int(height * (p1.shape[1] / p1.shape[0]))
        p1_scaled = cv2.resize(p1, (pw, height))
        if dark:
            p1_scaled = np.clip(p1_scaled.astype(np.int16) - 45, 15, 255).astype(np.uint8)
        x1 = max(0, cx - pw // 2)
        x2 = min(fw, x1 + pw)
        y1 = max(0, ground_y - height)
        y2 = min(fh, ground_y)
        frame[y1:y2, x1:x2] = p1_scaled[:y2 - y1, :x2 - x1]
        return

    top_y = max(10, ground_y - height)
    sub_w = 90
    x1 = max(0, cx - sub_w // 2)
    x2 = min(fw, cx + sub_w // 2)
    
    body_color = (35, 35, 38) if dark else (140, 70, 45)
    pants_color = (25, 25, 28) if dark else (50, 50, 60)
    skin_color = (135, 150, 195)

    head_r = 22
    head_cy = top_y + head_r + 5
    cv2.circle(frame, (cx, head_cy), head_r, skin_color, -1)
    cv2.circle(frame, (cx, head_cy), head_r, (40, 40, 40), 2)

    torso_top = head_cy + head_r
    torso_bottom = top_y + int(height * 0.55)
    cv2.rectangle(frame, (cx - 32, torso_top), (cx + 32, torso_bottom), body_color, -1)

    leg_w = 16
    cv2.rectangle(frame, (cx - 26, torso_bottom), (cx - 26 + leg_w, ground_y), pants_color, -1)
    cv2.rectangle(frame, (cx + 10, torso_bottom), (cx + 10 + leg_w, ground_y), pants_color, -1)

    # Shoes (touching ground)
    cv2.ellipse(frame, (cx - 18, ground_y), (14, 6), 0, 0, 360, (20, 20, 20), -1)
    cv2.ellipse(frame, (cx + 18, ground_y), (14, 6), 0, 0, 360, (20, 20, 20), -1)


# ── Category generators ───────────────────────────────────────────────────────

def make_person_with_bag():
    h, w = 480, 640
    img = textured_floor(h, w, 160)
    add_standing_person(img, cx=320, ground_y=430, height=330, dark=False)
    # Backpack / shoulder bag on right side
    cv2.rectangle(img, (335, 180), (375, 290), (30, 45, 130), -1)
    cv2.rectangle(img, (335, 180), (375, 290), (15, 25, 80), 2)
    save("person_with_bag", img, {
        "expected_objects": ["person", "backpack"],
        "expected_potholes": False,
        "expected_walkable": {"left": "WALKABLE", "centre": "BLOCKED", "right": "WALKABLE"}
    })


def make_person_dark_clothing():
    h, w = 480, 640
    img = textured_floor(h, w, 165)
    add_standing_person(img, cx=320, ground_y=430, height=330, dark=True)
    save("person_dark_clothing", img, {
        "expected_objects": ["person"],
        "expected_potholes": False,
        "expected_walkable": {"left": "WALKABLE", "centre": "BLOCKED", "right": "WALKABLE"}
    })


def make_dark_floor():
    h, w = 480, 640
    img = rng.integers(10, 35, (h, w, 3), dtype=np.uint8)
    save("dark_floor", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_shadow_on_floor():
    h, w = 480, 640
    img = textured_floor(h, w, 160)
    # Deep shadow covering center floor
    img[270:450, 160:480] = np.clip(img[270:450, 160:480].astype(int) - 85, 5, 255).astype(np.uint8)
    save("shadow_on_floor", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_table_edge():
    h, w = 480, 640
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:300, :] = textured_floor(300, w, 205)      # table surface (light wood/laminate)
    img[300:, :] = textured_floor(h - 300, w, 110)  # floor below table edge
    # Strong dark line marking edge discontinuity
    cv2.line(img, (0, 300), (w, 300), (10, 10, 10), 6)
    save("table_edge", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_table_corner():
    h, w = 480, 640
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = textured_floor(h, w, 115)           # floor background
    # Table corner pointing towards user in center:
    # Corner apex at (320, 380), with edges spreading out across left and right at y=310
    pts = np.array([[0, 0], [640, 0], [640, 310], [320, 380], [0, 310]], dtype=np.int32)
    cv2.fillPoly(img, [pts], (210, 205, 200))
    cv2.polylines(img, [pts], False, (15, 15, 15), 6)
    save("table_corner", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_desk_laptop():
    h, w = 480, 640
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # Desk covers bottom half of frame
    img[:270, :] = textured_floor(270, w, 130)       # room background
    img[270:, :] = textured_floor(h - 270, w, 215)   # desk surface
    cv2.line(img, (0, 270), (w, 270), (15, 15, 15), 5)  # table edge
    # Laptop: display y=100..265, keyboard base y=265..360 (inside ground ROI)
    cv2.rectangle(img, (180, 100), (460, 265), (40, 40, 45), -1)
    cv2.rectangle(img, (195, 115), (445, 250), (210, 225, 235), -1)
    cv2.rectangle(img, (170, 265), (470, 360), (55, 55, 60), -1)
    # Trackpad
    cv2.rectangle(img, (290, 320), (350, 355), (75, 75, 80), -1)
    save("desk_laptop", img, {
        "expected_objects": ["laptop"],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_blank_wall():
    h, w = 480, 640
    img = np.full((h, w, 3), 195, dtype=np.uint8)
    img = np.clip(img.astype(int) + noise(h, w, 0, 4), 0, 255).astype(np.uint8)
    save("blank_wall", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_stairs():
    h, w = 480, 640
    img = textured_floor(h, w, 160)
    step_h = 32
    for i in range(7):
        y = 230 + i * step_h
        if y < h:
            cv2.line(img, (0, y), (w, y), (15, 15, 15), 5)
            y_end = min(h, y + step_h)
            img[y:y_end, :] = textured_floor(y_end - y, w, 110 + (i % 2) * 55)
    save("stairs_ledge", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_clear_indoor_corridor():
    h, w = 480, 640
    img = textured_floor(h, w, 145, 20)
    # Walls on left and right sides in upper half
    img[:200, :90] = textured_floor(200, 90, 200)
    img[:200, w - 90:] = textured_floor(200, 90, 200)
    save("clear_indoor_corridor", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "WALKABLE", "centre": "WALKABLE", "right": "WALKABLE"}
    })


def make_outdoor_footpath():
    h, w = 480, 640
    img = np.full((h, w, 3), (130, 155, 180), dtype=np.uint8)  # sky / distant foliage
    img[240:, :] = textured_floor(h - 240, w, 140, 20)          # pavement path
    cv2.line(img, (0, 240), (w, 240), (120, 140, 130), 2)
    save("outdoor_footpath", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "WALKABLE", "centre": "WALKABLE", "right": "WALKABLE"}
    })


def make_road_with_pothole():
    h, w = 480, 640
    # Asphalt surface
    img = rng.integers(75, 105, (h, w, 3), dtype=np.uint8)
    # Irregular pothole contour centered in centre corridor at y=360
    pts = []
    num_pts = 16
    cx, cy, rx, ry = 320, 360, 55, 38
    for i in range(num_pts):
        angle = 2.0 * np.pi * i / num_pts
        r_jitter = rng.uniform(0.75, 1.25)
        px = int(cx + rx * r_jitter * np.cos(angle))
        py = int(cy + ry * r_jitter * np.sin(angle))
        pts.append([px, py])
    poly = np.array([pts], dtype=np.int32)
    
    # Fill pothole interior with dark asphalt cavity
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, poly, 255)
    img[mask > 0] = rng.integers(12, 32, (3,), dtype=np.uint8)
    # Jagged dark rim
    cv2.polylines(img, poly, True, (8, 8, 8), 3)

    save("road_pothole", img, {
        "expected_objects": [],
        "expected_potholes": True,
        "expected_walkable": {"left": "WALKABLE", "centre": "UNKNOWN", "right": "WALKABLE"}
    })


def make_road_manhole_patch():
    h, w = 480, 640
    img = rng.integers(75, 105, (h, w, 3), dtype=np.uint8)
    # Circular manhole on left
    cv2.circle(img, (180, 350), 38, (45, 45, 45), -1)
    cv2.circle(img, (180, 350), 38, (25, 25, 25), 3)
    # Rectangular asphalt patch on right
    cv2.rectangle(img, (400, 300), (520, 390), (115, 120, 120), -1)
    save("road_manhole_patch", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "WALKABLE", "centre": "WALKABLE", "right": "WALKABLE"}
    })


def make_dark_frame():
    h, w = 480, 640
    img = rng.integers(0, 8, (h, w, 3), dtype=np.uint8)
    save("dark_covered_lens", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_covered_lens():
    h, w = 480, 640
    img = np.full((h, w, 3), 12, dtype=np.uint8)
    img = cv2.GaussianBlur(img, (21, 21), 5)
    img = np.clip(img.astype(int) + noise(h, w, 0, 4), 0, 255).astype(np.uint8)
    save("covered_lens", img, {
        "expected_objects": [],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_keyboard_on_desk():
    h, w = 480, 640
    img = textured_floor(h, w, 170)
    img[:220, :] = textured_floor(220, w, 190)
    cv2.rectangle(img, (80, 240), (560, 350), (50, 50, 52), -1)
    for row in range(4):
        for col in range(14):
            kx = 95 + col * 33
            ky = 252 + row * 22
            cv2.rectangle(img, (kx, ky), (kx + 25, ky + 16), (60, 62, 65), -1)
            cv2.rectangle(img, (kx + 1, ky + 1), (kx + 24, ky + 15), (75, 75, 78), -1)
    save("keyboard_on_desk", img, {
        "expected_objects": ["keyboard"],
        "expected_potholes": False,
        "expected_walkable": {"left": "UNKNOWN", "centre": "UNKNOWN", "right": "UNKNOWN"}
    })


def make_bag_on_floor():
    h, w = 480, 640
    img = textured_floor(h, w, 155)
    cv2.ellipse(img, (320, 360), (120, 70), 0, 0, 360, (30, 35, 90), -1)
    cv2.rectangle(img, (220, 295), (420, 360), (40, 45, 100), -1)
    save("bag_on_floor", img, {
        "expected_objects": ["backpack"],
        "expected_potholes": False,
        "expected_walkable": {"left": "WALKABLE", "centre": "BLOCKED", "right": "WALKABLE"}
    })


ALL = [
    make_person_with_bag,
    make_person_dark_clothing,
    make_dark_floor,
    make_shadow_on_floor,
    make_table_edge,
    make_table_corner,
    make_desk_laptop,
    make_blank_wall,
    make_stairs,
    make_clear_indoor_corridor,
    make_outdoor_footpath,
    make_road_with_pothole,
    make_road_manhole_patch,
    make_dark_frame,
    make_covered_lens,
    make_keyboard_on_desk,
    make_bag_on_floor,
]

if __name__ == "__main__":
    for gen in ALL:
        gen()
    print(f"Generated {len(ALL)} fixtures in {OUT}")
