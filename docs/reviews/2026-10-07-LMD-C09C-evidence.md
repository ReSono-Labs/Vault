# C09C — Chat microphone visibility verification

Owner BP-R05 implemented as a visibility-only change. The existing Chat microphone
button has native `hidden` plus a scoped CSS display guard; it occupies no space
and is excluded from normal keyboard/accessibility navigation. Its icon, callback,
active state and connecting disabled state remain intact. The separate Voice page
and host Voice wiring were not changed by this correction.

Restore by removing `hidden` from the existing microphone button in
`frontend/src/browser-voice/conversation/ChatPanel.tsx`. The host already delegates
to the existing persistent Voice session. See the [contract](../contracts/2026-10-07-LMD-C09C-hide-chat-mic.md).

Verification: production frontend build passed; 21 focused conversation, Voice
shell and local API tests passed. The component test confirms accessibility
exclusion and temporarily restores the button to prove its existing callback.
Actual Chrome mobile emulation passed at 360×800, 390×844, 768×1024 and 667×375:
microphone display none and zero dimensions, Send 44px high, no horizontal overflow,
scrollable history and composer above navigation. Portrait and short-landscape
captures were visually inspected.

Artifacts: [metrics](2026-10-07-C09C-mobile/metrics.json),
[portrait](2026-10-07-C09C-mobile/360x800.png),
[landscape](2026-10-07-C09C-mobile/667x375.png).
The fixture uses synthetic read-only history, not private sessions or provider calls.
This is not physical-phone keyboard verification or a claim that the wider live
memory/decisions build is complete. Original grounding and historical evidence
were not rewritten by this correction.

Current source snapshot: [implementation manifest](2026-10-07-LMD-C09C-implementation.sha256).
