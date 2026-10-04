"""Model verification and setup script for SpatialVector-HMI.

Verifies local availability and integrity of:
1. yolov8n.pt (Primary Object Detector)
2. pothole_yolov8.pt (M13 Ground Hazard Detector)
"""
import hashlib
import os
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent


def get_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_models():
    print("=" * 60)
    print(" SpatialVector-HMI — Model Verification Utility")
    print("=" * 60)

    models = [
        ("yolov8n.pt", "COCO Object Detector (M02)", True),
        ("pothole_yolov8.pt", "Ground Hazard Detector (M13)", False),
    ]

    all_ok = True
    for filename, desc, required in models:
        candidates = [
            BASE_DIR / filename,
            BASE_DIR / "models" / filename,
        ]
        found = next((p for p in candidates if p.is_file()), None)
        if found:
            size_mb = found.stat().st_size / (1024 * 1024)
            sha = get_file_sha256(found)[:16]
            print(f"  [OK] {filename:<18} ({desc})")
            print(f"       Path: {found}")
            print(f"       Size: {size_mb:.2f} MB | SHA256[:16]: {sha}")
        else:
            status = "[MISSING]" if required else "[OPTIONAL]"
            print(f"  {status} {filename:<18} ({desc})")
            if required:
                all_ok = False
                print(f"       Run 'pip install ultralytics' or place {filename} in {BASE_DIR}")
            else:
                print(f"       System will run in safe mode without {filename}")
                print("       Overlay will display 'POTHOLE MODEL NOT LOADED'")

    print("=" * 60)
    return all_ok


if __name__ == "__main__":
    ok = verify_models()
    sys.exit(0 if ok else 1)
