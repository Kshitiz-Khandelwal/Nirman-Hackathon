/**
 * SpatialVector-HMI — Subpage: Test & Replay Scenarios S1–S6 (Advanced Diagnostics)
 *
 * Relocated wholesale from the dev dashboard:
 * - Benchmark scenarios S1–S6 with verified ground truth expectations
 * - Interactive timeline playback & frame scrubber
 * - Timeline canvas showing risk curves over time
 */

window.TestReplayPage = (function () {
    "use strict";

    let containerEl = null;
    let canvasEl = null;
    let currentScenarioId = "s1";
    let replayProgress = 35;
    let isReplaying = false;
    let replayTimer = null;

    const SCENARIOS = {
        s1: {
            title: "Scenario S1 - Parallel Wall (Safe)",
            desc: "Walk parallel to a wall at close lateral distance",
            expected: "SAFE / SILENT",
            actual: "SAFE / SILENT",
            result: "PASS",
            riskPeak: 0.12,
            curve: [0.05, 0.08, 0.11, 0.12, 0.10, 0.09, 0.07, 0.06, 0.05, 0.05]
        },
        s2: {
            title: "Scenario S2 - Head-On Obstacle (Warning)",
            desc: "Obstacle approaching directly in user's walking corridor",
            expected: "WARNING",
            actual: "WARNING",
            result: "PASS",
            riskPeak: 0.84,
            curve: [0.15, 0.22, 0.38, 0.55, 0.72, 0.84, 0.78, 0.45, 0.20, 0.10]
        },
        s3: {
            title: "Scenario S3 - Crossing Pedestrian (Warning)",
            desc: "Pedestrian crossing path at lateral angle with close CPA",
            expected: "WARNING",
            actual: "WARNING",
            result: "PASS",
            riskPeak: 0.76,
            curve: [0.10, 0.18, 0.35, 0.62, 0.76, 0.68, 0.30, 0.15, 0.08, 0.05]
        },
        s4: {
            title: "Scenario S4 - Safe Pass (Safe)",
            desc: "Pedestrian passing in adjacent corridor with zero path intersection",
            expected: "SAFE / SILENT",
            actual: "SAFE / SILENT",
            result: "PASS",
            riskPeak: 0.22,
            curve: [0.08, 0.12, 0.18, 0.22, 0.19, 0.14, 0.09, 0.06, 0.04, 0.02]
        },
        s5: {
            title: "Scenario S5 - Receding Object (Safe)",
            desc: "Object moving away in the same heading direction",
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
            curve: [0.20, 0.35, 0.52, 0.78, 0.95, 0.91, 0.84, 0.60, 0.35, 0.18]
        }
    };

    function init(container) {
        containerEl = container;
        render();
        canvasEl = document.getElementById("replay-timeline-canvas");
        selectScenario("s1");
    }

    function render() {
        containerEl.innerHTML = `
            <div class="subpage-header">
                <button class="back-btn" onclick="App.closeSubpage()">‹ Settings</button>
                <span class="subpage-title">Test & Replay (S1–S6)</span>
            </div>

            <!-- Scenario Selection Dropdown -->
            <div class="expand-panel open" style="margin-bottom: 12px;">
                <div class="expand-header" style="cursor: default;">
                    <span>Replay Benchmark Scenario</span>
                </div>
                <div class="expand-body" style="display: block;">
                    <select id="select-replay-scen" class="select-input" onchange="TestReplayPage.selectScenario(this.value)">
                        <option value="s1">S1 — Parallel Wall (Safe)</option>
                        <option value="s2">S2 — Head-On Obstacle (Warning)</option>
                        <option value="s3">S3 — Crossing Pedestrian (Warning)</option>
                        <option value="s4">S4 — Safe Pass (Safe)</option>
                        <option value="s5">S5 — Receding Object (Safe)</option>
                        <option value="s6">S6 — Multiple Obstacles (Critical)</option>
                    </select>

                    <div style="display: flex; gap: 8px; margin-top: 10px;">
                        <button id="btn-replay-play" class="action-btn primary" onclick="TestReplayPage.startReplay()">▶ Play</button>
                        <button class="action-btn" onclick="TestReplayPage.pauseReplay()">⏸ Pause</button>
                        <button class="action-btn" onclick="TestReplayPage.resetReplay()">↺ Reset</button>
                    </div>
                </div>
            </div>

            <!-- Scenario Details Card -->
            <div class="expand-panel open" style="margin-bottom: 12px;">
                <div class="expand-header" style="cursor: default;">
                    <span>Behavioral Ground Truth Verification</span>
                    <span id="scen-badge-result" class="pill-badge green">✔ PASS</span>
                </div>
                <div class="expand-body" style="display: block;">
                    <div class="kv-row">
                        <span class="kv-key">Description</span>
                        <span id="scen-txt-desc" class="kv-val" style="text-align: right; max-width: 60%;">—</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Expected State</span>
                        <span id="scen-txt-expected" class="kv-val mono">—</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Actual State</span>
                        <span id="scen-txt-actual" class="kv-val mono">—</span>
                    </div>
                </div>
            </div>

            <!-- Replay Timeline Chart -->
            <div class="expand-panel open" style="margin-bottom: 12px;">
                <div class="expand-header" style="cursor: default;">
                    <span>Collision Risk Trajectory Curve</span>
                    <span id="scen-txt-frame" class="kv-val mono" style="font-size: 11px;">Frame 1260</span>
                </div>
                <div class="expand-body" style="display: block;">
                    <div style="background: #ffffff; border: 1px solid var(--border-light); border-radius: 8px; padding: 4px; height: 90px; margin-bottom: 10px;">
                        <canvas id="replay-timeline-canvas" width="360" height="82" style="width: 100%; height: 100%;"></canvas>
                    </div>

                    <!-- Scrubber Slider -->
                    <input id="replay-slider" type="range" min="0" max="100" value="35" style="width: 100%; accent-color: var(--primary);" oninput="TestReplayPage.onScrubberInput(this.value)">
                </div>
            </div>

            <!-- All Scenarios Summary Grid -->
            <div class="expand-panel open">
                <div class="expand-header" style="cursor: default;">
                    <span>Standard Scenario Benchmark Suite</span>
                </div>
                <div class="expand-body" style="display: block;">
                    <div class="kv-row" style="cursor: pointer;" onclick="TestReplayPage.selectScenario('s1')">
                        <span class="kv-key" style="font-weight: 600;">S1 Parallel Wall</span>
                        <span class="pill-badge green">Pass (Safe)</span>
                    </div>
                    <div class="kv-row" style="cursor: pointer;" onclick="TestReplayPage.selectScenario('s2')">
                        <span class="kv-key" style="font-weight: 600;">S2 Head-On Obstacle</span>
                        <span class="pill-badge green">Pass (Warn)</span>
                    </div>
                    <div class="kv-row" style="cursor: pointer;" onclick="TestReplayPage.selectScenario('s3')">
                        <span class="kv-key" style="font-weight: 600;">S3 Crossing Pedestrian</span>
                        <span class="pill-badge green">Pass (Warn)</span>
                    </div>
                    <div class="kv-row" style="cursor: pointer;" onclick="TestReplayPage.selectScenario('s4')">
                        <span class="kv-key" style="font-weight: 600;">S4 Safe Pass</span>
                        <span class="pill-badge green">Pass (Safe)</span>
                    </div>
                    <div class="kv-row" style="cursor: pointer;" onclick="TestReplayPage.selectScenario('s5')">
                        <span class="kv-key" style="font-weight: 600;">S5 Receding Object</span>
                        <span class="pill-badge green">Pass (Safe)</span>
                    </div>
                    <div class="kv-row" style="cursor: pointer;" onclick="TestReplayPage.selectScenario('s6')">
                        <span class="kv-key" style="font-weight: 600;">S6 Multiple Obstacles</span>
                        <span class="pill-badge green">Pass (Crit)</span>
                    </div>
                </div>
            </div>
        `;
    }

    function selectScenario(scenId) {
        currentScenarioId = scenId;
        const sel = document.getElementById("select-replay-scen");
        if (sel) sel.value = scenId;

        const scen = SCENARIOS[scenId] || SCENARIOS.s1;
        const descEl = document.getElementById("scen-txt-desc");
        const expEl = document.getElementById("scen-txt-expected");
        const actEl = document.getElementById("scen-txt-actual");
        const resEl = document.getElementById("scen-badge-result");

        if (descEl) descEl.textContent = scen.desc;
        if (expEl) expEl.textContent = scen.expected;
        if (actEl) actEl.textContent = scen.actual;
        if (resEl) {
            resEl.textContent = "✔ PASS";
            resEl.className = "pill-badge green";
        }

        replayProgress = 35;
        const slider = document.getElementById("replay-slider");
        if (slider) slider.value = replayProgress;

        updateScrubberText();
        drawTimeline();
    }

    function startReplay() {
        if (isReplaying) return;
        isReplaying = true;
        if (replayTimer) clearInterval(replayTimer);

        replayTimer = setInterval(() => {
            replayProgress += 2;
            if (replayProgress > 100) {
                replayProgress = 100;
                pauseReplay();
            }
            const slider = document.getElementById("replay-slider");
            if (slider) slider.value = replayProgress;
            updateScrubberText();
            drawTimeline();
        }, 120);
    }

    function pauseReplay() {
        isReplaying = false;
        if (replayTimer) clearInterval(replayTimer);
    }

    function resetReplay() {
        pauseReplay();
        replayProgress = 0;
        const slider = document.getElementById("replay-slider");
        if (slider) slider.value = 0;
        updateScrubberText();
        drawTimeline();
    }

    function onScrubberInput(val) {
        replayProgress = Number(val);
        updateScrubberText();
        drawTimeline();
    }

    function updateScrubberText() {
        const frameEl = document.getElementById("scen-txt-frame");
        if (!frameEl) return;
        const scen = SCENARIOS[currentScenarioId] || SCENARIOS.s1;
        const frame = 1200 + Math.round((replayProgress / 100) * 180);
        const curveIdx = Math.min(scen.curve.length - 1, Math.floor((replayProgress / 100) * scen.curve.length));
        const risk = scen.curve[curveIdx] || 0.11;
        frameEl.textContent = `Frame ${frame} | Risk ${risk.toFixed(2)}`;
    }

    function drawTimeline() {
        if (!canvasEl) return;
        const ctx = canvasEl.getContext("2d");
        const w = canvasEl.width;
        const h = canvasEl.height;

        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, w, h);

        const scen = SCENARIOS[currentScenarioId] || SCENARIOS.s1;
        const pts = scen.curve;

        // Grid lines
        ctx.strokeStyle = "#f1f5f9";
        ctx.lineWidth = 1;
        for (let y = 15; y < h; y += 22) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
        }

        // Risk line
        ctx.beginPath();
        const step = w / (pts.length - 1);
        pts.forEach((val, i) => {
            const px = i * step;
            const py = h - 8 - (val * (h - 20));
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        });

        ctx.strokeStyle = scen.riskPeak > 0.5 ? "#f97316" : "#2563eb";
        ctx.lineWidth = 2.5;
        ctx.stroke();

        ctx.lineTo(w, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        ctx.fillStyle = scen.riskPeak > 0.5 ? "rgba(249, 115, 22, 0.08)" : "rgba(37, 99, 235, 0.08)";
        ctx.fill();

        // Cursor line
        const cursorX = (replayProgress / 100) * w;
        ctx.save();
        ctx.strokeStyle = "#0f172a";
        ctx.lineWidth = 2;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(cursorX, 0);
        ctx.lineTo(cursorX, h);
        ctx.stroke();

        const curveIdx = Math.min(pts.length - 1, Math.floor((replayProgress / 100) * pts.length));
        const cursorY = h - 8 - ((pts[curveIdx] || 0.1) * (h - 20));
        ctx.beginPath();
        ctx.arc(cursorX, cursorY, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = "#2563eb";
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
    }

    return {
        init,
        selectScenario,
        startReplay,
        pauseReplay,
        resetReplay,
        onScrubberInput,
    };
})();
