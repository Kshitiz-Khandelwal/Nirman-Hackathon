"""Compare YOLOv8n vs YOLOv8s on real HOLDOUT fixtures.

Measures:
- Latency (ms) and throughput (FPS) on CPU
- Object Precision, Recall, and F1 across expected object classes
- Confusion table: wrong class, phantom object, missed object per class
- Saves top 20 worst failure frames annotated to eval_object_failures/
"""

import json
import time
from pathlib import Path
from collections import defaultdict
import cv2
import numpy as np
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = BASE_DIR / "tests" / "fixtures" / "real" / "manifest.json"
FAILURES_DIR = BASE_DIR / "eval_object_failures"
FAILURES_DIR.mkdir(parents=True, exist_ok=True)

manifest = json.load(open(MANIFEST_PATH))
holdout_set = [x for x in manifest if x["split"] == "HOLDOUT"]

def evaluate_model(model_name: str, conf_thresh: float = 0.30):
    print(f"\n[*] Evaluating {model_name} on {len(holdout_set)} HOLDOUT images (conf={conf_thresh})...")
    model = YOLO(model_name)
    
    # Warmup
    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
    for _ in range(3):
        _ = model(dummy, conf=conf_thresh, verbose=False)
        
    times = []
    confusion = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "wrong_class": 0, "phantom": 0})
    failures = []
    
    for item in holdout_set:
        img_p = BASE_DIR / "tests" / "fixtures" / "real" / "holdout" / item["image_file"]
        img = cv2.imread(str(img_p))
        if img is None:
            continue
            
        t0 = time.perf_counter()
        results = model(img, conf=conf_thresh, verbose=False)[0]
        dt = time.perf_counter() - t0
        times.append(dt)
        
        detected_boxes = results.boxes.xyxy.cpu().numpy() if results.boxes is not None else []
        detected_classes = [model.names[int(c)] for c in results.boxes.cls.cpu().numpy()] if results.boxes is not None else []
        expected_classes = list(item.get("expected_objects", []))
        
        # Match detections to expectations
        matched_exp = set()
        img_mistakes = 0
        
        for det_cls in detected_classes:
            if det_cls in expected_classes and det_cls not in matched_exp:
                confusion[det_cls]["tp"] += 1
                matched_exp.add(det_cls)
            elif expected_classes:
                # Wrong class or phantom in an image expecting something else
                confusion[det_cls]["wrong_class"] += 1
                confusion[det_cls]["fp"] += 1
                img_mistakes += 1
            else:
                # Phantom object on an image that expected no objects (e.g. blank wall, table edge)
                confusion[det_cls]["phantom"] += 1
                confusion[det_cls]["fp"] += 1
                img_mistakes += 1

        for exp_cls in expected_classes:
            if exp_cls not in matched_exp:
                confusion[exp_cls]["fn"] += 1
                img_mistakes += 1
                
        if img_mistakes > 0:
            failures.append({
                "item": item,
                "img": img,
                "mistakes": img_mistakes,
                "detected": detected_classes,
                "expected": expected_classes,
                "boxes": detected_boxes,
            })

    mean_dt = float(np.mean(times))
    fps = 1.0 / max(1e-6, mean_dt)
    
    # Calculate aggregate precision & recall
    total_tp = sum(c["tp"] for c in confusion.values())
    total_fp = sum(c["fp"] for c in confusion.values())
    total_fn = sum(c["fn"] for c in confusion.values())
    precision = total_tp / max(1, total_tp + total_fp)
    recall = total_tp / max(1, total_tp + total_fn)
    f1 = 2 * precision * recall / max(1e-6, precision + recall)
    
    print(f"--- {model_name} Results ---")
    print(f"  Latency  : {mean_dt * 1000:.1f} ms ({fps:.1f} FPS)")
    print(f"  Precision: {precision:.2%} (TP={total_tp}, FP={total_fp})")
    print(f"  Recall   : {recall:.2%} (FN={total_fn})")
    print(f"  F1 Score : {f1:.2%}")
    
    return {
        "model": model_name,
        "latency_ms": mean_dt * 1000,
        "fps": fps,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion": dict(confusion),
        "failures": failures,
    }

def main():
    print("=" * 65)
    print(" SpatialVector-HMI — Object Detector Comparison & Confusion Table")
    print("=" * 65)
    
    res_nano = evaluate_model("yolov8n.pt", conf_thresh=0.25)
    res_small = evaluate_model("yolov8s.pt", conf_thresh=0.25)
    
    print("\n" + "=" * 65)
    print(f" {'Model':<12} | {'Latency (ms)':<14} | {'FPS':<8} | {'Precision':<10} | {'Recall':<8} | {'F1':<8}")
    print("-" * 65)
    print(f" {'yolov8n.pt':<12} | {res_nano['latency_ms']:<14.1f} | {res_nano['fps']:<8.1f} | {res_nano['precision']:<10.1%} | {res_nano['recall']:<8.1%} | {res_nano['f1']:<8.1%}")
    print(f" {'yolov8s.pt':<12} | {res_small['latency_ms']:<14.1f} | {res_small['fps']:<8.1f} | {res_small['precision']:<10.1%} | {res_small['recall']:<8.1%} | {res_small['f1']:<8.1%}")
    print("=" * 65)
    
    # Print Confusion Table for chosen model (or both)
    print("\n=== Confusion Table: yolov8n.pt (per class) ===")
    print(f"{'Class':<16} | {'TP':<6} | {'FP':<6} | {'FN':<6} | {'Wrong Class':<12} | {'Phantom Obj':<12}")
    print("-" * 65)
    for cls_name, counts in sorted(res_nano["confusion"].items(), key=lambda x: -(x[1]["tp"] + x[1]["fp"])):
        print(f"{cls_name:<16} | {counts['tp']:<6} | {counts['fp']:<6} | {counts['fn']:<6} | {counts['wrong_class']:<12} | {counts['phantom']:<12}")

    # Save Top 20 worst frames from yolov8n
    print(f"\n[*] Saving Top 20 failure cases to {FAILURES_DIR}...")
    sorted_fails = sorted(res_nano["failures"], key=lambda x: -x["mistakes"])[:20]
    for idx, fail in enumerate(sorted_fails):
        ann = fail["img"].copy()
        for box in fail["boxes"]:
            bx1, by1, bx2, by2 = map(int, box)
            cv2.rectangle(ann, (bx1, by1), (bx2, by2), (0, 0, 255), 2)
        exp_str = ", ".join(fail["expected"]) if fail["expected"] else "NONE"
        got_str = ", ".join(fail["detected"]) if fail["detected"] else "NONE"
        cv2.putText(ann, f"EXP: {exp_str}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(ann, f"GOT: {got_str}", (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        out_f = FAILURES_DIR / f"worst_{idx+1:02d}_{fail['item']['id']}.jpg"
        cv2.imwrite(str(out_f), ann)
    print(f"[+] Saved 20 annotated failure frames to {FAILURES_DIR}")

if __name__ == "__main__":
    main()
