/**
 * SpatialVector-HMI — Shared Haptic Body Diagram & Motor Controller.
 *
 * Visualizes 3-motor haptic belt/vest (LEFT, CENTER, RIGHT) with vibration
 * ripples, urgency badges, and pattern interpretation.
 */

(function (root, factory) {
    if (typeof define === 'function' && define.amd) {
        define([], factory);
    } else if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.HapticBodyDiagram = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    "use strict";

    const PATTERN_DESCRIPTIONS = {
        ALL_CLEAR: "Safe navigation path; all motors idle.",
        DEGRADED_WARN: "Sensor dropout warning pulse; caution recommended.",
        STOP_CRITICAL: "Emergency Stop! Collision hazard detected in all forward paths.",
        LEFT_SLOW: "Low-urgency prompt: veer slightly left.",
        LEFT_MED: "Active guidance: move into the left corridor.",
        LEFT_FAST: "High-urgency alert: obstacle detected; steer left immediately.",
        CENTER_SLOW: "Low-urgency prompt: forward corridor clear.",
        CENTER_MED: "Active guidance: maintain centered heading.",
        CENTER_FAST: "High-urgency alert: obstacles flanking sides; steer center.",
        RIGHT_SLOW: "Low-urgency prompt: veer slightly right.",
        RIGHT_MED: "Active guidance: move into the right corridor.",
        RIGHT_FAST: "High-urgency alert: obstacle detected; steer right immediately.",
    };

    function getPatternDescription(patternId) {
        if (!patternId) return "All clear — corridor safe.";
        return PATTERN_DESCRIPTIONS[patternId] || `Active pattern: ${patternId}`;
    }

    class DiagramController {
        constructor(containerEl, options = {}) {
            this.containerEl = containerEl;
            this.maxUrgency = options.maxUrgency || 5;
            this.motorElements = {};
            this.render();
        }

        render() {
            if (!this.containerEl) return;
            this.containerEl.innerHTML = `
                <div class="haptic-body-wrap">
                    <svg viewBox="0 0 280 200" class="haptic-vest-svg" style="width: 100%; height: 180px; max-width: 320px; display: block; margin: 0 auto;">
                        <!-- Vest Outline -->
                        <path d="M 60,30 C 90,15 190,15 220,30 L 250,85 L 230,175 C 230,185 200,190 140,190 C 80,190 50,185 50,175 L 30,85 Z"
                              fill="#f8fafc" stroke="#cbd5e1" stroke-width="2.5" stroke-linejoin="round" />

                        <!-- Center Spine Guideline -->
                        <line x1="140" y1="40" x2="140" y2="180" stroke="#e2e8f0" stroke-width="1.5" stroke-dasharray="4,4" />

                        <!-- Left Motor -->
                        <g id="haptic-motor-left" transform="translate(75, 110)">
                            <circle class="motor-ripple" r="26" fill="none" stroke="#3b82f6" stroke-width="2" opacity="0" />
                            <circle class="motor-base" r="18" fill="#ffffff" stroke="#94a3b8" stroke-width="2.5" />
                            <circle class="motor-core" r="9" fill="#cbd5e1" />
                            <text x="0" y="32" text-anchor="middle" font-size="10" font-weight="700" fill="#64748b" font-family="'JetBrains Mono', monospace">L</text>
                        </g>

                        <!-- Center Motor -->
                        <g id="haptic-motor-center" transform="translate(140, 95)">
                            <circle class="motor-ripple" r="26" fill="none" stroke="#3b82f6" stroke-width="2" opacity="0" />
                            <circle class="motor-base" r="18" fill="#ffffff" stroke="#94a3b8" stroke-width="2.5" />
                            <circle class="motor-core" r="9" fill="#cbd5e1" />
                            <text x="0" y="32" text-anchor="middle" font-size="10" font-weight="700" fill="#64748b" font-family="'JetBrains Mono', monospace">C</text>
                        </g>

                        <!-- Right Motor -->
                        <g id="haptic-motor-right" transform="translate(205, 110)">
                            <circle class="motor-ripple" r="26" fill="none" stroke="#3b82f6" stroke-width="2" opacity="0" />
                            <circle class="motor-base" r="18" fill="#ffffff" stroke="#94a3b8" stroke-width="2.5" />
                            <circle class="motor-core" r="9" fill="#cbd5e1" />
                            <text x="0" y="32" text-anchor="middle" font-size="10" font-weight="700" fill="#64748b" font-family="'JetBrains Mono', monospace">R</text>
                        </g>
                    </svg>
                </div>
            `;

            this.motorElements = {
                LEFT: this.containerEl.querySelector("#haptic-motor-left"),
                CENTER: this.containerEl.querySelector("#haptic-motor-center"),
                RIGHT: this.containerEl.querySelector("#haptic-motor-right"),
            };
        }

        update(hapticCommand) {
            this.reset();
            if (!hapticCommand) return;

            const dir = (hapticCommand.direction || "STOP").toUpperCase();
            const pattern = hapticCommand.pattern_id || "ALL_CLEAR";
            const urgency = hapticCommand.urgency || 1;
            const isVibrating = pattern !== "ALL_CLEAR";

            if (!isVibrating) return;

            const activeMotors = [];
            if (dir === "LEFT") activeMotors.push(this.motorElements.LEFT);
            else if (dir === "CENTER") activeMotors.push(this.motorElements.CENTER);
            else if (dir === "RIGHT") activeMotors.push(this.motorElements.RIGHT);
            else if (dir === "STOP") {
                activeMotors.push(this.motorElements.LEFT, this.motorElements.CENTER, this.motorElements.RIGHT);
            }

            activeMotors.forEach(m => {
                if (!m) return;
                const base = m.querySelector(".motor-base");
                const core = m.querySelector(".motor-core");
                const ripple = m.querySelector(".motor-ripple");

                const activeColor = (urgency >= 4 || dir === "STOP") ? "#ef4444" : "#2563eb";

                if (base) {
                    base.setAttribute("stroke", activeColor);
                    base.setAttribute("fill", (urgency >= 4 || dir === "STOP") ? "#fef2f2" : "#eff6ff");
                }
                if (core) {
                    core.setAttribute("fill", activeColor);
                }
                if (ripple) {
                    ripple.setAttribute("stroke", activeColor);
                    ripple.style.animation = `motorRipple ${Math.max(0.3, 1.2 - urgency * 0.18)}s infinite cubic-bezier(0, 0.2, 0.8, 1)`;
                    ripple.setAttribute("opacity", "0.85");
                }
            });
        }

        reset() {
            Object.values(this.motorElements).forEach(m => {
                if (!m) return;
                const base = m.querySelector(".motor-base");
                const core = m.querySelector(".motor-core");
                const ripple = m.querySelector(".motor-ripple");

                if (base) {
                    base.setAttribute("stroke", "#94a3b8");
                    base.setAttribute("fill", "#ffffff");
                }
                if (core) {
                    core.setAttribute("fill", "#cbd5e1");
                }
                if (ripple) {
                    ripple.style.animation = "none";
                    ripple.setAttribute("opacity", "0");
                }
            });
        }
    }

    return {
        create: (el, opts) => new DiagramController(el, opts),
        getDescription: getPatternDescription,
    };
}));
