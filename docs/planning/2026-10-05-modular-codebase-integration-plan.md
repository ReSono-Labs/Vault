# Modular codebase integration

2026-10-07 revalidation notice: [Decisions/evidence grounding amendment](2026-10-07-decisions-api-evidence-grounding.md)
is controlling for the resumed API and speculative-evidence scope. This plan's
affected mapping, evidence, learning, removal and provider assumptions require
Phase01 revision, then Phase02 review. Earlier API-unavailable/deferred wording
is historical and does not override the amendment. No build readiness added.

Revision: LMD-MODULES-r9. Source-first integration; current build readiness and
implementation status belong only to the linked build-contract register.
Current document set: [authority map](2026-10-07-live-memory-document-authority.md).

C08A additive mount: `conversation/runtime.py` composes the existing passive
identity repository, configured credentials, canonical memory and shared SDK.
`conversation_tools/runtime.py` adapts the existing interactive catalog and durable
tool authority to real conversation/turn IDs; it creates no Voice session or
parallel grant/result ledger. `conversation/{api,streaming,runtime_store,runtime_schema,model_capture}.py`
own the submitted runtime, missing response sources and replayable SSE. Host files
only inject/delegate/emit/stop; shared runner callbacks are optional for old callers.
The passive C03A foundation's dependency boundary remains tested independently.
Current status/evidence stays in the register; full C08/C09/live adoption is not implied.

C09A additive mount: `frontend/src/browser-voice/conversation/` owns the API client,
transient scope-owned controller and separate Chat panel/style. BrowserVoiceApp
only lazy-mounts/preserves it and passes existing Voice state/toggle; sidebar owner
adds Chat. Existing localApi request/CSRF is reused, never cloned. Pinned MIT
assistant-ui headless primitives use external server-owned state; no hosted model
or client tool execution. Production live draft integration remains a subsequent
adapter into this actual controller, not permission to rebuild the Chat surface.

Current implemented seams: C01 MemorySearchBackend.retrieve, C03A immutable
submitted text and scoped loading, C17A finite selector contracts/parser. Preserve
them. Exact C03R source transaction and C02 SQL/index deltas are covered by their
reviewed contracts/evidence linked in the register, not permissions to rebuild
these seams. C03B extra user-final event design is withdrawn pending necessity proof;
no ledger may be created merely to satisfy a planned dependency. Existing Voice
provider/transcript/tool sources remain authoritative; source-linked projections
and minimum missing causal metadata require exact review. [Feature audit](../reviews/2026-10-07-feature-validation-index.md)
and [reconciled scope](2026-10-07-live-memory-reconciled-build-scope.md) override
conflicting proposed dependencies/status below. New paths/ports are still designs,
not evidence of implemented modules or edit permission.
Authority: grounding r11, especially R01/R26/R28/R31–R33 and the owner's latest
explicit instruction to document how new work enters the codebase. Evidence:
[existing implementation and overlap](../research/2026-10-05-current-memory-implementation-review.md).
This document is the sole ownership and wiring authority for the candidate.
Paths below are proposed module locations; no directories are created now.

## Historical regrounding checkpoint — not current code/status

Recovered from disk after compaction: controlling anti-drift protocol, Phase 01
prompt, grounding r11, current implementation/VoiceMem overlap r1, and all feature
drafts. Confirmed branch `feature/live-memory-decisions`, runtime baseline
`ea39a6f9da89a2999c4f7e14f686428d2088f480`, documentation-only working changes.
Latest task is exhaustive implementation planning, including storage/indexing,
embedding wiring, full-context memory analysis, VoiceMem adaptation, transcription,
OAuth, chat, live preference, evidence, learning and independent removal.
The existing review is evidence, not a proposed replacement architecture.

## Responsibility and dependency contracts

All backend locations are below `app/vault_runtime/`. Owner of implementation
is the future maintainer under reviewed contracts; Christian accepts outcomes.

