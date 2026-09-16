/**
 * SpatialVector-HMI — Subpage: Social Assist (Relocated Wholesale)
 *
 * Strict Architectural Rule: Social Assist is completely sandboxed and
 * NEVER impacts or modifies the collision avoidance RiskState.
 */

window.SocialAssistPage = (function () {
    "use strict";

    let containerEl = null;
    let socialAssistEnabled = true;

    function init(container) {
        containerEl = container;
        render();
    }

    function render() {
        containerEl.innerHTML = `
            <div class="subpage-header">
                <button class="back-btn" onclick="App.closeSubpage()">‹ Settings</button>
                <span class="subpage-title">Social Assist</span>
            </div>

            <!-- Privacy Notice Banner -->
            <div class="guidance-prompt-card" style="margin-bottom: 12px;">
                <span class="guidance-icon">🔒</span>
                <span class="guidance-text" style="font-size: 11px;">
                    <strong>Privacy Sandbox:</strong> Facial recognition is optional and strictly isolated. Familiarity status has 0% weighting on collision risk.
                </span>
            </div>

            <!-- Master Toggle -->
            <div class="expand-panel open" style="margin-bottom: 12px;">
                <div class="expand-header" style="cursor: default;">
                    <span>Social Assist Engine</span>
                    <button id="social-master-toggle" class="pill-badge green" style="border: none; cursor: pointer;" onclick="SocialAssistPage.toggle()">
                        Active (ON)
                    </button>
                </div>
            </div>

            <!-- Contacts Directory -->
            <div class="expand-panel open">
                <div class="expand-header" style="cursor: default;">
                    <span>Enrolled Familiar Contacts</span>
                    <span class="pill-badge blue">3 Enrolled</span>
                </div>
                <div class="expand-body" style="display: block;">
                    <div class="kv-row">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 16px;">👤</span>
                            <div>
                                <div style="font-weight: 700; font-size: 12px;">Kshitiz (Team Lead)</div>
                                <div style="font-size: 10px; color: var(--text-muted);">Familiarity: Confirmed (98%)</div>
                            </div>
                        </div>
                        <span class="pill-badge green">KNOWN</span>
                    </div>
                    <div class="kv-row">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 16px;">👤</span>
                            <div>
                                <div style="font-weight: 700; font-size: 12px;">Priyesh (Judge / Reviewer)</div>
                                <div style="font-size: 10px; color: var(--text-muted);">Familiarity: Enrolled (92%)</div>
                            </div>
                        </div>
                        <span class="pill-badge green">KNOWN</span>
                    </div>
                    <div class="kv-row">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 16px;">👤</span>
                            <div>
                                <div style="font-weight: 700; font-size: 12px;">Unfamiliar Passerby</div>
                                <div style="font-size: 10px; color: var(--text-muted);">No biometric match in directory</div>
                            </div>
                        </div>
                        <span class="pill-badge gray">UNKNOWN</span>
                    </div>
                </div>
            </div>
        `;
    }

    function toggle() {
        socialAssistEnabled = !socialAssistEnabled;
        const btn = document.getElementById("social-master-toggle");
        if (btn) {
            btn.textContent = socialAssistEnabled ? "Active (ON)" : "Disabled (OFF)";
            btn.className = socialAssistEnabled ? "pill-badge green" : "pill-badge gray";
        }
    }

    return {
        init: init,
        toggle: toggle,
    };
})();
