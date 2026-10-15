# C09B — actual Chrome mobile layout verification

Branch `feature/live-memory-decisions`. Owner requested mobile styling, formatting
and spacing. Actual BrowserVoiceApp shell, ChatPanel and assistant-ui primitives
rendered in installed headless Chrome with device metrics, synthetic scoped read
history only. No DB, paid provider, real account, microphone or tool effect used.
Same-context internal review, not owner visual acceptance or physical-device proof.

## Demonstrated defects and corrections

Baseline 667×375 landscape: composer bottom **401.44px** beyond the 375px viewport;
existing fixed mobile navigation starts **248.63px** and obscures Chat controls.
Baseline microphone/Send heights **41.77/41.19px**, below the intended 44px target.
Open session rail consumes 130px on narrow screens; the jump button consumes message
flow space even in the tiny landscape viewport. Screenshots were visually inspected.

Chat-owned corrections only:
- `useChatViewport` measures actual existing navigation/header and visual viewport;
  updates available Chat height on their resize and visual viewport resize/scroll,
  cleans up on hide/unmount. No hardcoded navigation row count or Voice lifecycle.
- Mobile sessions initially collapsed but expandable; stress fixture deliberately
  opens dense history to test worst-case containment. Short landscape uses a compact
  side rail, hides redundant Chat title/footnote and preserves message/composer space.
- Composer one-row start, bounded content sizing/internal scrolling, no vertical
  drag expansion, 16px text and side-by-side right-hand controls with 44px targets.
- Latest-message action moved out of message flow and hidden when disabled/at bottom.
  Existing donor action remains the scrolling authority.

## Final real-browser measurements

| Viewport | Composer bottom | Navigation top | Message viewport height | Mic / Send height |
|---|---:|---:|---:|---:|
| 360×800 | 618.84 | 673.63 | 260.36 | 44 / 44 |
| 390×844 | 662.84 | 717.63 | 304.36 | 44 / 44 |
| 768×1024 | 864.23 | 901.63 | 635.75 | 44 / 44 |
| 667×375 | 236.63 | 248.63 | 66.63 | 44 / 44 |

All four: no message horizontal overflow, independent message scrolling, composer
and controls visible above navigation. Real screenshots inspected after corrections:
[360 portrait](2026-10-07-C09B-mobile/360x800.png),
[390 portrait](2026-10-07-C09B-mobile/390x844.png),
[tablet](2026-10-07-C09B-mobile/768x1024.png),
[short landscape](2026-10-07-C09B-mobile/667x375.png).
[Full measured rectangles](2026-10-07-C09B-mobile/metrics.json).

Developer fixture `frontend/tests/chat-mobile.html` + `.tsx` renders actual shell/
navigation/history with long URLs/multiline text/dense titles, refusing all mutations.
Not a production build entry. Zero-dependency `check-chat-mobile.mjs` uses installed
Chrome/CDP, fresh temporary profile and loopback Vite. It asserts geometry/overflow/
touch targets and captures evidence. Run with Vite on4176, then
`node tests/check-chat-mobile.mjs <artifact-directory>` from frontend. Chrome process
and owned Vite stopped after verification; no user browser profile touched.

Final production React18 build passed; focused Chat/controller/Voice shell/API group
**21 passed in 3.88s**. No broad unrelated testing. Backend/model behavior unchanged.

## Limits retained

Physical iOS/Android keyboard, safe-area hardware, 200% zoom and all scrolling/focus
states remain unverified. VisualViewport integration is not proof of every mobile
keyboard implementation. Current content renderer is safe plain text, not full
Markdown/code/table formatting support; that existing parent requirement remains
open. This does not complete C09/full build, live preparation display or learning.
Original grounding unchanged; current source hashes are separately frozen.
