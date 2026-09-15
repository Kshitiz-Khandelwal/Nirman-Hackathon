# 🦾 SpatialVector-HMI — Predict. Navigate. Empower.

> **Nirmaan 2026 Hackathon · Healthcare & Biotech Track**

A chest-worn, vision-first local safety system that tracks nearby objects, estimates camera/user motion, **predicts future trajectory intersection**, computes collision risk, selects a safer corridor, and communicates that decision through **directional haptics**.

---

## The Problem & The Solution

![The Problem vs The Solution - SpatialVector-HMI](assets/images/spatialvector_problem_solution.jpg)

Distance is not the same as danger. Incomplete or misleading information creates real risks.

> A visually impaired person navigating with a cane gets alerted when a *wall is nearby*, even while walking parallel to it — causing unnecessary panic. Meanwhile, a fast-moving scooter approaching from behind goes **undetected** because it was never "close enough" by simple proximity metrics.

**The system must understand movement, not just proximity.**

---

## The Solution Breakdown

**SpatialVector-HMI** goes beyond "something is nearby" → it answers:

| Question | How |
|---|---|
| Is the user on a collision course? | Trajectory intersection (TTC + CPA) |
| How soon will the risk materialize? | Time-To-Collision (TTC) |
| Which direction is safer? | Safe-corridor selection (L/C/R) |
| How do we communicate with minimal cognitive load? | Directional vibration haptics |

---

## Core Thesis

> *"We do not ask only what is nearby. We estimate whether the user and the obstacle are on a collision course, how soon the risk will materialize, and which local corridor is safer."*

---

## System Overview

```
Webcam (chest-mounted)
    ↓
M01 Frame Acquisition & Timebase
    ↓
M02 Object Detection (YOLO)       ←──── IMU / Gyroscope
    ↓                                        ↓
M03 Multi-Object Tracking         M05 Ego-Motion Compensation
    ↓                                        ↓
M04 Optical Flow & FOE ──────────────────────┘
    ↓
M06 Motion & Geometry
    ↓
M07 Collision Prediction (TTC + CPA + Intersection)
    ↓
M08 Risk Engine & State Machine  →  Phone Dashboard (M11)
    ↓
M09 Safe-Corridor Selector + Haptic Policy
    ↓
M10 Arduino Haptic Interface  →  3× Vibration Motors (L/C/R)
    ↓
M12 Logger + Replay + Evaluation Harness
```

---

## Hardware Components

| Component | Description & Role |
|---|---|
| Chest-Mounted Camera / Webcam | Real-time egocentric visual sensing |
| Microcontroller (Arduino Uno) | Haptic driver & pattern controller |
| Vibration Motors (×3) | Directional tactile feedback (Left / Center / Right) |
| IMU / Gyroscope (MPU6050) | Camera rotation & body ego-motion compensation |
| Power Bank | Portable, untethered power supply |
| Chest Harness | Rigid, aligned mounting for camera & IMU |

---

## Software Stack

- **Computer Vision**: OpenCV, Ultralytics YOLO (nano/ONNX)
- **Tracking**: ByteTrack / BoT-SORT
- **Motion**: Lucas-Kanade optical flow, NumPy geometry
- **Phone Streaming**: VDO.Ninja via Playwright WebRTC headless bridge
- **Arduino**: Serial/BLE haptic protocol
- **Dashboard**: FastAPI + WebSocket → mobile browser UI
- **Logging**: JSONL session files + OpenCV video replay

---

## 🚀 Quick Start & Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Camera Source
```bash
# Copy the template to camera_source.txt
cp camera_source.example.txt camera_source.txt

# Edit camera_source.txt:
# - For VDO.Ninja phone streaming: https://vdo.ninja/?view=YOUR_ROOM_ID
# - For local webcam: 0
# - For IP camera / RTSP / DroidCam: http://192.168.1.50:8080/video
```

### 3. Launch Master System (All-in-One)
```bash
# Live mode (resolves camera from camera_source.txt, starts dashboard & pipeline)
python run.py

# Synthetic demo mode (no camera or hardware required)
python run.py --synthetic

# Explicit webcam index
python run.py --source 0
```
This single command spins up:
1. Telemetry WebSocket & Web Server on `http://localhost:8081`
2. Camera stream capture & auto-reconnect engine
3. Full Perception, Tracking, Flow, Prediction & Risk Pipeline
4. Automatically opens the interactive mobile dashboard in your browser

> **Integrity Guarantee**: The live dashboard never fabricates track/risk data — an empty or DEGRADED state always means exactly what it says. Synthetic obstacle scenarios only run in explicitly requested `--synthetic` mode.

---

## Priority Order (P0 → P3)