| Proposed module | Owns / public port | Allowed dependencies | Prohibited duties |
|---|---|---|---|
| `memory_search/` | C01 search contract/default legacy adapter; C02 removable SQL backend/query and explicit concurrent index migration; fusion/loader/reranker/cutover remain separately reviewed | Canonical repository read/auth/connection adapters, scoped embedding factory; authorized administrative connection only for owned index migration | Canonical data writes, session review, scheduling drafts, credentials storage, tool execution |
| `live_memory/` | `revise`, `invalidate`, `prepare`, `validate_final`; revisions, coalescing, worker budgets, transient prepared context | Search port, preference port, optional interpretation port, clock/cancellation interfaces | Learning, granting access, executing tools, microphone transport, replacing canonical store |
| `live_memory/voicemem_stream.py`, `preparation.py` | Actual bounded C05A/C06A external-text extraction/shared parallel lifecycle; optional classifier/narrowing still separate evaluation | Canonical C17A types/C01 matches and required current/reuse ports; [exact contract](../contracts/2026-10-07-LMD-C05A-C06A-live-component.md) | No production loader/mount, VoiceMem ingestion, Mem0/Qdrant/SQLite store, ASR, persona, voiceprint, reply runtime |
| `memory_analysis/` | Snapshot, bounded review windows, hierarchical consolidation, coverage, durable retry and publication checkpoints | Existing memory reviewer, contracts, canonical reconciliation and embeddings; owned job repository | Background goals, chat response, procedural activation, vector search engine ownership |
| `conversation/` | Final submitted turns, model stream, final context handoff, tool delegation, evidence correlation | Existing selected scoped provider credentials and tool catalog; final search/live-validation ports; capture port | New agent identity, grant store, inline memory indexing or post-session analysis |
| `live_transcription/` | OpenAI transcription session configuration, provider event normalization, credential adapter, transport lifecycle | Existing credential resolver; conversation input port | Another ASR provider, memory writes, response/tool execution, storing OAuth tokens |
| `conversation_evidence/` | Scoped final-source projection, causal/summary/selection/coverage capture and acknowledgments; only necessary missing metadata persisted | C03A/Voice/provider/transcript/tool owners through reviewed atomic adapters; minimum justified metadata repository | Duplicate source-payload ledger, unsent facts, fabricated reasoning, reviewer/Background goals |
| `decision_learning/` | Independent procedural review, inactive proposals, version/example publication, rebuild jobs | Final evidence read port, capability descriptions, owned repository | Canonical memory reconciliation, grants, raw tool invocation, Decisions API assumptions |
| `decision_routing/` | Scoped examples/collapse, explicit semantic capability-to-current-tool/schema/effect mapping, eligibility, replaceable selector/fallback | Definitions/examples, existing ToolCatalog/current grant read ports; reviewed mappings only | Parallel catalog/grant engine, model-guessed equivalence, early execution, mandatory API |
| `feature_preferences/` | Live Memory preference and preference epoch | Existing authenticated user/workspace authority and database | Turning normal retrieval or memory analysis off |

Frontend proposed locations: `frontend/src/browser-voice/conversation/` owns chat
messages, composer, Send, voice button and stream display; `.../live-memory/`
owns draft revision client and preference control; `.../live-transcription/`
owns browser transport and application VAD/commit. Each communicates through
small typed ports. Use existing styling/tokens; no framework replacement.

Dependency direction: hosts compose modules; new modules use explicit ports
into canonical authorities. Canonical ingestion never imports optional live
memory or VoiceMem. Search has no dependency on conversation or learned decisions.
Decision learning and memory analysis consume final evidence independently.
No module imports the separate Background goal executor. Shared SDK observation
reuse may be injected through a small adapter; its current physical location
under `background_agent/` does not change responsibility.

## Exact existing-code seams

