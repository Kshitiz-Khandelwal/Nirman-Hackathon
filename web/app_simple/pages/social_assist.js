/**
 * SpatialVector-HMI — Subpage: Social Assist
 * UI-only prototype: Known contacts, Add Friend flow, Live Recognition demo.
 * No backend, no Arduino, no face recognition. Pure frontend state.
 */

window.SocialAssistPage = (function () {
    "use strict";

    let containerEl = null;
    let socialEnabled = true;
    let activeTab = "contacts"; // "contacts" | "live"
    let recognitionState = "known"; // "known" | "unknown" | "possible"

    let contacts = [
        { id: "c1", name: "Rahul", relationship: "Friend", photos: ["👤", "👤", "👤"], photoCount: 3, confidence: 91, status: "Ready" },
        { id: "c2", name: "Ananya", relationship: "Family", photos: ["👤", "👤", "👤", "👤"], photoCount: 4, confidence: 87, status: "Ready" },
        { id: "c3", name: "Arjun", relationship: "Classmate", photos: ["👤", "👤"], photoCount: 2, confidence: 94, status: "Ready" },
    ];

    // Add Friend form state
    let addFormState = { name: "", relationship: "Friend", photoDataUrls: [] };

    function init(container) {
        containerEl = container;
        render();
    }

    /* ================================================================
       MAIN SOCIAL ASSIST SCREEN
       ================================================================ */
    function render() {
        containerEl.innerHTML = `
            <div class="subpage-header">
                <button class="back-btn" onclick="App.closeSubpage()">‹ Settings</button>
                <span class="subpage-title">Social Assist</span>
            </div>

            <!-- Privacy Notice -->
            <div class="guidance-prompt-card" style="margin-bottom: 12px;">
                <span class="guidance-icon">🔒</span>
                <span class="guidance-text" style="font-size: 11px;">
                    <strong>Optional feature.</strong> Does not affect navigation safety. No data leaves your device.
                </span>
            </div>

            <!-- Enable Toggle -->
            <div class="expand-panel" style="margin-bottom: 12px;">
                <div class="expand-header" style="cursor: default;">
                    <span>Social Assist</span>
                    <button id="social-toggle-btn" class="toggle-btn ${socialEnabled ? 'on' : 'off'}" onclick="SocialAssistPage.toggleEnabled()">
                        ${socialEnabled ? "ON" : "OFF"}
                    </button>
                </div>
            </div>

            <!-- Tab Switcher -->
            <div class="segmented-control" style="margin-bottom: 14px;">
                <button id="tab-contacts-btn" class="seg-btn ${activeTab === 'contacts' ? 'active' : ''}" onclick="SocialAssistPage.switchTab('contacts')">
                    Known Contacts
                </button>
                <button id="tab-live-btn" class="seg-btn ${activeTab === 'live' ? 'active' : ''}" onclick="SocialAssistPage.switchTab('live')">
                    Live Recognition
                </button>
            </div>

            <!-- Tab Content -->
            <div id="social-tab-content"></div>
        `;

        renderTabContent();
    }

    function toggleEnabled() {
        socialEnabled = !socialEnabled;
        const btn = document.getElementById("social-toggle-btn");
        if (btn) {
            btn.textContent = socialEnabled ? "ON" : "OFF";
            btn.className = `toggle-btn ${socialEnabled ? 'on' : 'off'}`;
        }
    }

    function switchTab(tab) {
        activeTab = tab;
        const tabContacts = document.getElementById("tab-contacts-btn");
        const tabLive = document.getElementById("tab-live-btn");
        if (tabContacts) tabContacts.className = `seg-btn ${tab === 'contacts' ? 'active' : ''}`;
        if (tabLive) tabLive.className = `seg-btn ${tab === 'live' ? 'active' : ''}`;
        renderTabContent();
    }

    function renderTabContent() {
        const content = document.getElementById("social-tab-content");
        if (!content) return;
        if (activeTab === "contacts") {
            renderContactsTab(content);
        } else {
            renderLiveTab(content);
        }
    }

    /* ================================================================
       KNOWN CONTACTS TAB
       ================================================================ */
    function renderContactsTab(el) {
        if (contacts.length === 0) {
            el.innerHTML = `
                <div style="text-align: center; padding: 36px 0;">
                    <div style="font-size: 40px; margin-bottom: 12px;">👥</div>
                    <div style="font-size: 14px; font-weight: 700; color: var(--text-primary);">No contacts added yet</div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px; margin-bottom: 20px;">Add people you know for optional recognition.</div>
                    <button class="action-btn" style="max-width: 200px; margin: 0 auto;" onclick="SocialAssistPage.openAddFriend()">+ Add Friend</button>
                </div>
            `;
            return;
        }

        el.innerHTML = `
            <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 10px;">People you've added for optional recognition.</p>
            <div class="scenario-list" style="margin-bottom: 14px;">
                ${contacts.map(c => `
                    <div class="scenario-card" onclick="SocialAssistPage.openContactProfile('${c.id}')">
                        <div style="font-size: 28px; width: 40px; text-align: center;">👤</div>
                        <div class="scenario-card-body">
                            <div class="scenario-card-title">${c.name}</div>
                            <div class="scenario-card-desc">${c.photoCount} photos · ${c.relationship} · ${c.confidence}% confidence</div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span class="pill-badge green">${c.status}</span>
                            <span style="color: var(--text-muted); font-size: 18px;">›</span>
                        </div>
                    </div>
                `).join('')}
            </div>
            <button class="action-btn" onclick="SocialAssistPage.openAddFriend()">+ Add Friend</button>
        `;
    }

    /* ================================================================
       CONTACT PROFILE VIEW
       ================================================================ */
    function openContactProfile(contactId) {
        const c = contacts.find(x => x.id === contactId);
        if (!c) return;

        containerEl.innerHTML = `
            <div class="subpage-header">
                <button class="back-btn" onclick="SocialAssistPage.render()">‹ Contacts</button>
                <span class="subpage-title">${c.name}</span>
            </div>

            <div style="text-align: center; padding: 20px 0 16px;">
                <div style="font-size: 64px;">👤</div>
                <div style="font-size: 18px; font-weight: 800; margin-top: 8px;">${c.name}</div>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">${c.relationship} · ${c.photoCount} photos</div>
                <span class="pill-badge green" style="margin-top: 8px; display: inline-flex;">${c.status} · ${c.confidence}%</span>
            </div>

            <!-- Photo Grid Preview -->
            <div class="expand-panel open" style="margin-bottom: 12px;">
                <div class="expand-header" style="cursor: default;"><span>Photos</span></div>
                <div class="expand-body" style="display: block;">
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">
                        ${Array.from({length: c.photoCount}).map((_, i) => `
                            <div style="background: #f1f5f9; border-radius: 10px; height: 70px; display: flex; align-items: center; justify-content: center; font-size: 28px; border: 1px solid var(--border-subtle);">👤</div>
                        `).join('')}
                        <div style="background: #eff6ff; border-radius: 10px; height: 70px; display: flex; align-items: center; justify-content: center; font-size: 24px; border: 2px dashed #93c5fd; cursor: pointer;" onclick="SocialAssistPage.openAddFriend('${c.id}')">+</div>
                    </div>
                </div>
            </div>

            <!-- Details -->
            <div class="expand-panel open" style="margin-bottom: 14px;">
                <div class="expand-header" style="cursor: default;"><span>Contact Details</span></div>
                <div class="expand-body" style="display: block;">
                    <div class="kv-row">
                        <span class="kv-key">Name</span>
                        <span class="kv-val">${c.name}</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Relationship</span>
                        <span class="kv-val">${c.relationship}</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Photo Count</span>
                        <span class="kv-val">${c.photoCount}</span>
                    </div>
                    <div class="kv-row">
                        <span class="kv-key">Status</span>
                        <span class="pill-badge green">${c.status}</span>
                    </div>
                </div>
            </div>

            <!-- Actions -->
            <div style="display: flex; flex-direction: column; gap: 8px;">
                <button class="action-btn secondary" onclick="SocialAssistPage.openEditContact('${c.id}')">✏️ Edit Contact</button>
                <button class="action-btn" style="background: #fef2f2; color: #991b1b; border: 1px solid #fecaca;" onclick="SocialAssistPage.deleteContact('${c.id}')">🗑 Delete Contact</button>
            </div>
        `;
    }

    function deleteContact(contactId) {
        contacts = contacts.filter(c => c.id !== contactId);
        render();
    }

    function openEditContact(contactId) {
        const c = contacts.find(x => x.id === contactId);
        if (!c) return;

        containerEl.innerHTML = `
            <div class="subpage-header">
                <button class="back-btn" onclick="SocialAssistPage.openContactProfile('${c.id}')">‹ ${c.name}</button>
                <span class="subpage-title">Edit Contact</span>
            </div>

            <div class="expand-panel open" style="margin-bottom: 14px;">
                <div class="expand-header" style="cursor: default;"><span>Edit Details</span></div>
                <div class="expand-body" style="display: block;">
                    <div style="margin-bottom: 12px;">
                        <label style="font-size: 12px; font-weight: 700; display: block; margin-bottom: 6px;">Name</label>
                        <input id="edit-name-input" type="text" value="${c.name}" style="width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border-subtle); font-size: 14px; font-family: inherit;">
                    </div>
                    <div>
                        <label style="font-size: 12px; font-weight: 700; display: block; margin-bottom: 6px;">Relationship</label>
                        <select id="edit-rel-input" style="width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border-subtle); font-size: 14px; font-family: inherit; background: #fff;">
                            ${["Friend","Family","Classmate","Colleague","Other"].map(r => `<option ${r === c.relationship ? 'selected' : ''}>${r}</option>`).join('')}
                        </select>
                    </div>
                </div>
            </div>

            <button class="action-btn" onclick="SocialAssistPage.saveEditContact('${c.id}')">Save Changes</button>
        `;
    }

    function saveEditContact(contactId) {
        const nameInput = document.getElementById("edit-name-input");
        const relInput = document.getElementById("edit-rel-input");
        const c = contacts.find(x => x.id === contactId);
        if (c && nameInput && relInput) {
            c.name = nameInput.value.trim() || c.name;
            c.relationship = relInput.value;
        }
        openContactProfile(contactId);
    }

    /* ================================================================
       ADD FRIEND FLOW
       ================================================================ */
    function openAddFriend(existingId) {
        addFormState = { name: "", relationship: "Friend", photoDataUrls: [], existingId: existingId || null };
        renderAddFriendStep1();
    }

    function renderAddFriendStep1() {
        containerEl.innerHTML = `
            <div class="subpage-header">
                <button class="back-btn" onclick="SocialAssistPage.render()">‹ Contacts</button>
                <span class="subpage-title">Add Friend</span>
            </div>

            <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 14px;">
                Add a name and one or more photos of this person.
            </p>

            <!-- Photo Grid -->
            <div class="expand-panel open" style="margin-bottom: 14px;">
                <div class="expand-header" style="cursor: default;"><span>Photos</span></div>
                <div class="expand-body" style="display: block;">
                    <div id="add-photo-grid" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
                        <div class="add-photo-slot" onclick="SocialAssistPage.triggerFilePicker()">
                            <span style="font-size: 24px;">+</span>
                            <span style="font-size: 10px; color: var(--text-muted);">Add Photo</span>
                        </div>
                    </div>
                    <input type="file" id="photo-file-input" accept="image/*" multiple style="display:none;" onchange="SocialAssistPage.onPhotosSelected(event)">
                    <p style="font-size: 10px; color: var(--text-muted);">Tap + to select photos from your device. Photos are not uploaded anywhere.</p>
                </div>
            </div>

            <!-- Name & Relationship -->
            <div class="expand-panel open" style="margin-bottom: 14px;">
                <div class="expand-header" style="cursor: default;"><span>Contact Info</span></div>
                <div class="expand-body" style="display: block;">
                    <div style="margin-bottom: 12px;">
                        <label style="font-size: 12px; font-weight: 700; display: block; margin-bottom: 6px;">Name</label>
                        <input id="add-name-input" type="text" placeholder="Enter name..." value="${addFormState.name}" oninput="SocialAssistPage.onNameInput(this.value)"
                            style="width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border-subtle); font-size: 14px; font-family: inherit;">
                    </div>
                    <div>
                        <label style="font-size: 12px; font-weight: 700; display: block; margin-bottom: 6px;">Relationship <span style="font-weight: 400; color: var(--text-muted);">(optional)</span></label>
                        <select id="add-rel-input" onchange="SocialAssistPage.onRelInput(this.value)"
                            style="width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border-subtle); font-size: 14px; font-family: inherit; background: #fff;">
                            ${["Friend","Family","Classmate","Colleague","Other"].map(r => `<option ${r === addFormState.relationship ? 'selected' : ''}>${r}</option>`).join('')}
                        </select>
                    </div>
                </div>
            </div>

            <!-- Continue -->
            <button class="action-btn" onclick="SocialAssistPage.goToReview()">Continue to Review →</button>
        `;

        updateAddPhotoGrid();
    }

    function triggerFilePicker() {
        const input = document.getElementById("photo-file-input");
        if (input) input.click();
    }

    function onPhotosSelected(event) {
        const files = Array.from(event.target.files);
        let loaded = 0;
        files.forEach(file => {
            const reader = new FileReader();
            reader.onload = (e) => {
                addFormState.photoDataUrls.push(e.target.result);
                loaded++;
                if (loaded === files.length) updateAddPhotoGrid();
            };
            reader.readAsDataURL(file);
        });
    }

    function updateAddPhotoGrid() {
        const grid = document.getElementById("add-photo-grid");
        if (!grid) return;
        const photos = addFormState.photoDataUrls;
        const photoSlots = photos.map((url, i) => `
            <div style="background: #f1f5f9; border-radius: 10px; height: 70px; overflow: hidden; border: 1px solid var(--border-subtle); position: relative;">
                <img src="${url}" style="width: 100%; height: 100%; object-fit: cover;">
                <button onclick="SocialAssistPage.removePhoto(${i})" style="position:absolute;top:2px;right:2px;background:rgba(0,0,0,0.55);border:none;color:#fff;border-radius:50%;width:18px;height:18px;font-size:10px;cursor:pointer;display:flex;align-items:center;justify-content:center;">×</button>
            </div>
        `).join('');

        grid.innerHTML = photoSlots + `
            <div class="add-photo-slot" onclick="SocialAssistPage.triggerFilePicker()">
                <span style="font-size: 24px;">+</span>
                <span style="font-size: 10px; color: var(--text-muted);">Add</span>
            </div>
        `;
    }

    function removePhoto(idx) {
        addFormState.photoDataUrls.splice(idx, 1);
        updateAddPhotoGrid();
    }

    function onNameInput(val) { addFormState.name = val; }
    function onRelInput(val) { addFormState.relationship = val; }

    function goToReview() {
        // Read current form values before rendering review
        const nameEl = document.getElementById("add-name-input");
        const relEl = document.getElementById("add-rel-input");
        if (nameEl) addFormState.name = nameEl.value.trim();
        if (relEl) addFormState.relationship = relEl.value;

        renderReview();
    }

    function renderReview() {
        const { name, relationship, photoDataUrls } = addFormState;
        const photoCount = photoDataUrls.length || 0;

        containerEl.innerHTML = `
            <div class="subpage-header">
                <button class="back-btn" onclick="SocialAssistPage.renderAddFriendStep1()">‹ Edit</button>
                <span class="subpage-title">Review Contact</span>
            </div>

            <div style="text-align: center; padding: 16px 0 10px;">
                <div style="font-size: 52px;">👤</div>
                <div style="font-size: 17px; font-weight: 800; margin-top: 8px;">${name || "(No name entered)"}</div>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">${relationship} · ${photoCount} photo${photoCount !== 1 ? 's' : ''}</div>
            </div>

            ${photoCount > 0 ? `
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px;">
                    ${photoDataUrls.slice(0, 6).map(url => `
                        <div style="background: #f1f5f9; border-radius: 10px; height: 70px; overflow: hidden; border: 1px solid var(--border-subtle);">
                            <img src="${url}" style="width: 100%; height: 100%; object-fit: cover;">
                        </div>
                    `).join('')}
                </div>
            ` : `
                <div style="text-align: center; padding: 16px; background: #fffbeb; border-radius: 12px; border: 1px solid #fde68a; margin-bottom: 14px;">
                    <span style="font-size: 12px; color: #92400e;">⚠ No photos added. Adding photos helps with recognition.</span>
                </div>
            `}

            <div class="expand-panel open" style="margin-bottom: 14px;">
                <div class="expand-header" style="cursor: default;"><span>Summary</span></div>
                <div class="expand-body" style="display: block;">
                    <div class="kv-row"><span class="kv-key">Name</span><span class="kv-val">${name || "—"}</span></div>
                    <div class="kv-row"><span class="kv-key">Relationship</span><span class="kv-val">${relationship}</span></div>
                    <div class="kv-row"><span class="kv-key">Photos</span><span class="kv-val">${photoCount}</span></div>
                    <div class="kv-row"><span class="kv-key">Status</span><span class="pill-badge green">Ready</span></div>
                </div>
            </div>

            <button class="action-btn" style="margin-bottom: 8px;" onclick="SocialAssistPage.saveFriend()">
                ✓ Save Friend
            </button>
            <button class="action-btn secondary" onclick="SocialAssistPage.renderAddFriendStep1()">← Go Back</button>
        `;
    }

    function saveFriend() {
        const { name, relationship, photoDataUrls } = addFormState;
        if (!name) {
            alert("Please enter a name for this contact.");
            return;
        }
        const newContact = {
            id: `c${Date.now()}`,
            name: name,
            relationship: relationship,
            photos: photoDataUrls.length > 0 ? photoDataUrls : ["👤"],
            photoCount: photoDataUrls.length || 1,
            confidence: Math.floor(85 + Math.random() * 12),
            status: "Ready",
        };
        contacts.push(newContact);
        addFormState = { name: "", relationship: "Friend", photoDataUrls: [] };
        render();
    }

    /* ================================================================
       LIVE RECOGNITION TAB
       ================================================================ */
    function renderLiveTab(el) {
        const states = {
            known: {
                label: "Known Contact",
                person: contacts[0] ? contacts[0].name : "Rahul",
                confidence: contacts[0] ? contacts[0].confidence : 91,
                color: "#10b981",
                badge: "green",
                icon: "✓",
            },
            unknown: {
                label: "Unknown Person",
                person: "Unknown",
                confidence: 0,
                color: "#ef4444",
                badge: "red",
                icon: "?",
            },
            possible: {
                label: "Possible Match",
                person: contacts[0] ? contacts[0].name : "Rahul",
                confidence: 62,
                color: "#f59e0b",
                badge: "yellow",
                icon: "~",
            },
        };

        const s = states[recognitionState];

        el.innerHTML = `
            <!-- Demo Mode Banner -->
            <div class="guidance-prompt-card" style="margin-bottom: 12px;">
                <span class="guidance-icon">🎭</span>
                <span class="guidance-text" style="font-size: 11px;">
                    <strong>Demo Mode:</strong> Use the selector below to simulate recognition states.
                </span>
            </div>

            <!-- Camera Placeholder -->
            <div style="background: #0f172a; border-radius: 14px; height: 180px; margin-bottom: 12px; position: relative; overflow: hidden; border: 1px solid #334155; display: flex; align-items: center; justify-content: center;">
                <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: flex; align-items: center; justify-content: center;">
                    <div style="text-align: center;">
                        <div style="font-size: 32px; opacity: 0.3;">📷</div>
                        <div style="font-size: 11px; color: rgba(255,255,255,0.3); margin-top: 4px;">Camera Preview</div>
                    </div>
                </div>
                <!-- Person detection box -->
                ${recognitionState !== "unknown" ? `
                    <div style="position: absolute; border: 2px solid ${s.color}; border-radius: 6px; width: 90px; height: 110px; top: 35px; left: 50%; transform: translateX(-50%);">
                        <div style="position: absolute; bottom: -22px; left: 50%; transform: translateX(-50%); background: ${s.color}; color: white; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 4px; white-space: nowrap;">${s.person}</div>
                        <div style="font-size: 28px; text-align: center; margin-top: 28px; opacity: 0.6;">👤</div>
                    </div>
                ` : `
                    <div style="position: absolute; border: 2px solid #ef4444; border-radius: 6px; width: 90px; height: 110px; top: 35px; left: 50%; transform: translateX(-50%);">
                        <div style="position: absolute; bottom: -22px; left: 50%; transform: translateX(-50%); background: #ef4444; color: white; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 4px; white-space: nowrap;">Unknown</div>
                        <div style="font-size: 28px; text-align: center; margin-top: 28px; opacity: 0.6;">👤</div>
                    </div>
                `}
            </div>

            <!-- Recognition Result Card -->
            <div class="expand-panel open" style="margin-bottom: 12px;">
                <div class="expand-header" style="cursor: default;">
                    <span>Identified</span>
                    <span class="pill-badge ${s.badge}">${s.icon} ${s.label}</span>
                </div>
                <div class="expand-body" style="display: block;">
                    <div style="text-align: center; padding: 10px 0;">
                        <div style="font-size: 28px; font-weight: 800; color: ${s.color};">${s.person}</div>
                        ${recognitionState !== "unknown" ? `<div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">${s.label} · ${s.confidence}% confidence</div>` : `<div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">No matching contact found</div>`}
                    </div>
                </div>
            </div>

            <!-- Demo State Selector -->
            <div class="expand-panel open" style="margin-bottom: 12px;">
                <div class="expand-header" style="cursor: default;"><span>Recognition Demo State</span></div>
                <div class="expand-body" style="display: block;">
                    <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">Select a state to demo what the UI looks like:</p>
                    <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                        <button class="quick-test-chip ${recognitionState === 'known' ? 'active' : ''}" onclick="SocialAssistPage.setRecognitionState('known')">✓ Known</button>
                        <button class="quick-test-chip ${recognitionState === 'unknown' ? 'active' : ''}" onclick="SocialAssistPage.setRecognitionState('unknown')">? Unknown</button>
                        <button class="quick-test-chip ${recognitionState === 'possible' ? 'active' : ''}" onclick="SocialAssistPage.setRecognitionState('possible')">~ Possible</button>
                    </div>
                </div>
            </div>
        `;
    }

    function setRecognitionState(state) {
        recognitionState = state;
        renderTabContent();
    }

    return {
        init,
        render,
        toggle: () => {},
        toggleEnabled,
        switchTab,
        openContactProfile,
        deleteContact,
        openEditContact,
        saveEditContact,
        openAddFriend,
        renderAddFriendStep1,
        triggerFilePicker,
        onPhotosSelected,
        removePhoto,
        onNameInput,
        onRelInput,
        goToReview,
        renderReview,
        saveFriend,
        setRecognitionState,
    };
})();
