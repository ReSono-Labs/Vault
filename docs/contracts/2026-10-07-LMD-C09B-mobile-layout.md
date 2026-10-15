# C09B — actual mobile Chat layout check/correction

Owner explicitly requests mobile styling/formatting/spacing inspection. Extend
actual C09A, not redesign Voice or add another UI library. REUSE exact Vault
`frontend/src/browser-voice/conversation/{ChatPanel.tsx,conversation.css}`,
`BrowserVoiceApp.tsx` shell and `styles/browser-voice-r1-console.css` mobile rules,
plus synthetic read fixtures from `BrowserVoiceApp.test.tsx`. Existing authority:
Chat plan's mobile/viewport/composer/wrapping/touch acceptance requirements.

NEW necessary developer-only browser fixture and zero-dependency Chrome/CDP check:
render actual shell + Chat + real assistant-ui with synthetic scoped history,
no provider/database/private account, no model/tool writes. Use installed Chrome
with fresh temporary profile, loopback Vite, mobile device metrics, screenshots and
measured geometry at narrow portrait, larger portrait/tablet and short landscape.
Do not claim jsdom proves layout or physical iOS/Android keyboard behavior.

Check long user/assistant text and URLs, dense session names, composer and mic/Send
hit targets, spacing, horizontal overflow, independent message scrolling and bottom
navigation overlap. Correct only demonstrated Chat-owned layout/formatting defects;
record baseline/final measurements/screenshots and exact edits. Existing Voice
presentation/lifecycle untouched. Missing Markdown/code/table rendering is recorded
truthfully rather than certified by a plain-text fixture. Actual keyboard/safe-area
hardware acceptance remains conditional without device evidence.

Rollback removes only Chat-owned corrections/test harness, preserving runtime and
canonical history. Allocation under existing C09; no new feature/model/agent.