| Existing path | Allowed change | Logic that must remain in new module |
|---|---|---|
| `app/vault_runtime/composition.py` | Instantiate and inject services; mount optional no-op implementations; connect shared finalization entry for Voice, external memory and plugins | Query SQL, scheduler, chunking/retry, donor classifier, provider transcription state |
| `app/vault_runtime/local_api/app.py` | Authenticate, authorize, validate bounded envelope, delegate new handlers and mount route groups | Conversation execution, evidence ordering, transcription credential logic, live jobs |
| `app/vault_runtime/memory/service.py` | Delegate search to injected SearchPort; preserve callers and result contract | New HNSW queries, fusion, live scheduling |
| `app/vault_runtime/memory/repository.py` | Narrow scoped read/write primitives and atomic reconciliation/invalidation hooks needed by adapters | New engine, donor graph or reviewer orchestration |
| `app/vault_runtime/memory/retrieval.py` | C02 protected candidate-hook extraction only, preserve one existing merge/ranking/default algorithm | New SQL queries/index migration stay in memory_search; no inline scheduler |
| `app/vault_runtime/memory/voice_learning.py` and `pipeline.py` | Delegate complete-session processing through injected analysis port; retain canonical validator/publisher | Window planning, durable job loop, hierarchical consolidation |
| `app/vault_runtime/memory/openai_reviewer.py` | Bounded window/consolidation request adapter and explicit overflow response; remove silent truncation only under reviewed contract | Coverage coordinator or a replacement agent identity |
| `app/vault_runtime/voice/credentials.py` | Reuse scoped resolve/refresh; only add capability-specific access interface if needed | Second token store, browser OAuth export, transcription runtime |
| `app/vault_runtime/voice/openai_realtime.py` | Preserve existing voice path; delegate only proven new capability if shared transport required | Dedicated transcription config mixed into current realtime session builder |
| `frontend/src/browser-voice/BrowserVoiceApp.tsx` | Mount conversation component; forward existing scoped/session events and teardown | Composer state machine, VAD, speculative search, new chat model loop |
| `frontend/src/browser-voice/localApi.ts` / `SettingsPanel.tsx` | Small client binding/mount to component-owned API and setting | Inline feature implementations |

These are semantic limits, not blanket edit permission. Any additional existing
path needs documented necessity in its build contract. Every new file must have
one owner and purpose; no catch-all `utils`, duplicate credential client, or
copied runtime. Migration code belongs to its new owner, with one composition
hook; existing schema initialization must not acquire long-running index builds.

## Proposed integration envelopes

Backend API route names are candidate application routes, not provider endpoints:
`POST /conversations`, `POST /conversations/{id}/turns`,
`POST /conversations/{id}/drafts`, `POST /conversations/{id}/close`,
`GET/POST /preferences/live-memory`, and
`POST /conversations/{id}/transcription/session`. Streaming route/transport is
chosen in the near-term contract using existing server conventions. All derive
scope from the authenticated principal, check membership and session ownership,
and reject client scope substitution. Draft responses expose status/revision,
not tools or durable writes. Submitted turn has an idempotency key.

InputRevision contains conversation_id, utterance_id, provider_item_id when
present, content_index, revision, text, partial/final/abandoned, context_epoch.
PreparedContext contains scope identity, input fingerprint, preference_epoch,
authority_epoch, context_epoch, search/model identity, memory IDs/content versions
and metadata epoch, decision generation if used, expiry and status. Exact final
validation batch-checks current rows/membership, including metadata-only changes;
text equality alone is insufficient. Failed validation triggers normal final
retrieval, never stale reuse. SearchResult carries canonical payload and evidence,
method scores, embedding identity, incomplete/fallback status and versions.
These candidate fields are frozen into typed signatures in reviewed contracts.

## Composition, switches and removal

Live Memory user switch controls speculative preparation only. Distinguish it
from operator feature routing (new/legacy search, optional donor, new transcription,
procedural proposals/activation). Removing live preparation binds a no-op port;
normal final search and autonomous memory review still operate. Removing VoiceMem
binds plain hybrid search without importing donor dependencies. Removing procedural
learning leaves final evidence and memory learning intact. Removing Chat unmounts its separate destination;
existing Home/Voice mount and voice mode remain unchanged. Disabling new transcription restores the existing
voice path; do not send its provisional text into ordinary durable learning.

