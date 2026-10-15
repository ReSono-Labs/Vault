# C09A — separate mounted Chat surface over C08A

Source/necessity review, October7, before edits. Reuse exact Vault frontend
`BrowserVoiceApp.tsx`, `presentation/BrowserVoiceIcons.tsx`, `localApi.ts` authenticated
request/CSRF helper and `browser-voice.css` tokens. Existing Voice lifecycle stays
in its owner; Chat microphone delegates to that lifecycle. C08A is the sole
submitted execution/history/events/Stop backend, never a new inference server.

Donor: MIT `@assistant-ui/react` **0.15.25**, registry metadata inspected: React and
ReactDOM peers `^18 || ^19`, integrity
`sha512-uKAtDwMbdF2NY/F1L/sQNuNGU85tf7eyNSCZ2lBX4yddbsjP5FB3v46HxojRiIoeEyxsqe+6GS8p/RBb/YImuQ==`.
Official external-store and Thread primitive docs reviewed. Use headless external
store/thread/message primitives only, existing React18, no assistant-cloud/AI SDK/
new Node provider or copied hosted assistant. Lockfile records transitive versions.

NEW necessary `frontend/src/browser-voice/conversation/`: API types/delegation,
scope-owned controller and Chat presentation/CSS. BrowserVoiceApp only mounts and
passes existing identity/Voice state/callback. New desktop/mobile Chat navigation;
original Voice default/hero untouched. Mount Chat while authenticated and hide on
navigation so scoped transient drafts/selection survive. Workspace/user key remount
and logout unmount clear state/list/streams; all late replies fenced by teardown.

History lists/loads only; same conversation resumes without provider/tool replay.
One server-active turn, stable Send idempotency key and expected history version;
lost acknowledgment retries the same request, not a new tool run. EventSource
reads current scoped durable SSE with cursor dedupe, terminal/error/tool status and
text deltas; reconnect never submits. Navigation/disconnect ends viewing only.
Explicit Stop calls current server cancellation. Composer remains editable while
response runs; Send waits for terminal. IME/Shift+Enter preserved, right-side mic
delegates actual Voice toggle. Safe text rendering, autoscroll respects reader.

Bounded C09A excludes attachments, arbitrary editing/regeneration, pagination/
compaction, full tool-confirmation parity and live recall/Decisions mount. Draft
state is transient, not durable; no pretend speculative search. These remain
existing allocated work, not removed requirements. API errors are visible/retryable
and unknown/interrupted effects never show a blanket rerun action.

Focused tests: actual compiled React18 donor usage; Send/delta/final/Stop and
idempotency; history load/reopen no submit; late reply/scope teardown; navigation
preserves Voice/draft; text editing/IME; mobile CSS containment and scroll primitives.
Run existing Voice shell/API tests and production frontend build. Removal hides
Chat/unmounts its component and optional backend, preserving canonical history and
all existing Voice behavior. Full C09/full build acceptance remains separate.
No hosted assistant-cloud service is used. The selected package's normal transitive
cloud/stream/Radix libraries are retained in the lockfile, not configured as a
provider, persistence store or remote inference backend.
