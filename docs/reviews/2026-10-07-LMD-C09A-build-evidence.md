# C09A separate mounted Chat — bounded frontend evidence

Actual branch `feature/live-memory-decisions`; original grounding hashes unchanged.
This extends the mounted C08A runtime, not another model server/Voice session or
duplicate tool catalog. Full original build acceptance remains open.

## Exact mount and dependency

`BrowserVoiceApp` lazily imports the owned `conversation/ChatPanel` after first
Chat navigation. It keeps that scoped component mounted while hiding other-page
views, with user/workspace key remount and logout unmount. Existing Voice lifecycle,
default hero and fixed identity are untouched; right-side Chat mic delegates its
actual toggle. Desktop/mobile navigation gains Chat without a session-list global
navigation item. Owned controller holds drafts transiently, never durable/browser
storage or automatic session learning.

MIT `@assistant-ui/react` pinned **0.15.25**, exact registry integrity in prebuild
contract and lockfile, React18 peers verified. Real external-store/thread/message/
viewport primitives compile and render. It is not a hosted assistant. Its package
has transitive `assistant-cloud`, `assistant-stream` and Radix dependencies;
no cloud client/provider/service is instantiated or configured by Vault. Existing
nanoid/postcss/undici overrides retained. No install scripts executed.

`conversation/api.ts` reuses existing authenticated request/CSRF helper, actual
C08A endpoints and credentialed native EventSource. Reconnect/history are read-only,
no client provider call/tool execution. Sequence dedupe and turn ID filter protect
stream application. Lost Send acknowledgment retains the exact original key/text/
conversation/version for Retry same submission; edited draft cannot become a
second uncertain submission. Stop alone requests cancellation. Navigation closes
viewing only. Selected-view cleanup and unmount fence late history/stream/Stop replies.
Draft editing during response is allowed; Send waits for terminal. IME/Shift+Enter
are preserved. UTF-8/NUL limits reject locally before creating a conversation.

## Final checks

Focused actual-donor/controller/Voice shell/API frontend group: **21 passed**.
Includes edits/deletes without submit, streaming dedupe, explicit Stop, draft
preservation across navigation, exact lost-ack retry despite edited draft, late
history rejection, scoped teardown, oversize UTF-8 rejection, actual donor canonical
history text rendering without HTML interpretation, existing Voice control and
all prior Voice shell/API regressions. No mocked assistant-ui primitives.

Production React18 TypeScript/Vite build passed; lazy Chat chunk ~290kB (86kB gzip),
existing main ~347kB (92kB gzip). Initial eager mount increased the main bundle and
required ResizeObserver even on unrelated pages in jsdom; lazy first-visit mount
corrected that. Browser-required ResizeObserver is supplied only in the donor DOM
test, not patched or replaced in production. No broad package/model upgrade.

Official [external-store runtime](https://www.assistant-ui.com/docs/runtimes/custom/external-store)
and [Thread primitives](https://www.assistant-ui.com/docs/primitives/thread)
reviewed before wiring. Installed types exposed required convertMessage; actual
identity converter added, rather than assuming current docs match every overload.

## Not claimed

No live memory/Decisions execution before Send yet; drafts are captured in the
owned transient input state for the next shared producer mount. No attachment
support, full memory mutation confirmations, Chat post-session learning, history
pagination/compaction, historical Voice import, running indicators across all
sessions, real-browser responsive/scroll visual acceptance or paid model/microphone
end-to-end proof. Existing contract allocations retain these requirements. DOM
tests prove actual donor rendering and controller behavior, not viewport geometry.
Do not rebuild this mounted Chat surface when adding those remaining adapters.