Register owned cleanup on conversation close, scope change, logout, preference
change and memory/credential revocation. Retain worker accounting until underlying
requests actually stop. Emit structured metrics using IDs/status/timing without
raw drafts, token values or secrets. Database authority is checked on use; caches
are disposable and must not make deleted content available.

## Modularity acceptance

Contract tests instantiate each component with fake ports and exercise real
behavior, then integration tests remove each optional component. Reject imports
from canonical memory into optional live/donor packages. Reject new schedulers,
query engines or conversation state in host files even if paths are allowlisted.
Verify Voice, external-memory and plugin search/finalization all retain their
scope and same canonical authority. Prove actual SQL query plan and complete
session coverage separately; import checks cannot establish either.

Enforcement in this candidate is manual review plus proposed dependency checks,
not an existing merge gate. Each build contract must name its path allowlist,
owned interfaces, required meaningful tests, rollback flag and deletion behavior.
No directories, API routes, tables or dependencies are created in Phase 01.

## r2 separate Chat expansion and wiring corrections

Grounding r9 replaces prior Home mount interpretation. BrowserVoiceApp only mounts
new Chat destination; it never replaces current Voice page, reparents Voice lifetime
into Chat or disconnects active voice on navigation. Add Chat destination/icon to
`frontend/src/browser-voice/presentation/BrowserVoiceIcons.tsx`; existing items stay.
Isolate Chat styles from Voice hero selectors; no global restyle to fit new page.

Additional new modules:
- `conversation_history/`: scoped list/load/context/source links; read canonical
  evidence and context checkpoints, no copying/provider transport reopen/learning.
- `conversation_attachments/`: private staging/typed model inputs/extraction with
  replaceable managed-storage port; no canonical memory authority or filesystem.
- `conversation_tools/`: current catalog/grant projection and conversation-scoped
  durable call/confirmation adapter; no new agent/grant or background executor.
Frontend matching history rail/drawer, attachment tray/capture adapter and tool
status belong below `conversation/`; backend pipeline remains shared live/final
memory ports. Dependency direction prevents optional UI from changing authority.

Narrow additional existing seams: `tools/definitions.py` may add optional generic
conversation/turn context fields without changing Voice meaning;
`voice/tools.py` may expose existing common authorization/claim policy through a
shared port while existing Voice implementation remains compatible; catalog
observer injection composes channel routing instead of overwriting Voice observer.
Existing memory confirmation adapter exposes generic final-evidence identity
without faking Voice session. These are inspected necessary adapters, not license
to move new Chat execution/recovery into current Voice files. Test both existing
Voice and Background paths unchanged. New history reads must not weaken old
VoiceSessionRepository's originating-login authorization; use separate authenticated
history projection. Future filesystem replacement is a tool-handler port swap,
not built now.

Exact owners and schemas: [history](2026-10-05-chat-session-history-plan.md),
[attachments/tools](2026-10-05-chat-attachments-and-tool-parity-plan.md),
[Chat quality](2026-10-05-vault-conversation-plan.md). Existing earlier path proposals
are governed by these r2 corrections. No new directories or runtime edits made.

## Phase02 source corrections and immediate foundation

Local server currently implements GET/POST/PUT/DELETE, no PATCH. Preference update
uses POST; CSRF/origin/auth follows existing identity route controls. Current
LocalApiResponse has complete payload/body only and server `_send` always buffers
and sets Content-Length. Streaming therefore requires explicit future owned
`conversation/streaming.py` event iterator/cancel/replay port plus narrowly allowed
`local_api/server.py` emission adapter and app response envelope adapter, preserving
ordinary finite response semantics. No hidden SSE support is assumed. Contract must
prove worker limits, disconnect versus Stop, event sequence replay, request deadlines,
headers and server shutdown cleanup; no long poll/model loop inline in HTTP host.

