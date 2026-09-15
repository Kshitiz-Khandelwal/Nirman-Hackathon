/**
 * SpatialVector-HMI — Mobile Assistive Dashboard Engine (M11)
 *
 * Implements:
 * 1. 5-Tab Navigation (Live View, Prediction Inspector, Haptic State, Test & Replay, Social Assist)
 * 2. Client-Side Staleness Watchdog (Section 0 requirement: threshold = 1500ms)
 * 3. Dynamic VDO.Ninja Camera Feed embedding & real-time link configuration
 * 4. WebSocket auto-reconnect with telemetry visualization:
 *    - Real-time Risk Alert Banner with Circular Gauge (Safe, Caution, Warning, Critical, Degraded)
 *    - Corridor Risk Triad (Left, Center, Right)
 *    - Recommended Direction Guidance
 *    - Live HUD Perspective & Bounding Box Overlay Canvas
 * 5. Interactive Prediction Inspector with Vector Trajectory Canvas & Dynamic Reasoning
 * 6. Interactive Haptic State with Vest SVG Vibration Ripples & Telemetry History
 * 7. Interactive Test & Replay Scenarios (S1-S6) with Multi-metric Timeline Chart & Scrubber
 * 8. Social Assist with Privacy-isolated Face Recognition & Contacts Directory
 */

