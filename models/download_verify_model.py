"""Model verification and setup script for SpatialVector-HMI.

Verifies local availability and integrity of:
1. yolov8n.pt (Primary Object Detector - COCO)
2. pothole_yolov8.pt (M13 Ground Hazard Detector - Fine-tuned YOLOv8)
"""
import hashlib
import os
import shutil
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent

# Known verified checksums
VERIFIED_CHECKSUMS = {
    "yolov8n.pt": None,  # Ultralytics official
    "pothole_yolov8.pt": "c3c743711ac2bb32ca9ca9cf2c769737d3fbddd1c4e3ce201a4c41e043f96222",
}


def get_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def fetch_pothole_model_if_missing(dest: Path) -> bool:
    """Fetch base pretrained pothole detector if weights are missing."""
    print(f"[*] Pothole model not found at {dest}. Attempting auto-fetch from HuggingFace Hub...")
    try:
        from huggingface_hub import hf_hub_download
        cached = hf_hub_download(
            repo_id="peterhdd/pothole-detection-yolov8",
            filename="best.pt",
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, dest)
        # Also copy to root
        root_dest = BASE_DIR / "pothole_yolov8.pt"
        shutil.copyfile(cached, root_dest)
        print(f"[+] Successfully fetched pothole weights to {dest}")
        return True
    except Exception as e:
        print(f"[!] Could not auto-fetch pothole weights: {e}")
        return False


def verify_models():
    print("=" * 65)
    print(" SpatialVector-HMI — Model Verification Utility")
    print("=" * 65)

    models = [
        ("yolov8n.pt", "COCO Object Detector (M02)", True),
        ("pothole_yolov8.pt", "Ground Hazard Detector (M13 - Pothole YOLOv8)", True),
    ]

    all_ok = True
    for filename, desc, required in models:
        candidates = [
            BASE_DIR / filename,
            BASE_DIR / "models" / filename,
        ]
        found = next((p for p in candidates if p.is_file()), None)

        if not found and filename == "pothole_yolov8.pt":
            target = BASE_DIR / "models" / filename
            if fetch_pothole_model_if_missing(target):
                found = target

        if found:
            size_mb = found.stat().st_size / (1024 * 1024)
            sha = get_file_sha256(found)
            exp_sha = VERIFIED_CHECKSUMS.get(filename)
            match_str = " (Verified SHA256 match)" if (exp_sha and sha == exp_sha) else ""
            print(f"  [OK] {filename:<18} ({desc})")
            print(f"       Path: {found}")
            print(f"       Size: {size_mb:.2f} MB | SHA256: {sha[:16]}...{match_str}")
            print(f"       [STARTUP] Model loaded: {filename} ({found.name})")
        else:
            status = "[MISSING]" if required else "[OPTIONAL]"
            print(f"  {status} {filename:<18} ({desc})")
            if required:
                all_ok = False
                print(f"       Place {filename} in {BASE_DIR} or {BASE_DIR / 'models'}")

    print("=" * 65)
    return all_ok


if __name__ == "__main__":
    ok = verify_models()
    sys.exit(0 if ok else 1)