Server static frontend response sets Permissions-Policy camera=(). Optional camera
capture is unavailable until reviewed route/header capability change; file/paste
and user-triggered screen capture remain separate inputs. Don't globally enable
camera merely for appearance. Camera allowance must be necessary, self-only and
verified with browser permission; capture retained as conditional mechanism.

MemoryRecord has no retrieval_epoch; TranscriptEntry omits metadata although DB
stores it. Near-term typed result/evidence adapters explicitly load epochs/hashes/
attachment/summary references by authorized batch, preserving legacy dataclasses
and callers until additive typed contract reviewed. DB columns alone do not expose
these fields to prepared validation or session analysis.

First bounded foundation LMD-C01: owned SearchBackend protocol and default legacy
adapter, narrow MemoryService injection with identical default behavior, meaningful
caller compatibility tests. It creates no DB/index, no scoped-query policy, no
voice/frontend/provider feature. Search repair policy is explicit backend property;
legacy True, future indexed backend False to remove query-time backfill. Canonical
memory imports only lightweight search contracts/default adapter, never optional
live/donor packages; new query implementation remains owned memory_search.

Every new durable owner must register erasure cleanup in existing local_identity
user/workspace deletion seam before tables are activated. Scoped CASCADE joins
handle owned rows; storage blobs/provider references/cache cleanup needs explicit
outbox/checkpoint and failure status. No implicit erasure from FK existence. Forget
suppression identifiers themselves are privacy-scoped and cannot be a global
shadow store. Separate runtime owners must register stop() through composition/
LocalApiApp.close adapter, not use separate Background scheduler.
## October7 selector/evidence ownership refinement

decision_routing owns the optional openai_decisions adapter behind finite SelectorPort:
mapping validation/projection/request/response only. Its SDK imports are confined to
adapter, not core startup. composition injects no-op/model fallback; no new registry
or fixed-agent identity. decision_learning consumes qualified final evidence and
creates inactive proposals; conversation_evidence owns causal append/snapshot/load
and original reasoning availability, not usefulness judgments. live_memory owns
transient draft state and contextual selection scheduling; conversation_tools owns
actual claim/result/confirmation, using existing policy. Exact paths/signatures and
DDL freeze in contracts, no directory scaffold now.

Candidate EvidencePort exposes append_final_event, load_scoped_snapshot and
coverage status; SelectorPort exposes choose with immutable candidate mapping and
deadline; ReviewPort exposes propose(snapshot, existing_definitions). Diagnostics
must not copy raw unsent drafts into durable evidence. All producer projections
share one capture authority, not copied tool transcripts in decision tables.
Purpose-specific adapters reuse existing code where verified; new mapping is NEW
owner-directed work, not a donor port claim.

Manual review plus proposed dependency/removal tests (not existing merge enforcement):
core imports only ports; missing API SDK permits startup; disable selector/learner/
speculation independently; remove learned generation only under its owned boundary;
retain final evidence/canonical memory/current grants/history/existing Voice. Ensure
stop/revoke/erase callbacks include pending API work and its caches. Detailed
mapping and evidence semantics remain in selector and learning owned plans.

## Phase02 exact integration call graph and edit ownership

Draft: Chat composer revision client -> authenticated conversation/draft handler ->
live_memory.revise -> independent memory SearchPort and decision candidate repository ->
context-dependent SelectorPort -> transient PreparedContext. Browser input/change,
paste/delete/IME/attachment events update validity immediately; no network/model
work in BrowserVoiceApp. Payload contains utterance/revision/text/context refs;
server derives principal and validates bounded text. No tool claim in this chain.

