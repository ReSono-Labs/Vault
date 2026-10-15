# Separate Vault Chat page and interaction quality

Current document set: [authority map](2026-10-07-live-memory-document-authority.md).
This plan owns its design concern only; original grounding controls requirements,
register controls build status, and historical reviews/manifests are not work orders.

2026-10-07 applicability: [Decisions/evidence grounding amendment](2026-10-07-decisions-api-evidence-grounding.md)
requires Phase01 revalidation of this plan's applicable draft, final-turn, causal
evidence, history coverage, evaluation and provider assumptions. GPT-Live is not
in scope. This notice is not a replacement design or renewed review approval.

Revision LMD-CHAT-PLAN-r6. Phase01 candidate; grounding r11 R19/R22/R24/R25/R34–37 and BP-R05 visibility clarification.
Supersedes r2 Home replacement/lifecycle proposal. Existing Voice page/hero,
transport, persistent mode and navigation behavior stay unchanged. New live-memory
voice enhancements remain separate authorized work; Chat must not force a merge.
Module architecture: [integration](2026-10-05-modular-codebase-integration-plan.md).

## Page and shared runtime

New frontend `conversation/ChatPage.tsx` is mounted for new Chat destination.
Desktop navigation: propose Chat directly after Overview; mobile navigation adds
same destination without removing Voice. Reuse navy/cyan/padding/type conventions
from supplied screenshot. Within Chat: header/title/New Chat/Sessions control,
bounded message viewport, compact composer fixed to Chat panel's bottom. No new
large microphone hero. Exact width/style placement awaits visual reference review;
behavior and all states below are mandatory. History rail/drawer design is in
[session plan](2026-10-05-chat-session-history-plan.md).

Shared path: draft revision → same LiveMemory preparation port as voice; Send →
same final validator and SearchPort → existing provider/tool authority. Different
channel/session IDs prevent voice and text drafts overwriting each other. Off
stops partial search only; final retrieval and autonomous analysis continue. Model
and tools do not execute on partial drafts. Chat backend is not support Help.

Chat uses selected text provider/model via existing credentials. Existing Voice
controller remains mounted at application level; Chat mount/unmount does not own
its lifetime. Owner BP-R05 now hides the correctly wired Chat microphone because
the separate Voice page remains. Preserve its right-side button/delegation and
actual on/connecting state props for restoration; no visible Chat microphone or
reserved layout space. [Exact restoration](../contracts/2026-10-07-LMD-C09C-hide-chat-mic.md).
Do not start a second Chat microphone or attach active Voice events to selected
Chat silently. Default voice destination remains its own session; adding dictation
into a Chat turn would require explicit reviewed mode/session binding. Voice and
Chat responses need audio/focus arbitration before simultaneous output, not mode
shutdown on navigation. Text works without microphone permission.

## Complete interaction acceptance checklist

Owner-requested live preparation display is controlled by
[LC-R05–07](2026-10-07-live-recall-context-grounding.md): compact provisional area
inside Chat while typing, actual memory selection and proposed decision/tool route,
current-revision updates and immediate clearing on Send. This is not a persisted
assistant message or execution indicator. Share the real live lifecycle/diagnostic
output; no display-only model/search calls. Implement after the shared preparation
mount is proved, not as a fake preview over the current draft-only controller.
UI clearing must not erase safe backend stress-test diagnostics or turn draft
predictions into learning evidence. Existing C09 owns this additional presentation.

The following are functional acceptance conditions, not optional polish:

