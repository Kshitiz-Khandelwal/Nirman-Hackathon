/**
 * SpatialVector-HMI — Tab 1: Home Page (Live Navigation View)
 */

window.HomePage = (function () {
    "use strict";

    let vdoManager = null;
    let containerEl = null;

    function init(container) {
        containerEl = container;
        renderShell();

        const iframe = document.getElementById("home-vdo-frame");
        const canvas = document.getElementById("home-hud-canvas");

        vdoManager = VdoNinjaEmbed.createManager({
            iframeEl: iframe,
            canvasEl: canvas,
            onSourceResolved: (url) => {
                console.log("[Home] VDO.Ninja loaded:", url);
            }
        });
        vdoManager.init();
    }

    function renderShell() {
        containerEl.innerHTML = `
            <!-- Top Status Alert Banner -->
            <div id="home-status-banner" class="status-alert-card safe">
                <div class="alert-headline-box">
                    <span id="home-alert-tag" class="alert-state-tag">SAFE</span>
                    <span id="home-alert-msg" class="alert-text-main">Path Clear · Safe Navigation</span>
                </div>
                <div id="home-alert-dir" class="alert-dir-arrow">↑</div>
            </div>

            <!-- Live Camera View with AR Bounding Box HUD -->
            <div class="video-card">
                <div class="video-toolbar">
                    <button class="tool-chip" onclick="HomePage.toggleAspect()">Fill/Fit</button>
                    <button class="tool-chip" onclick="HomePage.toggleHud()">HUD</button>
                </div>
                <iframe id="home-vdo-frame" class="video-frame" allow="autoplay; camera; microphone" src="about:blank"></iframe>
                <canvas id="home-hud-canvas" class="hud-canvas"></canvas>
            </div>

            <!-- Directional Guidance Callout Line -->
            <div class="guidance-prompt-card">
                <span class="guidance-icon">🧭</span>
                <span id="home-safer-line" class="guidance-text">Forward corridor is clear to navigate.</span>
            </div>

            <!-- Quick Details Panel (Expandable) -->
            <div id="quick-details-container"></div>

            <!-- Nearby Objects Count -->
            <div class="expand-panel">
                <div class="expand-header" style="cursor: default;">
                    <span>Nearby Objects</span>
                    <span id="home-nearby-badge" class="pill-badge gray">0 Detected</span>
                </div>
            </div>

            <!-- Recent Guidance (Last 3 Actions) -->
            <div class="expand-panel open">
                <div class="expand-header" style="cursor: default;">
                    <span>Recent Guidance</span>
                    <span class="pill-badge blue">Live History</span>
                </div>
                <div class="expand-body" style="display: block;">
                    <div id="home-recent-actions-list" class="recent-actions-list" style="display: flex; flex-direction: column; gap: 6px;">
                        <span style="font-size: 11px; color: var(--text-muted);">Waiting for motor commands...</span>
                    </div>
                </div>
            </div>
        `;

        // Mount quick details inside container
        const qdContainer = document.getElementById("quick-details-container");
        QuickDetailsPage.init(qdContainer);
    }

    function updateTelemetry(msg) {
        if (!msg) return;

        const risk = msg.risk_state || {};
        const haptic = msg.haptic || {};
        const tracks = msg.tracks || [];
        const state = (risk.state || "SAFE").toUpperCase();
        const globalRisk = risk.global_risk || 0.0;
        const dir = (haptic.direction || "STOP").toUpperCase();

        // 1. Status Banner
        const banner = document.getElementById("home-status-banner");
        const tag = document.getElementById("home-alert-tag");
        const mainMsg = document.getElementById("home-alert-msg");
        const dirEl = document.getElementById("home-alert-dir");

        if (banner && tag && mainMsg && dirEl) {
            banner.className = `status-alert-card ${state.toLowerCase()}`;
            tag.textContent = state;

            // Direction arrow mapping
            let arrowChar = "↑";
            if (dir === "LEFT") arrowChar = "←";
            else if (dir === "RIGHT") arrowChar = "→";
            else if (dir === "STOP") arrowChar = "⏹";
            dirEl.textContent = arrowChar;

            // Text copy
            const primaryTrack = tracks[0];
            if (primaryTrack && primaryTrack.intersect) {
                mainMsg.textContent = `${primaryTrack.class_name || "Obstacle"} approaching your path`;
            } else if (state === "CRITICAL") {
                mainMsg.textContent = "Imminent Collision Hazard · Stop!";
            } else if (state === "WARNING") {
                mainMsg.textContent = "Obstacle detected ahead · Prepare to steer";
            } else if (state === "CAUTION") {
                mainMsg.textContent = "Nearby obstacle in corridor";
            } else if (state === "DEGRADED") {
                mainMsg.textContent = "Sensor Confidence Degraded · Fallback Active";
            } else {
                mainMsg.textContent = "Path Clear · Safe Navigation";
            }
        }

        // 2. Video HUD Bounding Boxes
        if (vdoManager) {
            vdoManager.drawBoundingBoxes(tracks, msg.frame_width || 640, msg.frame_height || 480, null, globalRisk);
        }

        // 3. Safer Side Guidance Line (derived from haptic.direction)
        const saferLine = document.getElementById("home-safer-line");
        if (saferLine) {
            if (dir === "LEFT") {
                saferLine.innerHTML = `<span class="guidance-highlight">Left side</span> is currently safer to navigate.`;
            } else if (dir === "RIGHT") {
                saferLine.innerHTML = `<span class="guidance-highlight">Right side</span> is currently safer to navigate.`;
            } else if (dir === "STOP") {
                saferLine.innerHTML = state === "SAFE"
                    ? `Forward corridor is clear to navigate.`
                    : `<span style="color: #ef4444; font-weight: 700;">Forward corridor obstructed. Stop and assess path.</span>`;
            } else {
                saferLine.textContent = `Center corridor is clear.`;
            }
        }

        // 4. Quick Details
        QuickDetailsPage.update(tracks[0], risk);

        // 5. Nearby Count
        const nearbyBadge = document.getElementById("home-nearby-badge");
        if (nearbyBadge) {
            const count = tracks.length;
            nearbyBadge.textContent = count === 1 ? "1 Object" : `${count} Objects`;
            nearbyBadge.className = count > 0 ? "pill-badge yellow" : "pill-badge gray";
        }

        // 6. Recent Actions History
        updateRecentActions(haptic);
    }

    const recentHistory = [];
    function updateRecentActions(haptic) {
        if (!haptic || !haptic.pattern_id || haptic.pattern_id === "ALL_CLEAR") return;

        const timeStr = new Date().toTimeString().split(" ")[0];
        const item = {
            time: timeStr,
            pattern: haptic.pattern_id,
            dir: haptic.direction || "STOP",
            urgency: haptic.urgency || 1,
        };

        // Don't duplicate consecutive identical entries
        if (recentHistory.length > 0) {
            const last = recentHistory[0];
            if (last.pattern === item.pattern && last.dir === item.dir) {
                return;
            }
        }

        recentHistory.unshift(item);
        if (recentHistory.length > 3) recentHistory.pop();

        const listEl = document.getElementById("home-recent-actions-list");
        if (listEl) {
            listEl.innerHTML = recentHistory.map(h => `
                <div style="display: flex; justify-content: space-between; font-size: 11px; padding: 4px 0; border-bottom: 1px dashed #e2e8f0;">
                    <span style="font-family: var(--font-mono); font-weight: 600; color: #2563eb;">${h.dir} · ${h.pattern}</span>
                    <span style="font-family: var(--font-mono); color: var(--text-muted);">${h.time}</span>
                </div>
            `).join("");
        }
    }

    return {
        init: init,
        updateTelemetry: updateTelemetry,
        toggleAspect: () => vdoManager && vdoManager.toggleAspect(),
        toggleHud: () => vdoManager && vdoManager.toggleHud(),
    };
})();