Send: conversation.submit(principal, conversation_id, idempotency_key,
expected_history_version, final_input) -> C03A final-turn acknowledgment and
reviewed source-linked capture acknowledgment (no copied user-final row) ->
live_memory.validate_final (or no-op) -> search/selector fallback -> selected text
provider with current scoped ToolCatalog definitions -> conversation_tools.invoke ->
authority/claim/handler/result -> final response events -> independent finalization
consumers. Text provider is selected from existing credential/model connection,
NOT hard-coded gpt-6-luna (that is selector model only). Selection picks a workflow,
ordinary model or deterministic authorized workflow constructs validated arguments.

Voice: existing provider/events/tools API adapters -> same EvidencePort via reviewed
Voice source mapping; dedicated transcript revisions only on experimental path ->
application commit/final transcript -> current context validation/response authority.
Keep existing Voice mode alive across navigation and don't force GPT-Live events.
Close: sealed acknowledged segment -> memory_analysis and decision_learning independent
job claims. No browser-triggered canonical learning from a draft; no Background goals.

Necessary existing-file allowlists by later contract (not global edit permission):
C03 evidence: voice/events.py, voice/repository.py, memory/repository.py, voice/tools.py,
memory/voice_learning.py for transaction/capture adapters; composition.py for injection;
local_api/app.py for bounded envelope/ack delegation. tools/catalog.py only if tested
observer fanout is necessary, never rewrite authorization/dispatch. Capture BEFORE
catalog denial and AFTER claim/result at runtime seam; ledger replay emits replay
reference, not second execution. Observer not presently wired in production.
C08 conversation: tools/definitions.py additive conversation/turn identity fields;
local_api/app.py narrow route delegates; local_api/server.py streaming emitter only;
composition.py injection/stop; local_identity/service.py cleanup registration via
explicit owned callback port, no alternate account authority. Memory confirmation
adapter necessary for non-Voice final evidence, not grant policy rewrite.
C17 provider: new decision_routing/openai_decisions.py, owned contracts/types/tests;
pyproject.toml/uv.lock only under reviewed SDK compatibility slice; composition.py
optional factory/injection. No API handler sends credentials to browser.

Current frontend API supports buffered responses; C08 must freeze one stream protocol,
disconnect/Stop/replay behavior and bounded pending events before C09. Candidate
SSE (server->client response events) over authenticated GET plus CSRF-protected POST
submit/stop; event IDs are canonical response sequence. Cookie auth follows existing
same-origin local principal; no tokens in URL. Response events carry text delta,
tool status, error and terminal status with turn/sequence identity. History load
never causes server execution. If server adapter cannot support bounded disconnect
handling, return to review instead of inline model loop in request handler.

Release controls remain contracts, not invented flags spread through core: injection
of no-op live preparation; model fallback selector; absent learner consumer; legacy
search backend; existing Voice provider. No-op should import zero optional SDK/donor
packages. Server stop owns new workers; cleanup invalidates scope and caches before
erasure. Dependency checks manual/advisory until implemented and tested.
## Reviewed foundation allocation and ownership refinement

C03A owns conversation/{contracts,schema,repository}.py: private conversation header,
segment and immutable submitted text turn. No API/UI/runtime mounting or jobs.
conversation_evidence consumes actual parent/source IDs; no fake Voice session
or copied event prerequisite. C03B extra user-final row is withdrawn. C03 repair/
C03C reuse existing sources and add only reviewed missing metadata/coverage.
C08 consumes C03A and those adapters, not C03B or another conversation store.

C17A owns decision_routing/contracts.py and selector.py only: deterministic finite
wire projection/response parsing, validity callback and no-op. C17B owns optional
openai_decisions.py live transport after SDK proof; it does not redefine types.
No core imports optional SDK, no production mounting of foundation components.
C01 legacy search boundary unchanged. Exact allowlists/tests are in individual
contracts; source-repair/C03C/C08/C14/C15 remain review-before-build.

All contract splitting is necessary to remove real identity/capture and SDK/policy
dependencies; it does not change final product scope or fabricate achieved behavior.
Private conversations/observations are not shared because canonical memory is shared.
