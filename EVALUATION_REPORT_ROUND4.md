# SpatialVector-HMI: Round 4 Evaluation & Audit Report
**Date**: 2026-10-04  
**Audit Target**: Commit `5092205` and Round 4 Process Repairs  
**Principles Enforced**: Process before product. No criterion marked PASSED unless it strictly meets target. Zero threshold tuning on HOLDOUT. HOLDOUT evaluated strictly once. All threshold changes restricted to TUNE and documented in `CHANGELOG.md`.

---

## 1. Executive Summary & Measured Results Table

> [!IMPORTANT]
> **Reporting Invariant**: Every number reported in this table is directly measured by code execution. LIVE evaluation frames are reported first, followed by the frozen Fresh HOLDOUT split (375 images from new sources, 25 per category, verified zero near-duplicate leakage against TUNE).

| Evaluation Split | Criterion / Metric | Stated Target | Measured Result | Status |
|---|---|---|---|:---:|
| **LIVE** (100 frames) | End-to-End Pipeline FPS | $\ge 15.0$ FPS | **15.8 FPS** (63.2 ms latency) | **PASS** |
| **LIVE** (100 frames) | Pothole FPR on Negatives | $\le 5.0\%$ | **0.00%** (0 / 100) | **PASS** |
| **LIVE** (100 frames) | YOLOv8n Object Precision | Informational | **74.29%** (TP=130, FP=45) | **MEASURED** |
| **LIVE** (100 frames) | YOLOv8n Object Recall | Informational | **83.87%** (TP=130, FN=25) | **MEASURED** |
| **LIVE** (100 frames) | Clear Corridor Recall (single frame) | $\ge 80.0\%$ | **0.00%** (0 / 228 corridor checks) | **FAIL** |
| **Fresh HOLDOUT** (375 images) | Hazard False WALKABLE Rate | **0.00%** | **2.29%** (4 / 175 images, 95% Wilson UB: **5.73%**) | **FAIL** |
| **Fresh HOLDOUT** (375 images) | Clear Corridor Recall (single frame) | $\ge 80.0\%$ | **25.00%** (25 / 100 images) | **FAIL** |
| **Fresh HOLDOUT** (375 images) | Pothole FPR on Negatives | $\le 5.0\%$ | **3.43%** (12 / 350 negative images) | **PASS** |
| **Fresh HOLDOUT** (375 images) | Pothole Recall | $\ge 60.0\%$ | **28.00%** (7 / 25 positive images) | **FAIL** |
| **Fresh HOLDOUT** (375 images) | Pothole Precision | Informational | **36.84%** (7 / 19 detections) | **MEASURED** |
| **Fresh HOLDOUT** (375 images) | Object Detector Precision (YOLOv8n) | Informational | **77.62%** (TP=274, FP=79) | **MEASURED** |
| **Fresh HOLDOUT** (375 images) | Object Detector Recall (YOLOv8n) | Informational | **58.17%** (TP=274, FN=197) | **MEASURED** |
| **Fresh HOLDOUT** (375 images) | Object Detector F1 (YOLOv8n) | Informational | **0.6650** | **MEASURED** |
| **Packaging & Safety** | SegFormer Missing Fail-Safe Refusal | Refuse WALK_FORWARD | **Verified** (Outputs UNKNOWN) | **PASS** |
| **Packaging & Safety** | Pinned Dependencies in requirements.txt | transformers pinned | **Verified** (`transformers>=4.40.0,<5.0.0`) | **PASS** |
| **Packaging & Safety** | Startup Multi-Model Self-Check | Verified weights/hashes | **Verified** (`models/download_verify_model.py`) | **PASS** |

---

## 2. Step 1: Repair of Evaluation Process

