# C09C — hide Chat microphone, preserve working Voice delegation

Owner request/BP-R05: separate Voice page remains; hide Chat microphone, preserve
correct wiring. REUSE exact existing Vault
`frontend/src/browser-voice/conversation/ChatPanel.tsx`, `conversation.css`,
`ChatPanel.test.tsx` and mobile fixture runner. No new module or Voice/controller
rewrite. Host `BrowserVoiceApp` remains unchanged.

Small reversible change: native `hidden` on existing Chat mic button, scoped
`[hidden]` display rule to prevent stylesheet overrides. Leave existing icon,
aria state/connecting disabled state, props and onToggleVoice callback intact.
Update Chat footnote to point to Voice page. Hidden button must not occupy layout
space or be keyboard/screen-reader reachable. No Voice page control is hidden.

Restoration: remove `hidden` from this button in ChatPanel only. Existing host
already passes voiceActive=isLive, voiceBusy=connecting, and callback to actual
toggleVoice. It controls the one existing persistent Voice session, never Chat
dictation, a fake Voice session or a second microphone. Scoped hidden CSS can stay.

Verify actual DOM hidden/accessibility exclusion and retained callback restoration;
existing Voice shell/API tests/build; mobile fixture asserts hidden mic and visible
Send with no spacing/overlap regression. Prior C09B screenshots are historical;
new captures must use a new directory. No backend/provider/database work needed.