| Area | Required behavior / concrete failure test |
|---|---|
| Layout | Message region fills available panel with min-height:0/flex/grid containment; only intended viewport scrolls. Composer never covers final message. Side rail and message region scroll independently. Test short/tall window and200%zoom |
| Alignment | Consistent readable content column; user and assistant distinct, aligned baselines/padding; multiline content/long URLs wrap. No offscreen bubbles or alignment shift as streamed text grows |
| Scroll following | Follow new output only while at bottom; manually scrolling up stops follow immediately. Show Jump to latest/new-output indicator; click restores follow. No forced jump each token |
| History scroll | Older-page prepend preserves first visible message/offset; loading images/fonts doesn't jump anchor. Restore per-session anchor on return. First-open policy latest, explicit jump links targeted message |
| Composer size | Starts one line, grows to modest bounded multiline maximum then scrolls internally. Proposed initial1–5lines; visual review pins exact height. No giant empty textarea or vertical drag ruining page |
| Keyboard | Enter submits, Shift+Enter newline; IME composition Enter never submits; empty/whitespace-only disabled unless supported attachment-only turn. Focus retained/restored predictably; buttons have labels/tooltips |
| Submission | One stable acknowledged user message, clear sending state before server acknowledgment, prevent double Send; preserve draft on failure. Pending assistant placeholder immediately after Send |
| Waiting/streaming | Visible animated ellipsis plus accessible waiting label before first content, then live text; distinguish waiting, tool running, interrupted and error. Never an indefinitely blank response area or false tool progress |
| Stop/retry | Stop reaches server cancellation, not just abort fetch; show stopping/stopped/incomplete content. Retry safe model/read work with stable IDs; unknown write effects never blindly rerun |
| Draft while busy | Allow composing next draft while turn runs; initial serialization makes Send unavailable with explanation until eligible, no accidental queued duplicate. Session switch preserves own draft |
| Rendering | Proper paragraphs/lists/code fences/tables; horizontally scroll wide code/table inside its own bounded area; copy text/code; safe link targets. Sanitize Markdown/HTML, no arbitrary execution from output |
| Attachments | Preview/name/type/progress/remove/retry; clear unsupported/error state; no silently missing selected file. Attachment tray bounded, no fullscreen composer expansion |
| Empty/loading/error | Useful empty page, history loading placeholder, recoverable load error, disconnected/reconnecting badge. Stale failed request cannot clear current session or overwrite another conversation |
| Mobile | Keyboard-safe viewport/composer/safe-area; Send visible, Chat mic intentionally hidden under BP-R05; rail becomes drawer; touch scrolling and focus work. If restored, mic retains adequate hit target |
| Accessibility | Keyboard reachable controls, focus-visible, named region/message roles, readable contrast; polite waiting/finished announcements without token-by-token flood; reduced motion honored |
| Persistence | Reload/reconnect restores server-acknowledged messages by ID; unsent text stays provisional; incoming response events deduped; route changes preserve active Voice behavior |
| Tool/result presentation | Compact expandable actual tool status/result and confirmation controls; distinguish completed/failed/effect_unknown; generated/downloadable file link has scope and availability checks |

Owner-approved selection: open-source assistant-ui headless primitives for viewport/composer/message
state using Vault-owned runtime adapter; [source review](../research/2026-10-05-chat-history-attachments-and-tools-research.md).
No assistant-cloud/persistence authority added. Pin peer dependencies and prove
existing React18 compatibility before integration; component adoption never
replaces these explicit tests. Library defaults may jump on switch/run and must
be configured to above behavior.

## Model/tool/session integration

Persist submitted final turn once; resolve current scoped context from server
history, validate preparation or normal final search, then invoke selected provider.
Stream actual response/available reasoning summaries with turn/response IDs to
common evidence owner. Reauthorize tools at call time with current grants; use
conversation tool adapter, no fake Voice microphone session. Attachments are typed
model parts through separate input adapter. [Attachments/tools](2026-10-05-chat-attachments-and-tool-parity-plan.md)
controls these responsibilities; [history](2026-10-05-chat-session-history-plan.md)
controls schema/context/ingestion. They replace r2's one-active/New-only assumption.

## Delivery and evidence

Owner explicitly requested mobile styling/formatting/spacing verification after
C09A. [C09B actual Chrome evidence](../reviews/2026-10-07-LMD-C09B-mobile-evidence.md)
records four measured mobile/tablet viewports and bounded corrections. It does
not certify physical keyboard behavior, full rendering or all acceptance below.

O4 entry: reviewed separate-page ownership, final search/tool/evidence ports;
O4-H history and O4-A attachments contracts can follow incrementally but remain
required scope. Positive evidence is actual text turn, authorized write tool,
waiting/streaming, full browser scroll/keyboard/mobile and existing Voice continuity.
Negative cases include delayed reply while reading old messages, loading older
history during stream, large image/code/table, failed Send/reconnect, IME, concurrent
tabs, revoked scope and unsupported model attachment. Use real-browser layout/
scroll tests and recorded screenshots at agreed desktop/mobile sizes; jsdom cannot
prove scroll geometry. Owner visual review after supplied reference, no self-
certified polish. Baseline Voice tests plus active audio navigation regression are
mandatory. No runtime behavior changed in this planning phase.

Rollback unmounts Chat destination and adapters only, preserving Voice page,
active mode semantics, acknowledged evidence and canonical memory. Stop on lost
history, duplicate tool effect, permission bypass, hidden waiting/failure or
scroll/input regression. Build/release cannot count a textarea or screenshots
alone as working Chat.
## October7 final-turn evidence wiring

DA-R05–07/10: conversation owns immutable submitted turns and actual model/tool
progress; composer draft predictions are not assistant messages or execution.
Associate original model proposals and available summaries with response/call IDs;
capture tool authorization, confirmation, claim, result and uncertain effects
through existing authorities and conversation_tools adapter. Do not fake a Voice
session for text. Record later explanation as reviewer inference. Decisions answer
is a selection record, not reasoning summary or tool arguments.

Shared evidence capture projects both chat and existing Voice into learning-plan
axes without changing legacy recovery states. A late summary cannot attach to the
next turn; failed capture remains incomplete. Stop/barge-in cannot undo an executed
write; effect_unknown remains available for existing recovery policy. No replay
when loading history. New Chat and persistent existing Voice remain separate.
Tests: model proposal never executed; result isError; duplicate Send/replayed call;
correction after apparent success; truncated summary; unsupported voice summary;
draft changed before Send; execution interrupted after dispatch. No GPT-Live events.