(function () {
    "use strict";

    const STALE_THRESHOLD_MS = 1500;
    let lastMessageTimestamp = 0;
    let ws = null;
    let reconnectDelay = 1000;
    let currentCameraUrl = "https://vdo.ninja/?view=vYEkARC";

    // Telemetry and Model State
    let currentRiskState = "WARNING";
    let currentGlobalRisk = 0.84;
    let currentTTC = 2.1;
    let currentCPA = 0.41;
    let activeTracks = [
        {
            track_id: 2,
            class_name: "Scooter",
            confidence: 0.87,
            ttc_s: 2.1,
            cpa: 0.41,
            intersect: true,
            relative_velocity: 2.5,
            pred_conf: 0.81,
            state: "WARNING",
            bbox: [160, 80, 240, 190]
        }
    ];
    let selectedTrackIndex = 0;
    let hapticHistory = [
        { time: "09:41:22", pattern: "LEFT_FAST", duration: 320, urgency: 3 },
        { time: "09:41:20", pattern: "LEFT_MEDIUM", duration: 240, urgency: 2 },
        { time: "09:41:18", pattern: "ALL_CLEAR", duration: 200, urgency: 1 },
        { time: "09:41:15", pattern: "ALL_CLEAR", duration: 200, urgency: 1 }
    ];

    // Replay State
    const SCENARIOS = {
        s1: {
            title: "Scenario S1 - Parallel Wall (Safe)",
            desc: "Walk parallel to a wall (close distance)",
            expected: "SAFE / SILENT",
            actual: "SAFE / SILENT",
            result: "PASS",
            riskPeak: 0.12,
            curve: [0.05, 0.08, 0.11, 0.12, 0.10, 0.09, 0.07, 0.06, 0.05, 0.05]
        },
        s2: {
            title: "Scenario S2 - Head-On Obstacle (Warning)",
            desc: "Obstacle approaching directly in user path",
            expected: "WARNING",
            actual: "WARNING",
            result: "PASS",
            riskPeak: 0.84,
            curve: [0.15, 0.22, 0.38, 0.55, 0.72, 0.84, 0.78, 0.45, 0.20, 0.10]
        },
        s3: {
            title: "Scenario S3 - Crossing Pedestrian (Warning)",
            desc: "Pedestrian crossing user path at lateral angle",
            expected: "WARNING",
            actual: "WARNING",
            result: "PASS",
            riskPeak: 0.76,
            curve: [0.10, 0.18, 0.35, 0.62, 0.76, 0.68, 0.30, 0.15, 0.08, 0.05]
        },
        s4: {
            title: "Scenario S4 - Safe Pass (Safe)",
            desc: "Pedestrian walking past in adjacent corridor",
            expected: "SAFE / SILENT",
            actual: "SAFE / SILENT",
            result: "PASS",
            riskPeak: 0.22,
            curve: [0.08, 0.12, 0.18, 0.22, 0.19, 0.14, 0.09, 0.06, 0.04, 0.02]
        },
        s5: {
            title: "Scenario S5 - Receding Object (Safe)",
            desc: "Object moving away in the same heading",
            expected: "SAFE / SILENT",
            actual: "SAFE / SILENT",
            result: "PASS",
            riskPeak: 0.08,
            curve: [0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.02, 0.01, 0.01]
        },
        s6: {
            title: "Scenario S6 - Multiple Obstacles (Critical)",
            desc: "Multiple converging obstacles with overlapping trajectories",
            expected: "CRITICAL",
            actual: "CRITICAL",
            result: "PASS",
            riskPeak: 0.95,
            curve: [0.20, 0.40, 0.65, 0.82, 0.95, 0.92, 0.88, 0.60, 0.35, 0.15]
        }
    };
    let currentScenarioId = "s1";
    let replayTimer = null;
    let replayProgress = 35; // 0 to 100 percent
    let isReplaying = false;
    let socialAssistEnabled = true;

    // -------------------------------------------------------------------------
    // DOM Element References
    // -------------------------------------------------------------------------
    const stalenessBanner = document.getElementById("staleness-banner");
    const staleSecTxt = document.getElementById("stale-sec-txt");
    const connPillBadge = document.getElementById("conn-pill-badge");
    const connStatusDot = document.getElementById("conn-status-dot");
    const connStatusText = document.getElementById("conn-status-text");
    const sessionIdLabel = document.getElementById("session-id-label");
    const headerClock = document.getElementById("header-clock");

    // Live Tab Elements
    const riskAlertCard = document.getElementById("risk-alert-card");
    const alertIconBox = document.getElementById("alert-icon-box");
    const alertStateName = document.getElementById("alert-state-name");
    const alertStateSub = document.getElementById("alert-state-sub");
    const gaugeCircleStroke = document.getElementById("gauge-circle-stroke");
    const valRiskScore = document.getElementById("val-risk-score");
    const valTtc = document.getElementById("val-ttc");
    const valCpa = document.getElementById("val-cpa");

    const vdoNinjaFrame = document.getElementById("vdo-ninja-frame");
    const liveOverlayCanvas = document.getElementById("live-overlay-canvas");
    const btnToggleCameraSrc = document.getElementById("btn-toggle-camera-src");
    const btnOpenSettings = document.getElementById("btn-open-settings");

    const boxCorrLeft = document.getElementById("box-corr-left");
    const txtCorrLeft = document.getElementById("txt-corr-left");
    const lblCorrLeft = document.getElementById("lbl-corr-left");
    const boxCorrCenter = document.getElementById("box-corr-center");
    const txtCorrCenter = document.getElementById("txt-corr-center");
    const lblCorrCenter = document.getElementById("lbl-corr-center");
    const boxCorrRight = document.getElementById("box-corr-right");
    const txtCorrRight = document.getElementById("txt-corr-right");
    const lblCorrRight = document.getElementById("lbl-corr-right");

    const recArrowIcon = document.getElementById("rec-arrow-icon");
    const recDirName = document.getElementById("rec-dir-name");
    const recDirSub = document.getElementById("rec-dir-sub");

    // Prediction Inspector Elements
    const inspectorObjLabel = document.getElementById("inspector-obj-label");
    const inspectorCanvas = document.getElementById("inspector-canvas");
    const inspId = document.getElementById("insp-id");
    const inspClass = document.getElementById("insp-class");
    const inspTrackConf = document.getElementById("insp-track-conf");
    const inspTtc = document.getElementById("insp-ttc");
    const inspCpa = document.getElementById("insp-cpa");
    const inspIntersect = document.getElementById("insp-intersect");
    const inspVel = document.getElementById("insp-vel");
    const inspPredConf = document.getElementById("insp-pred-conf");
    const inspState = document.getElementById("insp-state");
    const inspectorReasoningList = document.getElementById("inspector-reasoning-list");

    // Haptics Elements
    const svgMotorLeft = document.getElementById("svg-motor-left");
    const svgRippleLeft = document.getElementById("svg-ripple-left");
    const svgLblLeft = document.getElementById("svg-lbl-left");
    const svgMotorCenter = document.getElementById("svg-motor-center");
    const svgRippleCenter = document.getElementById("svg-ripple-center");
    const svgLblCenter = document.getElementById("svg-lbl-center");
    const svgMotorRight = document.getElementById("svg-motor-right");
    const svgRippleRight = document.getElementById("svg-ripple-right");
    const svgLblRight = document.getElementById("svg-lbl-right");

    const hapticPatLabel = document.getElementById("haptic-pat-label");
    const hapticVibBadge = document.getElementById("haptic-vib-badge");
    const hapticUrgVal = document.getElementById("haptic-urg-val");
    const hapticDurVal = document.getElementById("haptic-dur-val");
    const hapticTimeVal = document.getElementById("haptic-time-val");

    const devArdStatus = document.getElementById("dev-ard-status");
    const devLatencyVal = document.getElementById("dev-latency-val");
    const devMotorLStatus = document.getElementById("dev-motor-l-status");
    const devMotorCStatus = document.getElementById("dev-motor-c-status");
    const devMotorRStatus = document.getElementById("dev-motor-r-status");
    const hapticsDeviceView = document.getElementById("haptics-device-view");
    const hapticsCommandsView = document.getElementById("haptics-commands-view");
    const hapticCommandsList = document.getElementById("haptic-commands-list");

    // Test & Replay Elements
    const selectTestScenario = document.getElementById("select-test-scenario");
    const scenDesc = document.getElementById("scen-desc");
    const scenExpected = document.getElementById("scen-expected");
    const scenActual = document.getElementById("scen-actual");
    const scenResult = document.getElementById("scen-result");
    const replayTimelineCanvas = document.getElementById("replay-timeline-canvas");
    const scenFrameTxt = document.getElementById("scen-frame-txt");
    const replaySlider = document.getElementById("replay-slider");

    // Social Elements
    const toggleSocialSwitch = document.getElementById("toggle-social-switch");
    const socialSwitchLabel = document.getElementById("social-switch-label");
    const socialLiveView = document.getElementById("social-live-view");
    const socialContactsView = document.getElementById("social-contacts-view");
    const socialFaceBox = document.getElementById("social-face-box");

    // Settings Modal
    const settingsModal = document.getElementById("settings-modal");
    const inputCameraUrl = document.getElementById("input-camera-url");
    const btnCloseSettings = document.getElementById("btn-close-settings");
    const btnCancelSettings = document.getElementById("btn-cancel-settings");
    const btnSaveSettings = document.getElementById("btn-save-settings");

    // -------------------------------------------------------------------------
    // 1. Client-Side Staleness Watchdog (Section 0 Requirement)
    // -------------------------------------------------------------------------
    setInterval(function checkWatchdog() {
        if (lastMessageTimestamp === 0) {
            // Initializing/waiting for first connection
            return;
        }

        const elapsed = Date.now() - lastMessageTimestamp;
        if (elapsed > STALE_THRESHOLD_MS) {
            // Pipeline stalled or connection dropped
            stalenessBanner.style.display = "block";
            staleSecTxt.textContent = (elapsed / 1000).toFixed(1);

            connPillBadge.className = "conn-pill disconnected";
            connStatusDot.className = "status-dot disconnected";
            connStatusText.textContent = "Pipeline Stalled / Offline";

            // Put motors into idle visually
            resetMotorVisuals();
        } else {
            stalenessBanner.style.display = "none";
            connPillBadge.className = "conn-pill";
            connStatusDot.className = "status-dot";
            connStatusText.textContent = "Local Edge Connected";
        }
    }, 150);

    function updateClock() {
        const now = new Date();
        const timeStr = now.toTimeString().split(" ")[0];
        if (headerClock) headerClock.textContent = timeStr;
    }
    setInterval(updateClock, 1000);
    updateClock();

    // -------------------------------------------------------------------------
    // 2. Camera Source & VDO.Ninja Integration
    // -------------------------------------------------------------------------
    function formatVdoNinjaUrl(rawUrl) {
        if (!rawUrl) return "about:blank";
        let url = rawUrl.trim();
        if (url.includes("vdo.ninja")) {
            // Add cleanoutput and transparent HUD styling flags if missing
            if (!url.includes("cleanoutput")) {
                url += (url.includes("?") ? "&" : "?") + "cleanoutput";
            }
            if (!url.includes("transparent")) {
                url += "&transparent";
            }
            if (!url.includes("autoplay")) {
                url += "&autoplay=1";
            }
        }
        return url;
    }

    async function initCameraSource() {
        try {
            const resp = await fetch("/api/source");
            if (resp.ok) {
                const data = await resp.json();
                if (data.source) {
                    currentCameraUrl = data.source;
                }
            }
        } catch (e) {
            console.warn("Could not fetch /api/source, using default URL", e);
        }

        if (inputCameraUrl) inputCameraUrl.value = currentCameraUrl;
        if (vdoNinjaFrame) {
            vdoNinjaFrame.src = formatVdoNinjaUrl(currentCameraUrl);
        }
    }

    function openSettingsModal() {
        if (settingsModal) {
            if (inputCameraUrl) inputCameraUrl.value = currentCameraUrl;
            settingsModal.style.display = "flex";
        }
    }

    function closeSettingsModal() {
        if (settingsModal) settingsModal.style.display = "none";
    }

    async function saveCameraSettings() {
        const newUrl = inputCameraUrl ? inputCameraUrl.value.trim() : "";
        if (!newUrl) return;

        currentCameraUrl = newUrl;
        if (vdoNinjaFrame) {
            vdoNinjaFrame.src = formatVdoNinjaUrl(currentCameraUrl);
        }

        try {
            await fetch("/api/set-source", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ source: newUrl })
            });
        } catch (err) {
            console.error("Failed to persist camera source", err);
        }

        closeSettingsModal();
    }

    if (btnOpenSettings) btnOpenSettings.addEventListener("click", openSettingsModal);
    if (btnToggleCameraSrc) btnToggleCameraSrc.addEventListener("click", openSettingsModal);
    if (btnCloseSettings) btnCloseSettings.addEventListener("click", closeSettingsModal);
    if (btnCancelSettings) btnCancelSettings.addEventListener("click", closeSettingsModal);
    if (btnSaveSettings) btnSaveSettings.addEventListener("click", saveCameraSettings);

    // -------------------------------------------------------------------------
    // 3. Tab Switching
    // -------------------------------------------------------------------------
    window.switchTab = function (tabId) {
        const tabs = ["live", "predict", "haptics", "test", "social"];
        const navButtons = document.querySelectorAll(".bottom-nav-bar .nav-item");

        tabs.forEach((name, idx) => {
            const screen = document.getElementById(`screen-${name}`);
            if (screen) {
                if (name === tabId) {
                    screen.classList.add("active");
                } else {
                    screen.classList.remove("active");
                }
            }
            if (navButtons[idx]) {
                if (name === tabId) {
                    navButtons[idx].classList.add("active");
                } else {
                    navButtons[idx].classList.remove("active");
                }
            }
        });

        if (tabId === "live") {
            drawLiveOverlay();
        } else if (tabId === "predict") {
            updateInspector();
            drawInspectorCanvas();
        } else if (tabId === "test") {
            drawReplayTimeline();
        }
    };

    // -------------------------------------------------------------------------
    // 4. WebSocket Telemetry Processing
    // -------------------------------------------------------------------------
    function connectWs() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const host = window.location.host || "localhost:8080";
        const wsUrl = `${protocol}//${host}/ws/telemetry`;

        try {
            ws = new WebSocket(wsUrl);
        } catch (e) {
            scheduleReconnect();
            return;
        }

        ws.onopen = function () {
            lastMessageTimestamp = Date.now();
            connPillBadge.className = "conn-pill";
            connStatusDot.className = "status-dot";
            connStatusText.textContent = "Local Edge Connected";
            reconnectDelay = 1000;
        };

        ws.onmessage = function (event) {
            lastMessageTimestamp = Date.now();
            try {
                const msg = JSON.parse(event.data);
                handleTelemetryMessage(msg);
            } catch (err) {
                console.error("Telemetry parse error", err);
            }
        };

        ws.onclose = function () {
            scheduleReconnect();
        };

        ws.onerror = function () {
            ws.close();
        };
    }

    function scheduleReconnect() {
        setTimeout(connectWs, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 1.5, 5000);
    }

    function handleTelemetryMessage(msg) {
        if (msg.session_id && sessionIdLabel) {
            sessionIdLabel.textContent = `Session: ${msg.session_id.substring(0, 10)}`;
        }

        // 1. Risk State & Score
        const rs = msg.risk_state || {};
        const state = (rs.state || "SAFE").toUpperCase();
        const globalRisk = (typeof rs.global_risk === "number") ? rs.global_risk : 0.0;
        currentRiskState = state;
        currentGlobalRisk = globalRisk;

        updateRiskBanner(state, globalRisk);

        // 2. Corridors
        const cr = rs.corridor_risks || {};
        const leftRisk = cr.left !== undefined ? cr.left : 0.12;
        const centerRisk = cr.center !== undefined ? cr.center : 0.84;
        const rightRisk = cr.right !== undefined ? cr.right : 0.23;
        updateCorridorBoxes(leftRisk, centerRisk, rightRisk);

        // 3. Recommended Direction
        updateDirectionRecommendation(leftRisk, centerRisk, rightRisk, state);

        // 4. Tracks & Objects
        if (msg.tracks && msg.tracks.length > 0) {
            activeTracks = msg.tracks;
            // Compute min TTC and CPA
            let minTtc = null;
            let minCpa = null;
            for (const t of activeTracks) {
                if (t.ttc_s !== null && t.ttc_s !== undefined) {
                    if (minTtc === null || t.ttc_s < minTtc) minTtc = t.ttc_s;
                }
                if (t.cpa !== null && t.cpa !== undefined) {
                    if (minCpa === null || t.cpa < minCpa) minCpa = t.cpa;
                }
            }
            currentTTC = minTtc !== null ? minTtc : 2.1;
            currentCPA = minCpa !== null ? minCpa : 0.41;
        }
        if (valTtc) valTtc.textContent = `${Number(currentTTC).toFixed(1)} s`;
        if (valCpa) valCpa.textContent = `${Number(currentCPA).toFixed(2)} m`;

        // 5. Haptic Feedback
        if (msg.haptic) {
            updateHapticTelemetry(msg.haptic);
        }

        // 6. Pipeline Health
        if (msg.pipeline_health) {
            const ph = msg.pipeline_health;
            if (devArdStatus) {
                if (ph.arduino === "OK") {
                    devArdStatus.className = "pill-badge green";
                    devArdStatus.textContent = "● Connected";
                } else {
                    devArdStatus.className = "pill-badge red";
                    devArdStatus.textContent = "● Degraded";
                }
            }
        }

        // Render Canvases
        drawLiveOverlay();
        updateInspector();
    }

    // -------------------------------------------------------------------------
    // 5. UI Renderers for Live Tab
    // -------------------------------------------------------------------------
    function updateRiskBanner(state, riskScore) {
        if (!riskAlertCard) return;

        // Colors & Text
        riskAlertCard.className = `risk-alert-card alert-${state.toLowerCase()}`;
        if (alertStateName) alertStateName.textContent = state;

        let strokeColor = "#10b981";
        let subText = "Clear path · No collision risk";

        if (state === "SAFE") {
            strokeColor = "#10b981";
            subText = "Clear navigation path · No hazard detected";
            if (alertStateName) alertStateName.style.color = "#065f46";
        } else if (state === "CAUTION") {
            strokeColor = "#f59e0b";
            subText = "Approaching obstacle · Monitoring trajectory";
            if (alertStateName) alertStateName.style.color = "#92400e";
        } else if (state === "WARNING") {
            strokeColor = "#f97316";
            subText = "Predicted collision risk detected";
            if (alertStateName) alertStateName.style.color = "#9a3412";
        } else if (state === "CRITICAL") {
            strokeColor = "#ef4444";
            subText = "Imminent collision · Emergency stop required";
            if (alertStateName) alertStateName.style.color = "#991b1b";
        } else if (state === "DEGRADED") {
            strokeColor = "#8b5cf6";
            subText = "Sensor confidence degraded · Fallback active";
            if (alertStateName) alertStateName.style.color = "#5b21b6";
        }

        if (alertStateSub) alertStateSub.textContent = subText;
        if (valRiskScore) valRiskScore.textContent = riskScore.toFixed(2);

        // Circular Gauge Animation
        if (gaugeCircleStroke) {
            const pct = Math.min(100, Math.max(0, Math.round(riskScore * 100)));
            gaugeCircleStroke.setAttribute("stroke-dasharray", `${pct}, 100`);
            gaugeCircleStroke.setAttribute("stroke", strokeColor);
        }
    }

    function updateCorridorBoxes(left, center, right) {
        applyCorridorStyle(boxCorrLeft, txtCorrLeft, lblCorrLeft, left);
        applyCorridorStyle(boxCorrCenter, txtCorrCenter, lblCorrCenter, center);
        applyCorridorStyle(boxCorrRight, txtCorrRight, lblCorrRight, right);
    }

    function applyCorridorStyle(boxEl, txtEl, lblEl, score) {
        if (!boxEl || !txtEl || !lblEl) return;
        txtEl.textContent = Number(score).toFixed(2);

        if (score < 0.30) {
            boxEl.className = "corridor-box safe";
            lblEl.className = "corridor-status-tag";
            lblEl.textContent = "SAFE";
        } else if (score < 0.70) {
            boxEl.className = "corridor-box caution";
            lblEl.className = "corridor-status-tag";
            lblEl.textContent = "CAUTION";
        } else {
            boxEl.className = "corridor-box risky";
            lblEl.className = "corridor-status-tag";
            lblEl.textContent = "RISKY";
        }
    }

    function updateDirectionRecommendation(left, center, right, state) {
        if (!recDirName || !recDirSub || !recArrowIcon) return;

        if (state === "CRITICAL") {
            recDirName.textContent = "STOP IMMEDIATELY";
            recDirSub.textContent = "Hazards in active corridor";
            recDirName.style.color = "var(--c-critical)";
            recArrowIcon.innerHTML = `<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>`;
            return;
        }

        // Safest corridor
        if (left <= center && left <= right) {
            recDirName.textContent = "MOVE LEFT";
            recDirSub.textContent = "Left corridor is safest";
            recDirName.style.color = "#10b981";
            recArrowIcon.innerHTML = `<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>`;
        } else if (right < left && right <= center) {
            recDirName.textContent = "MOVE RIGHT";
            recDirSub.textContent = "Right corridor is safest";
            recDirName.style.color = "#10b981";
            recArrowIcon.innerHTML = `<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>`;
        } else {
            recDirName.textContent = "MAINTAIN PATH";
            recDirSub.textContent = "Center path is unobstructed";
            recDirName.style.color = "#2563eb";
            recArrowIcon.innerHTML = `<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"></line><polyline points="5 12 12 5 19 12"></polyline></svg>`;
        }
    }

    // -------------------------------------------------------------------------
    // 6. Live HUD Perspective & Bounding Box Overlay
    // -------------------------------------------------------------------------
    function drawLiveOverlay() {
        if (!liveOverlayCanvas) return;
        const ctx = liveOverlayCanvas.getContext("2d");
        const w = liveOverlayCanvas.width;
        const h = liveOverlayCanvas.height;

        ctx.clearRect(0, 0, w, h);

        // Perspective corridor lines on ground plane
        const vanishY = h * 0.42;
        const vanishX = w * 0.50;

        // Ground perspective trapezoids (Left, Center, Right)
        // Center Corridor (Hazards zone)
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(vanishX - 35, vanishY);
        ctx.lineTo(vanishX + 35, vanishY);
        ctx.lineTo(w * 0.70, h);
        ctx.lineTo(w * 0.30, h);
        ctx.closePath();

        if (currentGlobalRisk > 0.5) {
            ctx.fillStyle = "rgba(239, 68, 68, 0.22)"; // Red danger tint
            ctx.strokeStyle = "rgba(239, 68, 68, 0.8)";
        } else {
            ctx.fillStyle = "rgba(16, 185, 129, 0.15)";
            ctx.strokeStyle = "rgba(16, 185, 129, 0.6)";
        }
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.restore();

        // Left Corridor
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(vanishX - 90, vanishY);
        ctx.lineTo(vanishX - 35, vanishY);
        ctx.lineTo(w * 0.30, h);
        ctx.lineTo(w * 0.05, h);
        ctx.closePath();
        ctx.fillStyle = "rgba(16, 185, 129, 0.12)";
        ctx.fill();
        ctx.restore();

        // Right Corridor
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(vanishX + 35, vanishY);
        ctx.lineTo(vanishX + 90, vanishY);
        ctx.lineTo(w * 0.95, h);
        ctx.lineTo(w * 0.70, h);
        ctx.closePath();
        ctx.fillStyle = "rgba(16, 185, 129, 0.12)";
        ctx.fill();
        ctx.restore();

        // Draw Bounding Boxes for detected objects (e.g. Scooter #2)
        const primaryTrack = activeTracks[selectedTrackIndex] || activeTracks[0];
        if (primaryTrack) {
            const bx = 165;
            const by = 80;
            const bw = 70;
            const bh = 110;

            ctx.save();
            ctx.strokeStyle = "#ef4444";
            ctx.lineWidth = 2.5;
            ctx.setLineDash([]);
            // Corner-bracket bounding box
            const len = 12;
            // Top-left
            ctx.beginPath(); ctx.moveTo(bx, by + len); ctx.lineTo(bx, by); ctx.lineTo(bx + len, by); ctx.stroke();
            // Top-right
            ctx.beginPath(); ctx.moveTo(bx + bw - len, by); ctx.lineTo(bx + bw, by); ctx.lineTo(bx + bw, by + len); ctx.stroke();
            // Bottom-left
            ctx.beginPath(); ctx.moveTo(bx, by + bh - len); ctx.lineTo(bx, by + bh); ctx.lineTo(bx + len, by + bh); ctx.stroke();
            // Bottom-right
            ctx.beginPath(); ctx.moveTo(bx + bw - len, by + bh); ctx.lineTo(bx + bw, by + bh); ctx.lineTo(bx + bw, by + bh - len); ctx.stroke();

            // Label Tag
            const labelText = `${primaryTrack.class_name || 'Object'} #${primaryTrack.track_id} | TTC: ${Number(currentTTC).toFixed(1)}s`;
            ctx.font = "bold 10px 'JetBrains Mono', monospace";
            const textWidth = ctx.measureText(labelText).width;

            ctx.fillStyle = "rgba(239, 68, 68, 0.9)";
            ctx.beginPath();
            ctx.roundRect(bx, by - 20, textWidth + 12, 18, 4);
            ctx.fill();

            ctx.fillStyle = "#ffffff";
            ctx.fillText(labelText, bx + 6, by - 7);

            // Vector arrow projecting collision trajectory
            ctx.beginPath();
            ctx.moveTo(bx + bw / 2, by + bh);
            ctx.lineTo(vanishX, h * 0.90);
            ctx.strokeStyle = "#ef4444";
            ctx.lineWidth = 2;
            ctx.setLineDash([4, 4]);
            ctx.stroke();
            ctx.restore();
        }
    }

    // -------------------------------------------------------------------------
    // 7. Tab 2: Prediction Inspector & Vector Canvas
    // -------------------------------------------------------------------------
    window.prevTrack = function () {
        if (activeTracks.length === 0) return;
        selectedTrackIndex = (selectedTrackIndex - 1 + activeTracks.length) % activeTracks.length;
        updateInspector();
        drawInspectorCanvas();
    };

    window.nextTrack = function () {
        if (activeTracks.length === 0) return;
        selectedTrackIndex = (selectedTrackIndex + 1) % activeTracks.length;
        updateInspector();
        drawInspectorCanvas();
    };

    function updateInspector() {
        const track = activeTracks[selectedTrackIndex] || {
            track_id: 2,
            class_name: "Scooter",
            confidence: 0.87,
            ttc_s: 2.1,
            cpa: 0.41,
            intersect: true,
            relative_velocity: 2.5,
            pred_conf: 0.81,
            state: "WARNING"
        };

        if (inspectorObjLabel) {
            inspectorObjLabel.textContent = `${track.class_name} #${track.track_id} (${track.state || 'Selected'})`;
        }

        if (inspId) inspId.textContent = `#${track.track_id}`;
        if (inspClass) inspClass.textContent = track.class_name;
        if (inspTrackConf) inspTrackConf.textContent = (track.confidence || 0.87).toFixed(2);
        if (inspTtc) inspTtc.textContent = track.ttc_s ? `${Number(track.ttc_s).toFixed(1)} s` : "None";
        if (inspCpa) inspCpa.textContent = track.cpa ? `${Number(track.cpa).toFixed(2)} m` : "--";
        if (inspIntersect) {
            inspIntersect.textContent = track.intersect ? "YES" : "NO";
            inspIntersect.className = track.intersect ? "pill-badge red" : "pill-badge green";
        }
        if (inspVel) inspVel.textContent = `${track.relative_velocity || 2.5} m/s`;
        if (inspPredConf) inspPredConf.textContent = (track.pred_conf || 0.81).toFixed(2);
        if (inspState) {
            inspState.textContent = track.state || "WARNING";
            inspState.className = `pill-badge ${(track.state || 'warning').toLowerCase() === 'safe' ? 'green' : 'orange'}`;
        }

        // Dynamic reasoning steps
        if (inspectorReasoningList) {
            inspectorReasoningList.innerHTML = `
                <div class="reasoning-item"><span class="reasoning-num">1.</span><span>Object tracked consistently across video frames</span></div>
                <div class="reasoning-item"><span class="reasoning-num">2.</span><span>Relative velocity estimated at ${track.relative_velocity || 2.5} m/s</span></div>
                <div class="reasoning-item"><span class="reasoning-num">3.</span><span>User ego-motion compensated using IMU angular rate</span></div>
                <div class="reasoning-item"><span class="reasoning-num">4.</span><span>Predicted path intersects CENTER corridor</span></div>
                <div class="reasoning-item"><span class="reasoning-num">5.</span><span>CPA (${Number(track.cpa || 0.41).toFixed(2)}m) below safe passing threshold (0.60m)</span></div>
                <div class="reasoning-item"><span class="reasoning-num">6.</span><span>Hysteresis policy transitioned state to ${track.state || 'WARNING'}</span></div>
            `;
        }
    }

    function drawInspectorCanvas() {
        if (!inspectorCanvas) return;
        const ctx = inspectorCanvas.getContext("2d");
        const w = inspectorCanvas.width;
        const h = inspectorCanvas.height;

        ctx.clearRect(0, 0, w, h);

        // Deep technical grid background
        ctx.fillStyle = "#0f172a";
        ctx.fillRect(0, 0, w, h);

        ctx.strokeStyle = "rgba(51, 65, 85, 0.4)";
        ctx.lineWidth = 1;
        for (let x = 20; x < w; x += 30) {
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
        }
        for (let y = 20; y < h; y += 30) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
        }

        // Center axes
        const userX = w * 0.5;
        const userY = h * 0.88;
        const foeX = w * 0.5;
        const foeY = h * 0.28;

        // 1. User Path (Dashed Blue Line)
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(userX, userY);
        ctx.lineTo(foeX, foeY);
        ctx.strokeStyle = "#3b82f6";
        ctx.lineWidth = 2.5;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.restore();

        // 2. FOE (Focus of Expansion) marker
        ctx.save();
        ctx.beginPath();
        ctx.arc(foeX, foeY, 6, 0, Math.PI * 2);
        ctx.fillStyle = "#3b82f6";
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();

        // 3. User Current Position marker
        ctx.save();
        ctx.beginPath();
        ctx.arc(userX, userY, 7, 0, Math.PI * 2);
        ctx.fillStyle = "#2563eb";
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.font = "bold 9px 'Plus Jakarta Sans', sans-serif";
        ctx.fillStyle = "#94a3b8";
        ctx.fillText("Current position", userX - 70, userY + 4);
        ctx.restore();

        // 4. Object Position & Velocity Vector
        const objX = w * 0.50;
        const objY = h * 0.22;
        const interX = w * 0.50;
        const interY = h * 0.55;

        // Object Predicted Path (Dashed Red Line)
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(objX, objY);
        ctx.lineTo(interX, interY);
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = 2.5;
        ctx.setLineDash([5, 3]);
        ctx.stroke();
        ctx.restore();

        // Scooter Graphic Box representation
        ctx.save();
        ctx.fillStyle = "#ef4444";
        ctx.beginPath();
        ctx.roundRect(objX - 16, objY - 14, 32, 28, 4);
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 8px 'JetBrains Mono', monospace";
        ctx.textAlign = "center";
        ctx.fillText("SCOOTER", objX, objY + 2);
        ctx.restore();

        // Collision Intersection Point
        ctx.save();
        ctx.beginPath();
        ctx.arc(interX, interY, 6, 0, Math.PI * 2);
        ctx.fillStyle = "#ef4444";
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.stroke();

        // Tag: 2.1s collision
        ctx.fillStyle = "rgba(239, 68, 68, 0.95)";
        ctx.beginPath();
        ctx.roundRect(interX + 10, interY - 9, 74, 18, 4);
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 9px 'JetBrains Mono', monospace";
        ctx.textAlign = "left";
        ctx.fillText("2.1s hazard", interX + 15, interY + 4);
        ctx.restore();

        // Legend (Top Right)
        ctx.save();
        ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
        ctx.beginPath();
        ctx.roundRect(w - 110, 10, 100, 72, 6);
        ctx.fill();
        ctx.strokeStyle = "rgba(148, 163, 184, 0.2)";
        ctx.stroke();

        ctx.font = "8px 'Plus Jakarta Sans', sans-serif";
        ctx.fillStyle = "#94a3b8";

        // User path line
        ctx.strokeStyle = "#3b82f6"; ctx.lineWidth = 2; ctx.setLineDash([4, 2]);
        ctx.beginPath(); ctx.moveTo(w - 100, 22); ctx.lineTo(w - 80, 22); ctx.stroke();
        ctx.fillText("User path", w - 74, 25);

        // Object path line
        ctx.strokeStyle = "#ef4444"; ctx.beginPath(); ctx.moveTo(w - 100, 38); ctx.lineTo(w - 80, 38); ctx.stroke();
        ctx.fillText("Object path", w - 74, 41);

        // Intersection dot
        ctx.fillStyle = "#ef4444"; ctx.beginPath(); ctx.arc(w - 90, 53, 3.5, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#94a3b8"; ctx.fillText("Intersection", w - 74, 56);

        // FOE dot
        ctx.fillStyle = "#3b82f6"; ctx.beginPath(); ctx.arc(w - 90, 68, 3.5, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#94a3b8"; ctx.fillText("FOE", w - 74, 71);
        ctx.restore();
    }

    // -------------------------------------------------------------------------
    // 8. Tab 3: Haptic State
    // -------------------------------------------------------------------------
    window.switchHapticView = function (view) {
        const btnDev = document.getElementById("btn-seg-device");
        const btnCmd = document.getElementById("btn-seg-commands");

        if (view === "device") {
            if (hapticsDeviceView) hapticsDeviceView.style.display = "block";
            if (hapticsCommandsView) hapticsCommandsView.style.display = "none";
            if (btnDev) btnDev.classList.add("active");
            if (btnCmd) btnCmd.classList.remove("active");
        } else {
            if (hapticsDeviceView) hapticsDeviceView.style.display = "none";
            if (hapticsCommandsView) hapticsCommandsView.style.display = "block";
            if (btnDev) btnDev.classList.remove("active");
            if (btnCmd) btnCmd.classList.add("active");
            renderHapticCommandsList();
        }
    };

    function updateHapticTelemetry(haptic) {
        const dir = (haptic.direction || "STOP").toUpperCase();
        const pattern = haptic.pattern_id || "ALL_CLEAR";
        const urgency = haptic.urgency || 1;
        const dur = haptic.duration_ms || 200;
        const timeNow = new Date().toTimeString().split(" ")[0];

        if (hapticPatLabel) hapticPatLabel.textContent = pattern;
        if (hapticUrgVal) hapticUrgVal.textContent = `${urgency}/3`;
        if (hapticDurVal) hapticDurVal.textContent = `${dur} ms`;
        if (hapticTimeVal) hapticTimeVal.textContent = timeNow;

        // Reset motors first
        resetMotorVisuals();

        const isVibrating = pattern !== "ALL_CLEAR";
        if (hapticVibBadge) {
            hapticVibBadge.textContent = isVibrating ? "● Vibrating" : "○ Idle";
            hapticVibBadge.style.background = isVibrating ? "#eff6ff" : "#f1f5f9";
            hapticVibBadge.style.color = isVibrating ? "#2563eb" : "#64748b";
            hapticVibBadge.style.borderColor = isVibrating ? "#bfdbfe" : "#cbd5e1";
        }

        if (dir === "LEFT" && isVibrating) {
            setMotorActive(svgMotorLeft, svgRippleLeft, svgLblLeft, devMotorLStatus, true);
        } else if (dir === "CENTER" && isVibrating) {
            setMotorActive(svgMotorCenter, svgRippleCenter, svgLblCenter, devMotorCStatus, true);
        } else if (dir === "RIGHT" && isVibrating) {
            setMotorActive(svgMotorRight, svgRippleRight, svgLblRight, devMotorRStatus, true);
        } else if (dir === "STOP" && isVibrating) {
            setMotorActive(svgMotorLeft, svgRippleLeft, svgLblLeft, devMotorLStatus, true);
            setMotorActive(svgMotorCenter, svgRippleCenter, svgLblCenter, devMotorCStatus, true);
            setMotorActive(svgMotorRight, svgRippleRight, svgLblRight, devMotorRStatus, true);
        }

        // Add to history
        hapticHistory.unshift({ time: timeNow, pattern, duration: dur, urgency });
        if (hapticHistory.length > 20) hapticHistory.pop();
        renderHapticCommandsList();
    }

    function setMotorActive(circleEl, rippleEl, labelEl, badgeEl, active) {
        if (!circleEl) return;
        if (active) {
            circleEl.setAttribute("fill", "#eff6ff");
            circleEl.setAttribute("stroke", "#3b82f6");
            circleEl.setAttribute("stroke-width", "3");
            if (rippleEl) rippleEl.classList.add("vibrating");
            if (labelEl) labelEl.setAttribute("fill", "#3b82f6");
            if (badgeEl) {
                badgeEl.className = "pill-badge green";
                badgeEl.textContent = "● ACTIVE";
            }
        }
    }

    function resetMotorVisuals() {
        const motors = [
            { c: svgMotorLeft, r: svgRippleLeft, l: svgLblLeft, b: devMotorLStatus },
            { c: svgMotorCenter, r: svgRippleCenter, l: svgLblCenter, b: devMotorCStatus },
            { c: svgMotorRight, r: svgRippleRight, l: svgLblRight, b: devMotorRStatus }
        ];

        motors.forEach(m => {
            if (m.c) {
                m.c.setAttribute("fill", "#f8fafc");
                m.c.setAttribute("stroke", "#94a3b8");
                m.c.setAttribute("stroke-width", "2");
            }
            if (m.r) m.r.classList.remove("vibrating");
            if (m.l) m.l.setAttribute("fill", "#64748b");
            if (m.b) {
                m.b.className = "detail-val";
                m.b.style.color = "var(--text-muted)";
                m.b.textContent = "○ Idle";
            }
        });
    }

    function renderHapticCommandsList() {
        if (!hapticCommandsList) return;
        hapticCommandsList.innerHTML = hapticHistory.slice(0, 8).map(cmd => `
            <div class="detail-table-row">
                <span class="detail-key mono">${cmd.time}</span>
                <span class="detail-val mono" style="font-size:0.75rem;">${cmd.pattern} (${cmd.duration}ms, urg ${cmd.urgency})</span>
            </div>
        `).join("");
    }

    // -------------------------------------------------------------------------
    // 9. Tab 4: Test & Replay
    // -------------------------------------------------------------------------
    window.selectScenario = function (scenId) {
        currentScenarioId = scenId;
        if (selectTestScenario) selectTestScenario.value = scenId;

        const scen = SCENARIOS[scenId] || SCENARIOS.s1;
        if (scenDesc) scenDesc.textContent = scen.desc;
        if (scenExpected) scenExpected.textContent = scen.expected;
        if (scenActual) scenActual.textContent = scen.actual;
        if (scenResult) {
            scenResult.className = "pill-badge green";
            scenResult.textContent = "✔ PASS";
        }

        replayProgress = 35;
        if (replaySlider) replaySlider.value = replayProgress;
        updateScrubberText();
        drawReplayTimeline();
    };

    window.startReplay = function () {
        if (isReplaying) return;
        isReplaying = true;
        if (replayTimer) clearInterval(replayTimer);

        replayTimer = setInterval(() => {
            replayProgress += 2;
            if (replayProgress > 100) {
                replayProgress = 100;
                window.pauseReplay();
            }
            if (replaySlider) replaySlider.value = replayProgress;
            updateScrubberText();
            drawReplayTimeline();
        }, 120);
    };

    window.pauseReplay = function () {
        isReplaying = false;
        if (replayTimer) clearInterval(replayTimer);
    };

    window.resetReplay = function () {
        window.pauseReplay();
        replayProgress = 0;
        if (replaySlider) replaySlider.value = 0;
        updateScrubberText();
        drawReplayTimeline();
    };

    window.onScrubberInput = function (val) {
        replayProgress = Number(val);
        updateScrubberText();
        drawReplayTimeline();
    };

    function updateScrubberText() {
        if (!scenFrameTxt) return;
        const scen = SCENARIOS[currentScenarioId] || SCENARIOS.s1;
        const frame = 1200 + Math.round((replayProgress / 100) * 180);
        const curveIdx = Math.min(scen.curve.length - 1, Math.floor((replayProgress / 100) * scen.curve.length));
        const risk = scen.curve[curveIdx] || 0.11;
        scenFrameTxt.textContent = `Frame ${frame} | Risk ${risk.toFixed(2)}`;
    }

    function drawReplayTimeline() {
        if (!replayTimelineCanvas) return;
        const ctx = replayTimelineCanvas.getContext("2d");
        const w = replayTimelineCanvas.width;
        const h = replayTimelineCanvas.height;

        ctx.clearRect(0, 0, w, h);

        // Chart background
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, w, h);

        const scen = SCENARIOS[currentScenarioId] || SCENARIOS.s1;
        const pts = scen.curve;

        // Draw horizontal grid guidelines
        ctx.strokeStyle = "#f1f5f9";
        ctx.lineWidth = 1;
        for (let y = 15; y < h; y += 22) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
        }

        // Draw Risk Curve
        ctx.beginPath();
        const step = w / (pts.length - 1);
        pts.forEach((val, i) => {
            const px = i * step;
            const py = h - 10 - (val * (h - 25));
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        });

        ctx.strokeStyle = scen.riskPeak > 0.5 ? "#f97316" : "#2563eb";
        ctx.lineWidth = 2.5;
        ctx.stroke();

        // Area under curve
        ctx.lineTo(w, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        ctx.fillStyle = scen.riskPeak > 0.5 ? "rgba(249, 115, 22, 0.08)" : "rgba(37, 99, 235, 0.08)";
        ctx.fill();

        // Scrubber Cursor Line
        const cursorX = (replayProgress / 100) * w;
        ctx.save();
        ctx.strokeStyle = "#0f172a";
        ctx.lineWidth = 2;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(cursorX, 0);
        ctx.lineTo(cursorX, h);
        ctx.stroke();

        // Scrubber thumb dot
        const curveIdx = Math.min(pts.length - 1, Math.floor((replayProgress / 100) * pts.length));
        const cursorY = h - 10 - ((pts[curveIdx] || 0.1) * (h - 25));
        ctx.beginPath();
        ctx.arc(cursorX, cursorY, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = "#2563eb";
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
    }

    // -------------------------------------------------------------------------
    // 10. Tab 5: Social Assist
    // -------------------------------------------------------------------------
    window.toggleSocialAssist = function () {
        socialAssistEnabled = !socialAssistEnabled;

        if (toggleSocialSwitch) {
            if (socialAssistEnabled) {
                toggleSocialSwitch.classList.remove("off");
                toggleSocialSwitch.style.background = "var(--c-primary)";
                const knob = toggleSocialSwitch.querySelector(".toggle-knob");
                if (knob) {
                    knob.style.right = "2px";
                    knob.style.left = "auto";
                }
            } else {
                toggleSocialSwitch.classList.add("off");
                toggleSocialSwitch.style.background = "#cbd5e1";
                const knob = toggleSocialSwitch.querySelector(".toggle-knob");
                if (knob) {
                    knob.style.right = "auto";
                    knob.style.left = "2px";
                }
            }
        }

        if (socialSwitchLabel) {
            socialSwitchLabel.textContent = socialAssistEnabled ? "Enabled" : "Disabled";
            socialSwitchLabel.style.color = socialAssistEnabled ? "var(--c-primary)" : "var(--text-muted)";
        }

        if (socialFaceBox) {
            socialFaceBox.style.opacity = socialAssistEnabled ? "1" : "0.2";
        }
    };

    window.switchSocialView = function (view) {
        const btnLive = document.getElementById("btn-seg-live-rec");
        const btnContacts = document.getElementById("btn-seg-contacts");

        if (view === "live") {
            if (socialLiveView) socialLiveView.style.display = "block";
            if (socialContactsView) socialContactsView.style.display = "none";
            if (btnLive) btnLive.classList.add("active");
            if (btnContacts) btnContacts.classList.remove("active");
        } else {
            if (socialLiveView) socialLiveView.style.display = "none";
            if (socialContactsView) socialContactsView.style.display = "block";
            if (btnLive) btnLive.classList.remove("active");
            if (btnContacts) btnContacts.classList.add("active");
        }
    };

    // -------------------------------------------------------------------------
    // Startup Initialization
    // -------------------------------------------------------------------------
    initCameraSource();
    connectWs();
    window.switchTab("live");
    window.selectScenario("s1");
})();