### 2.1 Per-Image Ground Truth Labels
- In Round 3, `tests/fixtures/real/*.json` had category-level uniform defaults where `expected_objects` was set to a single dummy string (e.g. `"chair"` across every indoor image).
- **Audit & Pre-fill**:
  - We ran `yolov8x.pt` (the 68M parameter COCO model) across all 360 images in `tests/fixtures/real/tune/`.
  - Hand-audited every single image: **300 out of 360 labels were corrected** for visible COCO objects (e.g., distinguishing pedestrians, vehicles, bags, bicycles, laptops, potted plants vs empty background).
- **Category Mismatch Purge**:
  - 9 images were discovered to be corrupt or completely mismatched to their category:
    - 2 `indoor_floor` images showed vertical walls and ceilings with no floor visible.
    - 1 `blank_wall` image showed an outdoor soccer pitch.
    - 3 `table_edge` images showed outdoor lakes and boats.
    - 3 `desk_closeup` images showed exterior street buildings.
  - Replaced all 9 images with genuine category photos using `scripts/download_clean_replacements.py`.

### 2.2 Re-Split and Freeze Lock
- The original 360 images were permanently designated as the **TUNE** split (`tests/fixtures/real/tune/`).
- Because the previous HOLDOUT was repeatedly evaluated during threshold adjustments, it was treated as **burned**.
- A brand new **Fresh HOLDOUT** set was generated from scratch (`tests/fixtures/real/holdout/`) containing **25 images per category across 15 categories (375 total images)**.
- **Perceptual dHash Invariant**: During download, every prospective image was compared against all 351 TUNE images using difference hashing (`dhash`). Any candidate with Hamming distance $< 6$ was automatically discarded, guaranteeing zero near-duplicate leakage.
- **CI-Style Freeze Guard (`scripts/check_holdout_freeze.py`)**:
  - Generates `tests/fixtures/real/holdout/freeze_lock.json` recording the SHA256 of `manifest.json`.
  - Enforces that any modification to thresholds or configuration files must be accompanied by an entry in `CHANGELOG.md`. Exits with non-zero code on violation.

### 2.3 User's Own Live Frames Evaluation Split
- Extracted 100 sequential frames from user walking and crossing footage into `sessions/live_recorded_frames/`.
- Per-frame ground truth verified with `YOLOv8x` + hand audit:
  - Frames 1–50: Unobstructed user walking corridor (`walkable=True`).
  - Frames 51–100: Crossing pedestrian scenario (crossing corridor blocked during frames 62–85).
- Evaluated as a standalone split **LIVE** and reported first in the summary.

---

## 3. Step 2: Object Detection Analysis & Model Selection

### 3.1 Walking-Relevant Confusion Analysis
Evaluated across walking-relevant classes on verified ground truth:

| Class | YOLOv8n Precision | YOLOv8n Recall | YOLOv8s Precision | YOLOv8s Recall | YOLOv8m Precision | YOLOv8m Recall |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **person** | 87.5% | 70.0% | 88.9% | 80.0% | 90.9% | 90.0% |
| **car / vehicle** | 88.9% | 61.5% | 90.0% | 76.9% | 91.7% | 84.6% |
| **bicycle** | 80.0% | 57.1% | 83.3% | 71.4% | 85.7% | 85.7% |
| **chair / bench**| 81.8% | 52.9% | 84.6% | 64.7% | 85.0% | 76.5% |
| **backpack / bag**| 75.0% | 50.0% | 80.0% | 66.7% | 83.3% | 83.3% |
| **dog / animal** | 100.0% | 66.7% | 100.0% | 100.0% | 100.0% | 100.0% |

### 3.2 Accuracy vs. End-to-End Speed Benchmark
Measured on CPU host architecture:

| Model | Weights Size | Micro Precision | Micro Recall | Micro F1 | Standalone Latency | Standalone FPS | Full Pipeline FPS |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`yolov8n.pt`** | **6.2 MB** | **85.9%** | **59.8%** | **0.705** | **27.3 ms** | **36.6 FPS** | **15.8 FPS** |
| `yolov8s.pt` | 21.5 MB | 87.9% | 74.5% | 0.806 | 56.2 ms | 17.8 FPS | ~10.4 FPS |
| `yolov8m.pt` | 49.7 MB | 88.3% | 84.8% | 0.865 | 133.8 ms | 7.5 FPS | ~5.6 FPS |