| Priority | Feature |
|---|---|
| **P0** | Frame capture, YOLO detection, multi-object tracking, optical flow, IMU, ego-motion, TTC/CPA, trajectory intersection, risk state machine, safe corridor, Arduino haptics, logger/replay |
| **P1** | Phone dashboard, dynamic obstacle prediction, uncertainty states, scenario modes |
| **P2** | Free-space segmentation, face detection (Social Assist only — **not** in safety path) |
| **P3** | Embedded deployment, voice/cloud (deferred) |

---

## 24-Hour Build Roadmap

| Time | Milestone |
|---|---|
| 0–2h | Smoke tests across all four roles |
| 2–4h | P0 foundations pass |
| 4–6h | Prediction works on synthetic data |
| 6–8h | Synthetic → physical haptic end-to-end |
| 8–10h | Live laptop demo core running |
| 10–12h | Demo scenarios 1 & 2 pass |
| 12–15h | Demo scenarios 3 & 4 pass |
| 15–18h | Replay is repeatable |
| 18–21h | Full system stable end-to-end |
| 21–24h | ⛔ Feature freeze — bug fixes & demo polish only |

---

## Demo Scenarios

| Scene | Physical Action | Haptic Behavior | Judge Takeaway |
|---|---|---|---|
| Baseline | Open space walk | Silent | System doesn't constantly alert |
| Parallel wall | Walk beside wall at close offset | Silent / low caution | Nearby ≠ dangerous |
| Turn toward wall | Rotate body toward obstacle | Center pulses faster | Risk changes as trajectory changes |
| Crossing person | Person crosses future path | Side motor warns | Dynamic objects predicted, not just detected |
| Safe passing | Person passes outside corridor | No warning | Same distance, different decision |
| Sensor degradation | Interrupt IMU / create low-flow scene | DEGRADED pattern | System exposes uncertainty |

---

## Non-Goals

- ❌ Certified mobility-aid status
- ❌ Facial identity in the safety path
- ❌ GPS navigation / voice assistant / cloud analytics
- ❌ Ground-level hazards (stairs, curbs) — cane/guide dog covers these
- ❌ Unvalidated testing on actual visually-impaired users (sighted blindfolded volunteers only until integration gates pass)

---

## Team (4-Person Work Breakdown)

| Person | Primary Ownership |
|---|---|
| Person 1 — Perception | M01 Frame Acquisition + M02 YOLO + M03 Tracking |
| Person 2 — Motion | M04 Optical Flow/FOE + M05 IMU/Ego Motion + M06 Geometry |
| Person 3 — Prediction | M07 TTC/CPA/Intersection + M08 Risk Engine + M09 Safe Corridor |
| Person 4 — HMI/Product | M10 Arduino + M11 Phone Dashboard + M12 Logging |

---

## Key Design Decisions

> ⚠️ **Facial recognition is NOT in the safety path.** It may exist as an optional Social Assist module (P2) after all safety features are stable — local only, opt-in, enrolled contacts only.

> ⚠️ **Phone is observational, not the safety decision maker.** All safety decisions happen on the laptop edge node. Phone connects over local Wi-Fi.

> ⚠️ **No embedded hardware deployment for the hackathon.** Laptop retains compute. Edge deployment is P3.

---

## Perception Chain (Modules M01–M03)

The perception chain forms the foundational sensing pipeline:
- **M01 — Frame Acquisition & Timebase**: Monotonic clock timestamps, dedicated capture thread, drop-oldest ring buffer, auto-reconnect.
- **M02 — Object Detection**: Ultralytics YOLOv8 nano inference, class filtering (`person`, `bicycle`, `car`, `chair`), filtered detection accounting.
- **M03 — Multi-Object Tracking**: Persistent identity tracking (`ByteTrack` or `BoT-SORT`), bounding box history (N=10), finite-difference image velocity (px/sec). Enforces forward-only data flow with zero haptic/risk coupling.

### Quickstart & Running the Pipeline

```bash
# Install dependencies
pip install ultralytics pytest opencv-python pyyaml numpy

# 1. Run live pipeline with webcam (Gate A demo)
python scripts/run_pipeline.py

# 2. Run on recorded test video (headless or GUI)
python scripts/run_pipeline.py --source tests/fixtures/test_crossing.mp4
python scripts/run_pipeline.py --source tests/fixtures/test_walking.mp4 --no-view

# 3. Swap tracker backend between ByteTrack and BoT-SORT
python scripts/run_pipeline.py --tracker bytetrack
python scripts/run_pipeline.py --tracker botsort

# 4. Verify M01 -> M02 standalone execution (no M03 dependency)
python scripts/dump_detections.py
```

### Running Perception Tests (T01 – T08)

```bash
# Run all unit tests
pytest tests/ -v

# Run individual module tests
pytest tests/test_m01_frame_source.py -v   # T01 (monotonicity), T02 (disconnect/recovery), T03 (queue bound)
pytest tests/test_m02_detector.py -v       # T04 (qualitative dump), T05 (pre-filter low-conf retention)
pytest tests/test_m03_tracker.py -v -s     # T06 (ID persistence), T07 (panning stability), T08 (benchmark)
```

