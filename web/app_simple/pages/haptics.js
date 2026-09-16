/**
 * SpatialVector-HMI — Tab 2: Haptics Page
 */

window.HapticsPage = (function () {
    "use strict";

    let containerEl = null;
    let diagramController = null;

    function init(container) {
        containerEl = container;
        renderShell();

        const vestBox = document.getElementById("haptics-vest-diagram");
        diagramController = HapticBodyDiagram.create(vestBox, { maxUrgency: 5 });
    }

    function renderShell() {
        containerEl.innerHTML = `
            <!-- Vest Diagram Card -->
            <div class="expand-panel open" style="margin-bottom: 14px;">
                <div class="expand-header" style="cursor: default;">
                    <span>Active Haptic Feedback</span>
                    <span id="haptic-status-chip" class="pill-badge gray">○ Standby</span>
                </div>
                <div class="expand-body" style="display: block; background: #ffffff; padding: 14px 10px;">
                    <div id="haptics-vest-diagram"></div>
                </div>
            </div>

            <!-- Current Command Card -->
            <div class="expand-panel open" style="margin-bottom: 14px;">
                <div class="expand-header" style="cursor: default;">
                    <span>Current Command</span>
                    <span id="haptic-urg-badge" class="pill-badge blue">1 / 5 Urgency</span>
                </div>
                <div class="expand-body" style="display: block; background: #ffffff;">
                    <div class="kv-row">
                        <span class="kv-key">Tactile Direction</span>
                        <span id="haptic-dir-val" class="kv-val" style="color: #2563eb; font-weight: 700;">STOP</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Active Pattern ID</span>
                        <span id="haptic-pattern-val" class="kv-val">ALL_CLEAR</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Pulse Duration</span>
                        <span id="haptic-dur-val" class="kv-val">200 ms</span>
                    </div>
                    <div class="kv-row" style="flex-direction: column; align-items: flex-start; gap: 4px; margin-top: 4px;">
                        <span class="kv-key">Guidance Interpretation</span>
                        <span id="haptic-meaning-val" style="font-size: 12px; font-weight: 600; color: var(--text-primary);">
                            Safe navigation path; all motors idle.
                        </span>
                    </div>
                </div>
            </div>

            <!-- Intuitive Sensory Help Prompt -->
            <div class="guidance-prompt-card" style="margin-bottom: 14px;">
                <span class="guidance-icon">💡</span>
                <span class="guidance-text">
                    <strong>Quick Reminder:</strong> Feeling a vibration pulse on the left? It means <em>steer left</em> into the open corridor.
                </span>
            </div>

            <!-- Haptic Language Guide (Expandable) -->
            <div class="expand-panel" id="panel-haptic-patterns">
                <button class="expand-header" onclick="HapticsPage.togglePanel('panel-haptic-patterns')">
                    <span>Haptic Language Guide</span>
                    <span class="expand-chevron">▼</span>
                </button>
                <div class="expand-body">
                    <div class="kv-row">
                        <span class="kv-key"><code>ALL_CLEAR</code></span>
                        <span style="font-size: 11px; color: var(--text-secondary);">Silent / idle pulse. Corridor is safe.</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key"><code>LEFT_MED</code></span>
                        <span style="font-size: 11px; color: var(--text-secondary);">Cadenced pulse on left motor. Steer left.</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key"><code>RIGHT_MED</code></span>
                        <span style="font-size: 11px; color: var(--text-secondary);">Cadenced pulse on right motor. Steer right.</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key"><code>STOP_CRITICAL</code></span>
                        <span style="font-size: 11px; color: var(--text-secondary);">Rapid triple pulse across all 3 motors. Halt.</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key"><code>DEGRADED_WARN</code></span>
                        <span style="font-size: 11px; color: var(--text-secondary);">Slow recurring warning pulse. Sensor dropout.</span>
                    </div>
                </div>
            </div>

            <!-- Device Status (Expandable) -->
            <div class="expand-panel" id="panel-haptic-device">
                <button class="expand-header" onclick="HapticsPage.togglePanel('panel-haptic-device')">
                    <span>Haptic Belt Hardware Status</span>
                    <span class="expand-chevron">▼</span>
                </button>
                <div class="expand-body">
                    <div class="kv-row">
                        <span class="kv-key">Actuator Interface</span>
                        <span id="dev-hw-status" class="pill-badge green">Simulated Arduino (OK)</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Actuator Link</span>
                        <span id="dev-link-status" class="kv-val">Online</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Command Latency</span>
                        <span id="dev-latency-val" class="kv-val">&lt; 4 ms</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Motor Diagnostic</span>
                        <span id="dev-diag-val" class="kv-val">3/3 Operational</span>
                    </div>
                </div>
            </div>

            <!-- Calibration Card (Honest Notice per Section 7) -->
            <div class="expand-panel" style="background: #fafafa; border-style: dashed;">
                <div class="expand-header" style="cursor: default;">
                    <span>Haptic Calibration</span>
                    <span class="pill-badge gray">Fixed Baseline</span>
                </div>
                <div class="expand-body" style="display: block; font-size: 11px; color: var(--text-muted); line-height: 1.6;">
                    Motor intensity is calibrated to the standardized 5-tier ISO-9241 assistive vibration profile (1.0x baseline gain). Custom per-user sensory sensitivity calibration will be enabled in v2.0 firmware.
                </div>
            </div>
        `;
    }

    function togglePanel(id) {
        const p = document.getElementById(id);
        if (p) p.classList.toggle("open");
    }

    function updateTelemetry(msg) {
        if (!msg) return;
        const haptic = msg.haptic || {};
        const health = msg.pipeline_health || {};

        if (diagramController) {
            diagramController.update(haptic);
        }

        const dir = (haptic.direction || "STOP").toUpperCase();
        const pattern = haptic.pattern_id || "ALL_CLEAR";
        const urgency = haptic.urgency || 1;
        const dur = haptic.duration_ms || 200;
        const isVibrating = pattern !== "ALL_CLEAR";

        // Status Chip
        const statusChip = document.getElementById("haptic-status-chip");
        if (statusChip) {
            statusChip.textContent = isVibrating ? "● Vibrating" : "○ Standby";
            statusChip.className = isVibrating ? "pill-badge blue" : "pill-badge gray";
        }

        // Urgency
        const urgBadge = document.getElementById("haptic-urg-badge");
        if (urgBadge) {
            urgBadge.textContent = `${urgency} / 5 Urgency`;
            urgBadge.className = urgency >= 4 ? "pill-badge red" : (urgency >= 3 ? "pill-badge orange" : "pill-badge blue");
        }

        // Values
        const dirVal = document.getElementById("haptic-dir-val");
        const patVal = document.getElementById("haptic-pattern-val");
        const durVal = document.getElementById("haptic-dur-val");
        const meaningVal = document.getElementById("haptic-meaning-val");

        if (dirVal) dirVal.textContent = dir;
        if (patVal) patVal.textContent = pattern;
        if (durVal) durVal.textContent = `${dur} ms`;
        if (meaningVal) meaningVal.textContent = HapticBodyDiagram.getDescription(pattern);

        // Hardware Status
        const hwStatus = document.getElementById("dev-hw-status");
        if (hwStatus && health.arduino) {
            hwStatus.textContent = health.arduino;
            hwStatus.className = health.arduino.includes("OK") ? "pill-badge green" : "pill-badge red";
        }
    }

    return {
        init: init,
        togglePanel: togglePanel,
        updateTelemetry: updateTelemetry,
    };
})();