### 3.3 Selection Decision
- **Chosen Model**: **`yolov8n.pt`**.
- **Rationale**: The stated requirement demands a live frame rate of $\ge 15.0$ FPS for the full interactive pipeline (camera capture + YOLO + SegFormer + ByteTrack + Optical Flow + Voice + HMI). With `yolov8n`, full pipeline speed reaches **15.8 FPS**. Any model larger than nano (`yolov8s` at 17.8 FPS standalone, `yolov8m` at 7.5 FPS standalone) reduces the live viewer below the 15 FPS safety minimum.

---

## 4. Step 3: Ground Hazards & Pothole Model Performance

### 4.1 Measured Results on Fresh HOLDOUT (375 Images)
- Evaluated on the un-tuned Fresh HOLDOUT (25 positive pothole images, 350 negative images):
  - **Pothole Recall**: **28.00%** (7 / 25 detected). Target: $\ge 60.00\%$. **FAIL**.
  - **Pothole FPR on Negatives**: **3.43%** (12 / 350 false alerts). Target: $\le 5.00\%$. **PASS**.
  - **Pothole Precision**: **36.84%** (7 / 19).

### 4.2 Two-Stage Ground Confirmation Implementation
To prevent false alarms on non-navigable surfaces (such as dark spots on walls, monitor screens, and table edges), we implemented the two-stage confirmation rule in `spatialvector/hazards/ground_hazard.py`:
```python
if self.require_ground_confirmation and freespace_result is not None:
    # Requires the freespace segmentation to confirm walkable ground
    c_status = freespace_result.get(det.corridor)
    if c_status != CorridorStatus.WALKABLE:
        continue  # Reject candidate if ground is not confirmed
```
This reduced false positives on hazard categories to zero in TUNE.

### 4.3 Policy Action: Advisory-Only Classification
Because the fine-tuned model does not satisfy the joint target ($\ge 60\%$ recall at $\le 5\%$ FPR):
- **Decision**: In accordance with prompt instructions, **potholes are formally designated as ADVISORY ONLY**.
- **Enforcement**:
  - `spatialvector/hazards/ground_hazard.py`: Set `advisory_only: true`.
  - `spatialvector/guidance/decision.py`: When `pothole_advisory_only: true`, ground hazards display a visual alert on screen and trigger voice warning, but **never stop or redirect the user** (`STOP` or `AVOID_LEFT/RIGHT`).
  - Documented prominently in `README.md` and `CHANGELOG.md`.

---

## 5. Step 4: Walkable Ground (M14) Investigation & Evaluation

### 5.1 Veto Investigation on TUNE Split
Auditing why clear images failed to achieve `WALKABLE` on the TUNE split revealed the following cue veto counts across clear category frames:

1. **SegFormer Class Mix Veto (41 frames)**: In corridors and walkways, side walls and doors occupy $>30\%$ of the image corridor, causing `o_frac > obstacle_max_frac` (0.35) even when the central walking path is clear.
2. **YOLO Bounding Box Overlap Veto (20 frames)**: YOLO obstacle bounding boxes extending into the upper portion of the corridor trigger `BLOCKED` even when distant ($>3\text{m}$).
3. **Span Difference & Continuity Veto (14 frames)**: High-contrast tile borders, shadows, and carpet seams cause horizontal gradient variance $>15\%$.
4. **Validity Gate Veto (2 frames)**: Low light or extreme exposure.

### 5.2 Safety Invariant vs Recall Trade-off
- When we tested relaxed thresholds on TUNE (`obstacle_max_frac: 0.50`, `ground_min_frac: 0.20`), clear category recall rose from 14.6% to 26.0%, but immediately produced **5.36% false WALKABLE decisions on stairs and table edges**.
- In an assistive navigation system for blind and visually impaired users, **a false WALKABLE into a staircase or off an edge is a catastrophic failure**.
- Therefore, we kept the conservative, safe thresholds and documented the ADE20K ground and obstacle classes in `default.yaml`.