### ID-Switch Benchmark Baseline (T08)

On the two-person crossing test clip (`tests/fixtures/test_crossing.mp4`):
- **Tracker backend:** `ByteTrack`
- **Frames evaluated:** 60 frames
- **Recorded ID-switch events:** `0`
- **Duplicate IDs observed:** `0` (asserted per frame)

*(Note: When swapping to `BoT-SORT` on high-ego-motion walking footage with camera rotation, evaluate whether ReID features reduce track loss under severe occlusion.)*

---

## Documentation

| Document | Description |
|---|---|
| [📄 Engineering Blueprint v2](./ENGINEERING_BLUEPRINT.md) | Full architecture, module specs, 4-person breakdown, test plan, demo script |
| [📦 Blueprint (original .docx)](./SpatialVector-HMI_Engineering_Blueprint_v2.docx) | Source engineering planning document |

---

## Motion Chain — M04 / M05 / M06 ✅

**Status:** Complete — T09–T15 passing, Gate B integration script ready.

The motion chain takes tracked objects (M03) and computes the *geometry of approach* — optical flow field, Focus of Expansion (travel direction proxy), IMU-corrected ego-motion, and per-object bearing/velocity relative to camera center.

### Modules

| Module | File | Purpose |
|--------|------|---------|
| M04 | `spatialvector/motion/optical_flow.py` | Lucas-Kanade sparse flow + RANSAC FOE estimation |
| M05a | `spatialvector/motion/imu_reader.py` | MPU-6050 serial reader (background thread) |
| M05b | `spatialvector/motion/ego_motion.py` | Gyro-based rotation subtraction from flow |
| M06 | `spatialvector/motion/geometry.py` | Per-object bearing, normalized velocity, FOE containment |

### Run the Gate B motion pipeline

```bash
# Live webcam (no IMU — DEGRADED fallback mode, which is fine for demo)
python scripts/run_motion_pipeline.py

# Against a recorded walking clip
python scripts/run_motion_pipeline.py --source tests/fixtures/test_crossing.mp4

# With real IMU (MPU-6050 on Arduino over serial)
python scripts/run_motion_pipeline.py --source 0 --imu-port COM3

# Simulate an IMU that disconnects after 5 seconds (to test fallback)
python scripts/run_motion_pipeline.py --source tests/fixtures/test_crossing.mp4 \
    --sim-imu --sim-imu-disconnect-after 5.0

# Headless (no OpenCV window — for remote/SSH use)
python scripts/run_motion_pipeline.py --source tests/fixtures/test_crossing.mp4 --no-view
```

### Run the tests

```bash
# M04 — optical flow + FOE (T09, T10, T11)
pytest tests/test_m04_optical_flow.py -v
python -u tests/test_m04_optical_flow.py    # standalone, no pytest needed

# M05 — IMU ingestion + ego-motion (T12, T13)
pytest tests/test_m05_imu.py -v
python -u tests/test_m05_imu.py

# M06 — geometry (T14, T15)
pytest tests/test_m06_geometry.py -v
python -u tests/test_m06_geometry.py

# All motion chain tests at once
pytest tests/test_m04_optical_flow.py tests/test_m05_imu.py tests/test_m06_geometry.py -v
```

### Simulating an IMU disconnect (for Gate B verification)

```bash
# Flag --sim-imu-disconnect-after N disconnects the simulated IMU after N seconds.
# You will see the status bar change from green "OK" to red "DEGRADED | FALLBACK ACTIVE".
python scripts/run_motion_pipeline.py \
    --source tests/fixtures/test_crossing.mp4 \
    --sim-imu --sim-imu-disconnect-after 5.0
```

### What `fallback_active: True` means (for M07 author)

When `MotionState.fallback_active` is `True`:
- The IMU was absent, disconnected, or its timestamp drifted beyond `imu.max_timestamp_drift_s` (50ms)
- **OR** `flow_quality` dropped below `ego_motion.fallback_flow_quality_threshold` (0.30)
- `corrected_flow` is **raw, uncorrected** flow — rotational component has NOT been subtracted
- `ego_rotation` is `(0.0, 0.0, 0.0)` — not measured, not estimated
- `ObjectGeometry.geometry_confidence` is penalized by 50% automatically (see `geometry.py`)
- **M07 must read `ego_motion.fallback_caution_widen_factor` (1.5) from config** and widen its uncertainty envelope accordingly — do not hard-code this value in M07 logic

### Current measured FOE accuracy (from T09)

