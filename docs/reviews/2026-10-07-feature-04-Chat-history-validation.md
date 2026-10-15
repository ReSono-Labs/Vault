# Feature 04 — general Chat and continuation validation

Read COMPLETE vault-conversation-plan r4 and chat-session-history-plan r1 before
disposition. Compared navigation destination union/items, BrowserVoiceApp mounted
panels, HelpAssistantPanel/localApi.askHelp/backend handler, LocalApiResponse and
HTTP _send, C03A repository/contracts/schema, composition imports and actual tests.
Internal2026-10-07 code validation; no new UI/runtime/schema implementation.

Verdict: general persistent tool-enabled Chat and history/resume are NOT IMPLEMENTED.
Help text chat, existing selected text-model access, and C03A final-turn persistence
ARE IMPLEMENTED. C03A is unmounted: its existence does not make Chat functional.

| Chat plan obligation | Actual code evidence | Status |
|---|---|---|
| Separate desktop/mobile Chat destination, ChatPage | BrowserVoiceDestination/items have home/workspace/etc, no chat; no ChatPage or mount | NOT DONE |
| Keep existing Voice page/persistent runtime | BrowserVoiceApp owns current refs/media/transcript lifecycle; no replacement in change | Existing owner retained; new Chat navigation regression NOT VERIFIED |
| Composer-right voice button/current state and no second mic | Only existing Voice surface and Help composer | NOT DONE on Chat |
| Scoped finalized Send -> context/search -> selected text model | C03A submit_text persists final turn; Help ask resolves provider; no Chat runtime joining them | PARTIAL primitives; actual integration missing |
| General tools including writes/current grant/confirmation | Voice/catalog authority exists, tied durable claims to Voice session; Help answers document questions | NOT DONE Chat adapter; do not treat Help or direct catalog bypass as tool parity |
| Real incremental stream and reasoning/tool correlation | LocalApiResponse payload/body only; _send buffers bytes with Content-Length | NOT DONE Chat streaming/producer; ordinary Voice stream unrelated |
| Idempotent Send/history version | C03A submit_text checks key/content/version and commits once | DONE repository; NOT mounted API/UI acknowledgement |
| Stop/retry/reconnect/late event rejection | No Chat turn stream/cancel/replay endpoint | NOT DONE |
| Layout containment/alignment/wrapping | Help panel exists, no planned Chat viewport | NOT DONE for required Chat acceptance |
| Scroll follow/JumptoLatest/prepend anchor/session restoration | No Chat/history viewport or session rail | NOT DONE |
| Growing bounded composer/Enter/ShiftEnter/IME/focus | Help textarea has onChange and form submit, no approved Chat implementation | NOT DONE required behavior |
| Pending ellipsis/tool-running/error/interrupted states | Help working/error exists; no Chat response lifecycle | PARTIAL UI pattern only, NOT planned Chat |
| Draft while busy/per-session transient draft | Help state local single panel; no selected Chat sessions/controller | NOT DONE |
| Markdown/code/table/copy/safe links | Help renderMarkdown is existing primitive; no Chat surface/runtime | PARTIAL possible reuse, NOT Chat acceptance |
| Attachment tray/preview/remove/progress | No Chat composer/model attachment flow | NOT DONE; separate attachment feature |
| Empty/loading/reconnecting/mobile keyboard/accessibility/reduced-motion | Existing platform/Help patterns; no new Chat integration/browser evidence | NOT DONE for Chat, baseline UI not discarded |
| Server-ack message reload/current scoped persistence | C03A final input store only; Help client messages last8 | PARTIAL source foundation; model responses/read/reconnect missing |
| Tool result/confirmation/scoped downloads in Chat | Existing tool results/files exist but no Chat presentation | NOT DONE |
| Approved assistant-ui primitive integration/React proof | No assistant-ui dependency/import in actual package/source inventory | NOT DONE; owner selection retained, not silently replaced by Help |

| History plan obligation | Actual code evidence | Status |
|---|---|---|
| Stable private conversation/header/segment/turn identity | Actual C03A schema/repository | DONE bounded foundation |
| Sessions rail/drawer/list/title/status/pagination/rename | No Chat UI/list API; create returns existing title but no list/update workflow | NOT DONE |
| Resume same ID/new activity segment, no stale transport | Only segment0 creation; no resume/close segment method | NOT DONE; existing IDs reused, no second conversation schema |
| Authorized read-only older Voice projection/source links | Existing transcripts available internally; no history projection/source-link adapter/API | NOT DONE |
| Per-source/revision/consumer/contribution atomic coverage | memory ingestion tracks full transcript fingerprint; proposed coverage/contribution tables absent | NOT DONE; existing ingestion reused, not claimed equivalent |
| Server context recent/full tool pairs/checkpoints/older retrieval | Help client-provided last8; Voice startup limited prior summary/profile | NOT DONE general resumed Chat context assembler |
| New segment reviews only new contributions/corrections | Existing per-fingerprint finalize, no continuation contribution suppression | NOT DONE |
| Legacy >100k truthful unknown coverage/catch-up | Reviewer slices100000; no per-range success history | NOT DONE; source existence not completeness |
| Stream cursor/active turn/stop/concurrent tabs | C03A version check present, no active-running lease/stream orchestration | PARTIAL identity concurrency, remaining runtime missing |
| Scoped cache/draft/scroll cleanup and re-login history | No history UI/cache/API | NOT DONE integration |
| Repeated load zero model/tool/learning and resumed fact exactly once tests | C03A load tests exist; no actual history resume consumer | PARTIAL foundation tests; required end-to-end history tests missing |

Executed .venv/bin/python -m pytest -q tests/unit/test_conversation_identity.py
tests/unit/test_help_assistant.py tests/unit/test_tool_catalog.py
tests/unit/test_scoped_tool_catalog.py:32 PASS in0.74s. Prior C03A evidence includes
51 real scoped persistence tests; not rerun now. No browser geometry/active-audio
navigation or real text-model Chat execution validated. Chat plan's sentence
"ChatPage is mounted" describes proposed target, not a current source fact.

Reuse C03A and existing provider access/catalog/authority/visual primitives. Build
only execution/stream/current-context/tool-channel adapters, Chat UI and missing
history read/continuation duties. Do not copy Help-specific knowledge learning as
general Chat backend, fake Voice session, duplicate source history, or rebuild
already persisted submission identity. Repeated auth policy in C03A versus Voice
requires reviewed consolidation/adaptation before mounting, not automatic deletion.