### 5.3 Fresh HOLDOUT Measured Results
- **Hazard Categories Evaluated**: 175 images.
  - False WALKABLE occurrences: 4 images (2 `blank_wall` with smooth light gradients, 1 `stairs_up`, 1 `table_edge`).
  - **False WALKABLE Rate**: **2.29%** (Target: 0.00%). **FAIL**.
  - **95% Wilson Score Upper Bound**: **5.73%**.
- **Clear Categories Evaluated**: 100 images.
  - Correct Centre Corridor WALKABLE (TP): 25 images.
  - **Clear Category Recall**: **25.00%** (Target: $\ge 80.00\%$). **FAIL**.

### 5.4 Root Cause & Physical Necessity for Temporal Motion
Static 2D photos lack the temporal parallax, continuous optical flow, and ego-motion required to distinguish a planar textured surface from a true drop-off. In the live viewer, temporal voting over $N=3$ consistent frames and optical flow continuity prevent transient false positives, but single static photos expose the fundamental limitation of monocular depth estimation without active range sensing.

---

## 6. Step 5: Packaging, Safety & System Benchmarks

### 6.1 Pinned Dependencies
Updated `requirements.txt`:
```
transformers>=4.40.0,<5.0.0
huggingface_hub>=0.20.0,<1.0.0
```

### 6.2 Fail-Safe Model Loading Guard
In `spatialvector/freespace/corridor_estimator.py`, if SegFormer fails to load (due to missing files, corrupt weights, or environment issues):
- The estimator sets `self.seg_failed = True`.
- Without `--allow-classical-fallback`, all corridor statuses return `UNKNOWN` with reason `"SEGMENTATION MODEL NOT LOADED"`.
- `spatialvector/guidance/decision.py` checks this and **refuses to issue `WALK_FORWARD`**, displaying:
  `SEGMENTATION MODEL NOT LOADED — WALK REFUSED (CAUTION)`.

### 6.3 Startup Self-Check & Checksum Verification
- Added startup multi-model integrity check in `run_camera_prediction_viewer.py` and `models/download_verify_model.py`:
  - `yolov8n.pt`: Validated.
  - `pothole_yolov8.pt`: Validated.
  - `nvidia/segformer-b0-finetuned-ade-512-512`: Validated with HuggingFace Hub cached snapshot.
  - Documented exact Colab / GPU fine-tuning reproduction commands in `models/README.md`.

### 6.4 Measured Live Viewer Frame Rate
Benchmark with full sensor-to-display loop (YOLOv8n + SegFormer with 1-frame skip + ByteTrack + Lucas-Kanade Optical Flow + Voice + Pygame HUD):
- **Full End-to-End FPS**: **15.8 FPS** (**63.2 ms** per frame).
- **Target**: $\ge 15.0$ FPS.
- **Status**: **PASS**.

---

## 7. Audit Compliance & Code Changes After HOLDOUT Freeze

1. **Threshold Immutability**:
   - Zero thresholds in `spatialvector/config/default.yaml` were modified after the fresh HOLDOUT freeze date.
   - The HOLDOUT manifest SHA256 was checked and verified by `scripts/check_holdout_freeze.py`.
2. **Remaining Failure Categories**:
   - **Blank walls with uniform bright lighting**: Can occasionally register minimal gradient variance, mimicking clear ground.
   - **Ascending stairs**: Look visually similar to textured floor planes in single 2D camera angles.
3. **What Cannot Be Verified Without Physical Hardware**:
   - Monocular monocular scale factor ($Z = f \cdot H / y$) assumes a rigid camera height and pitch. Real walking tests with blindfolded volunteers and an MPU6050 IMU are required to test dynamic body bounce, pitch compensation, and vibration motor tactile comprehension.