Synthetic forward-zoom sequence (true FOE at image center = (320, 240)):
- Median FOE within **±20% of frame dimensions** (128px × 96px tolerance on 640×480)
- `foe_confidence` peaks > 0.10 on clean sequences
- Real-world accuracy will be lower due to gait bob — M07 should treat `foe_containment` as a **cue**, not a hard binary

**Fallback threshold (for M07 inheritance):** `ego_motion.fallback_flow_quality_threshold = 0.30` — decided during build, not at demo time.

---

## Modules M10–M12: Output, Telemetry & Evaluation Chain

### 1. Run the Full Live Demo (M01 → M12)

```bash
# Synthetic Gate C/D/E mode (No camera, no YOLO, no hardware required)
python scripts/run_full_pipeline.py --synthetic

# Live camera + simulated IMU + simulated Arduino + Phone Dashboard
python scripts/run_full_pipeline.py --sim-imu --sim-arduino

# With physical Arduino and IMU
python scripts/run_full_pipeline.py --imu-port COM3 --arduino-port COM4
```

### 2. Phone Telemetry Dashboard (M11)
Open your phone browser on the same Wi-Fi network and navigate to:
```text
http://<laptop-ip>:8080/
```
- **Real-Time Visuals**: Displays current state (`SAFE`, `CAUTION`, `WARNING`, `CRITICAL`, `DEGRADED`), numeric risk score `0.000`–`1.000`, 3-motor actuation ripples, and corridor risk bars.
- **Risk Explanation**: Shows human-readable `reason_codes` (e.g. `ttc_low:1.8s`, `intersection:track_4`).
- **Client-Side Staleness Watchdog (Section 0)**: The dashboard autonomously monitors update timestamps. If no telemetry message is received within **1.5 seconds**, the phone independently trips into a flashing `DISCONNECTED / PIPELINE STALLED` alert, ensuring observers never mistake a frozen pipeline for a clear scene.

### 3. Proving M11 Removability (Safety Independence)
Run the pipeline with `--no-telemetry`:
```bash
python scripts/run_full_pipeline.py --synthetic --no-telemetry
```
The safety loop and M10 haptic motors execute at 100% capacity with zero dependency on the telemetry server.

### 4. M12 Session Recording & Deterministic Replay
Sessions are automatically recorded to `sessions/<session_id>/session.jsonl` with schema versioning.
To replay a session offline through the decision chain:
```bash
python -c "from spatialvector.hmi.replay import SessionReplayer; rep = SessionReplayer('sessions/<session_id>/session.jsonl'); res = rep.run_replay(); print(res['state_distribution'])"
```
Replays run with **100% determinism (T32)** and allow offline A/B evaluation of risk-engine weights without live re-recording.

### 5. Benchmark Metrics & Watchdog Timings
- **Telemetry Transport Latency (T30)**: Benchmarked at **~10–14ms** average over local WebSocket.
- **Arduino Hardware Watchdog**: **500ms** timeout (firmware zeroes motors autonomously if laptop stalls).
- **Client Staleness Watchdog**: **1500ms** threshold on phone dashboard.


---

## Research References

| Paper | Relevance |
|---|---|
| [**Pedestrian Detection with Wearable Cameras for the Blind: A Two-way Perspective**](https://pmc.ncbi.nlm.nih.gov/articles/PMC7423406/) — Lee et al., CHI 2020 · PMC7423406 | Privacy/social-acceptance tensions of always-on wearable cameras; both user and bystander perspectives; directly informs our privacy-first design decisions (no raw video to cloud, no identity in safety path) |
| [Shared privacy concerns — Microsoft Research](https://www.microsoft.com/en-us/research/?p=1121952) | Shared concerns about AI fallibility and facial-recognition errors |
| [Assistive IoT device with face recognition](https://doi.org/10.1080/17483107.2025.2582033) | Confirms feature combination exists in research; reinforces our differentiation via prediction intelligence |
| [SmartCane — IIT Delhi](https://assistech.iitd.ernet.in/smartcane.php) | Obstacle sensing + tactile HMI precedent |
| [WeWALK](https://support.wewalk.io/en/article/customizing-obstacle-detection-settings-through-the-smart-cane-2/) | "Sensor + vibration" alone is not sufficient differentiation |
| [Ultralytics Tracking Docs](https://docs.ultralytics.com/modes/track) | ByteTrack / BoT-SORT tracker selection guidance |

---

## Competitive Positioning

| Existing Direction | What It Does | SpatialVector Differentiation |
|---|---|---|
| Traditional/smart cane | Proximity detection + vibration | **Predictive trajectory intersection**, not proximity only |
| Wearable AI vision | Object/person understanding | **Temporal motion + collision geometry** as core safety decision |
| Multi-feature assistive devices | Detection + face recognition + feedback | No identity in core; **collision intelligence** is the story |
| LiDAR wearables | Spatial awareness + alerts | Vision-first, **low-cost prototype** |

---

*Technology for a more independent tomorrow.*

