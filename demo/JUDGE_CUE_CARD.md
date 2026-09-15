# What NOT to say to judges

- ❌ "It prevents accidents." → ✅ "This prototype predicts collision risk; it is not a certified safety device."
- ❌ "95% accurate." → ✅ Only cite an accuracy number if you have measured test data on a defined dataset — otherwise don't cite a number at all.
- ❌ "Facial recognition makes it smarter." → ✅ "Facial recognition is a separate, optional Social Assist capability — it's not part of the safety-critical path."
- ❌ "Everything is on the server." → ✅ "Processing happens on a local edge server/laptop for this prototype; the phone is a client, not where computation happens."
- ❌ "TTC means probability of collision." → ✅ "Time-to-collision tells you the timing, not the likelihood — we combine it with intersection, CPA, and confidence to make a decision."

# One-line answers if a judge asks...

- "What happens if the camera fails?" → "The system enters a DEGRADED state and tells the user explicitly, rather than staying silent or guessing."
- "What about ground-level hazards, like curbs?" → "Out of scope by design — this complements a cane or guide dog for head/chest-level hazards, it doesn't replace one."
- "Why not just use proximity/distance?" → [Run Scene 2 and Scene 5 back to back live — same distance, different decision, that's the whole point.]
