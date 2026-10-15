# Reconciled live-memory, Chat and Decisions build scope

October8 applicability correction: this is the original delta allocation, NOT a
fresh absence audit of current code. Several “absent/not mounted” observations below
are now superseded by verified children in the current register. Do not build from those
old absence statements. [Current source/duplication reconciliation](../reviews/2026-10-08-scope-and-duplication-reconciliation.md)
and register own current evidence/status; original grounding still owns scope.

October8 post-C04E revalidation: [six remaining groups checked against code](../reviews/2026-10-08-remaining-build-code-revalidation.md)
is the latest remaining-delta evidence. Idle review/independent markers, exact
source provenance, vector cutover, settings UI and Decisions HTTP transport are
already built. Remaining long-Chat, Voice qualification/recovery, channel-specific
memory confirmations/provider adapters, attachments, semantic suppression/rebuild
and historical qualification must extend existing owners, not rebuild them.

Revision LMD-RECONCILED-r3, 2026-10-07. Phase01 correction candidate, internally
code-revalidated inventory; NOT READY implementation contracts. [Feature validation](../reviews/2026-10-07-feature-validation-index.md)
is the requirement-by-requirement evidence, not contract existence. Owner directed
merging all unimplemented scope into current build documents with no duplicates.
Grounding original r11 plus Decisions amendment r2 remains unchanged. No new
product scope, agent, permission, retention or activation policy is added.
This amendment supersedes conflicting build-status/dependency/path proposals in
older plans, not their requirements. [Document authority map](2026-10-07-live-memory-document-authority.md)
identifies the sole current owner of each concern. The current register owns allocation/lifecycle;
module plan r8 owns boundaries. Current baseline is actual code, including
uncommitted built files; no branch identification is required from the owner.

## What is already built — do not rebuild

| Existing owner | Actual implementation to retain | Mount/assurance |
|---|---|---|
| memory | schema.py records/versions/evidence/transcripts/summaries/ingestion/vector table; repository.py reconciliation/embedding/confirmation; retrieval.py lexical+Python cosine; pipeline.py factual finalize; openai_reviewer.py; openai_embeddings.py | composition.py mounts MemoryService, scoped embedding factory and VoiceMemoryLearning; existing factual learning is real, not a future task |
| voice | repository.py session/provider events; schema.py invocation/results/grants; tools.py LocalToolAuthority and VoiceToolRuntime; local_api/app.py events/close/finalize | Actual Voice workflow exists. Complete tool transcript coverage is NOT established: observer setter is not used in composition |
| credentials/providers | voice/credentials.py, oauth.py and current provider adapters; selected text credentials already used by Help/reviewer/Background | No additional credential/OAuth store, provider picker or fake model access |
| Help UI/text | help_assistant.py:ask; DocumentsPanel.tsx:HelpAssistantPanel; localApi.askHelp | Working domain-specific text chat, not general persistent tool-enabled Chat. Reuse eligible primitives; preserve Help-specific learning and document authority |
| files | workspace_files service/manager/local_operations; BrowserWorkspaceFileBrowser upload/preview/edit | Reuse storage and authorization; workspace file upload is not automatically private staged Chat attachment or model input |
| C01 | memory_search/contracts.py protocol and legacy.py delegation; MemoryService injected backend | Built default production search path remains legacy; same ranking/store. C02 SQL/index subset separate, not production cutover |
| C02 bounded SQL/index subset | memory_search/postgres.py, indexed.py, indexes.py; existing retrieval candidate hooks | [Exact contract](../contracts/2026-10-07-LMD-C02-indexed-query.md) and evidence/register govern proof. Existing service accepts adapter; production composition remains legacy, C13 cutover outstanding |
| C03A | conversation header/segment/final-turn repository/schema and optional erasure hook | Built, unmounted. Adds text submission identity/version semantics; contains repeated auth predicate. No second conversation schema permitted |
| C17A | decision_routing/contracts.py and selector.py finite mapper/parser/current-token/no-op | Built, unmounted and offline. No actual Decisions transport or rule execution |

Existing memory_type='decision' describes factual knowledge, NOT executable
procedural rules. Available sdk_runner AgentTurnObservation reasoning_summaries
is existing reusable collection, not session-wide capture proof.

## Remaining work: extend/wire versus genuinely new

Each row is a delta, not a whole replacement feature. A later bounded contract
must freeze exact methods/DDL after source revalidation; paths here are ownership
targets, not permission to scaffold all modules. Preserve approved assistant-ui
selection; assess existing React/visual primitives without silently replacing it.

| Allocation | Required missing behavior | Existing wiring target | Genuinely new duty/data justified by gap | Duplicate explicitly forbidden / required proof |
|---|---|---|---|---|
| C02 bounded delivered subset / C13 remaining cutover | Scoped SQL distance/lexical adapter and owned indexes, not installed migration/cutover | MemoryService -> C01 search interface -> C02 SQL adapter; canonical store/scoped factory unchanged | [C02 contract](../contracts/2026-10-07-LMD-C02-indexed-query.md) covers isolated query/index proof. C13 alone owns epoch/maintenance/production migration/cutover | Do not rebuild SQL/index adapter or embedding store. Source column alone is not proof; actual isolated plans/recall/restore in build evidence |
| C03R bounded repair | Provider event/transcript crash consistency, changed duplicate detection, missing projection repair | VoiceProviderEventCapture -> existing repositories' shared-transaction primitives | [Bounded implementation evidence](../reviews/2026-10-07-LMD-C03R-build-evidence.md); register owns status; no new ledger | Existing provider/transcript IDs authoritative. Real rollback/retry/concurrency tests; no tool replay. Full capture remains C03C |
| C03C | Actual model-call summaries/proposals; denial/error/replay/effect attribution; capture coverage | Existing SDK observation, VoiceToolRuntime claims/results, ToolCatalog observer; submitted C03A turn IDs for text | Minimum missing model-call/selection/coverage metadata only; gap-by-gap DDL necessity before READY | Do not copy raw transcripts/results into parallel ledger. Read source-linked projections; missing summary remains missing; tool isError distinct from transport success |
| C04 | Bounded review of ALL retained source, cross-window consolidation, durable retry/coverage | Existing MemoryPipeline/OpenAIMemoryReviewer/contracts/reconcile_memory/store_summary/ingestion | Review coordinator/coverage/recovery only where existing ingestion cannot represent complete windows | No second factual reviewer/reconciler. >100k tail, cross-window correction, duplicate/restart and independent procedural failure tests |
| C05 | VoiceMem factual/live integration evaluation and exact reusable donor selection | Planned live_memory/voicemem_adapter.py -> existing search port, not donor store | Retrieval-only adapted pinned donor subset if evaluation supports adoption; exact copied symbols/license/changes required | Upstream6cacb3c1e7fca2679f3bf95451f6b480efd9a783; adapter/symbols absent in current code. No Mem0/Qdrant/SQLite/ASR/persona. Do not confuse VoiceMemoryLearning with VoiceMem |
| C06 | Dynamic text edits/deletions and transcript revisions; parallel context/decision preparation; exact-final validation | Chat input/Voice transcript adapters -> existing search port + built selector | Bounded transient revision controller/current context IDs/cache invalidation; no durable draft learning | No speculative tool call. Delete/negation/ABA, late memory changes route, Send during jobs, cancel underlying-worker accounting |
| C07 | Persist Live Memory switch controlling preparation only | Existing local auth/API/settings UI and owned preference persistence | Minimum scoped preference/epoch, not generic replacement settings system | Normal final search/review continues Off; tests for revoke/Off/stale completion. Release default/scope stays grounded, not invented |
| C08 | General submitted text model/tools/stream/cancel with final evidence | C03A submit/load; existing scoped text credentials/SDK/helper ports; catalog + current grant authority; memory search | Conversation execution orchestration, transport streaming and conversation tool-context adapter | No second identity/grant/dispatcher/provider store, no fake Voice session. Existing Voice-specific claims/confirmation require explicit adapter, not bypass. Actual text-only tool/summary correlation/retry tests |
| C09 | Separate Chat surface with composer-right voice button, full scroll/keyboard/waiting/mobile behavior | BrowserVoiceApp persistent Voice state; Help message/draft patterns; approved assistant-ui primitives via Vault adapter | New Chat page/components and live revision client | Preserve existing Voice screen/transport and Help. Browser/layout/IME/stream/navigation proof, not textarea-only acceptance |
| C10 | Private history/resume/context without duplicate learning; O-DA-A historical evidence qualification | C03A IDs/version, existing source owners and learning-plan read-only audit procedure | Read/resume/context assembler and necessary coverage; separately bounded scoped qualification report before historical learning | No history copy/tool replay/re-ingestion. Actual private-history access needs reviewed scoped authority; no provider/publication/export inferred |
| C11 | Private staged images/docs, preview/extraction and real selected model parts | Existing file storage/authorization/upload/preview primitives, C03A submission | Staging/model-input conversion and missing attachment refs/coverage only | No new filesystem/upload manager or silent workspace publication. Actual model capability/limits, revoked preview, add/remove invalidation, cleanup |
| C12 | Incremental OpenAI transcription -> shared preparation/final validator | Existing microphone/Voice/provider/credential/OAuth lifecycle | Optional dedicated transcription adapter and application commit if actual supported path verified | No GPT-Live migration or parallel OAuth/ASR system. Exact entitlement not inferred from Voice token; existing Voice works without adapter |
| C13 | Epoch-safe maintenance and indexed cutover avoiding per-revision repair | MemoryService.ensure_vectors, scoped factory, store_embedding/content fingerprint | Bounded maintenance orchestration/indexed-backend cutover after C02 | No repeated embedder/backfill implementation. Correction/delete race, wrong-model and rollback real PG tests |
| C14 | Independent inactive procedural review and rebuildable rules/examples | Read existing finalized source; existing selected text-model access, strict JSON/capability descriptions | NEW procedural definitions/examples/generations and example vectors, reviewer capability (not agent) | No canonical memory rewrite, second event store or grants. Source-proven rules, no raw abandoned drafts, generation/forget/rollback tests |
| C15 | Stable semantic capability mapping, eligibility and final authorized routing | C14 -> built C17A; existing ToolCatalog/current grants | NEW explicit capability-to-current-provider/tool/schema/effect read adapter, eligibility and generation validity | Reuse catalog/grants; no guessed equivalence/parallel registry. Unknown/multiple providers defer; stale selection cannot execute |
| C16 | Integrated useful-response/quality/cost/removal acceptance | Existing/new actual tests and runtime paths | Evaluation fixtures/measurements only | Do not count mocks/schemas as deployment or useful-audio latency evidence |
| C17B | Real standalone Decisions transport | Inject DecisionTransport into actual C17A DecisionSelector; resolve existing credentials | NEW optional API transport, compatibility/error/deadline integration | No duplicate DTO/parser/choose; no GPT-Live; account/SDK/authorized budget proof before real call |

C03B/r1 is superseded WITHDRAWN DESIGN, not a mandatory prerequisite. Necessity of its
extra user_final metadata row beyond already persisted source fields is unproved; do not
create it just to unlock later work. Parent C03 and C17 are allocations consumed
by split work, not additional builds. C01 r1/r2 historical revisions are not tasks.
C03C must not depend on withdrawn C03B; it consumes actual existing source owners.

## Exact owner boundaries and integration rules

1. Source transcript authority stays memory repository; Voice provider/tool ledgers
   stay execution authority; C03A owns immutable text submissions. A read-only
   evidence adapter can unify refs without copying every row into another store.
   New metadata requires proving it is absent and cannot be represented safely by
   existing schemas. Atomicity repair changes owners minimally, not wholesale rewrite.
2. MemorySearchBackend actual retrieve signature is authoritative for C02. The old
   proposed search(scope,filters,deadline) is NOT already built; changing it requires
   its own compatibility review, not silently forking interfaces.
3. Conversation auth repeats Voice predicate. Resolve shared current-authority
   enforcement by reviewed minimal adaptation before mounting text tools; do not
   create a third policy implementation or remove locks casually.
4. Existing factual pipeline publishes canonical memory. Procedural consumer has
   independent outcomes and uses source refs; its failure cannot block factual
   publication. Nothing grants a tool because a rule/example/selection matches.
5. Live controller owns provisional revision/context work only. Models may inspect
   permitted partial text for the owner's test, but no tool execution/durable raw
   draft learning. Final committed meaning and actual execution remain distinct.
6. Stable semantic capability resolution is required by original R17 and absent
   from current tool_id/name/schema fields. C15 owns the minimal explicit mapping
   adapter over the existing catalog; representation/signature requires review.
   No model-guessed equivalence or parallel tool/grant authority.

## Dependency sequence, not a claim that everything needs rebuilding

The bounded C03R repair and C02 SQL/index subset are covered by their contracts/
evidence; do not rebuild them. C05A/C06A bounded unmounted component is also covered
by [actual build evidence](../reviews/2026-10-07-LMD-C05A-C06A-build-evidence.md),
not completion of full C05/C06. Next Phase02: review C06 real current/relevance
loaders and C13 epoch/maintenance prerequisites against actual Vault code, honoring
[LC-R01–04](2026-10-07-live-recall-context-grounding.md). One evolving context feeds
memory and decisions in parallel, with validated retention or drop/re-search.
C13 maintenance/cutover and C08 text-tool-context prerequisites remain source-backed
follow-on work. Source coverage/complete-review C03C/C04, preference C07, text
execution C08/Chat C09/history C10/attachments C11 retain their separate gates.
VoiceMem C05 is explicitly retained integration/evaluation scope, not forgotten;
it must not become a second memory owner or unnecessary prerequisite for basic
Chat. Dedicated transcription C12 remains conditional. Procedural C14/C15 and
optional actual Decisions transport C17B follow actual evidence/controller types.
No fixed count/estimate inferred; larger allocations may be split only for a
reviewable missing delta, never to recreate existing functionality.

## Mandatory no-duplication gate before every READY/build

Each contract must contain: requirement IDs; actual existing function/table/caller;
source hashes and current mounts; precise missing behavior; why reuse needs a delta;
allowed existing/new paths; no parallel owner; positive/negative regression cases;
fault/revocation/erase recovery; consumer compatibility; removal/rollback; tests
and explicit unperformed checks. Verify against working tree including untracked
code. If a claimed missing feature exists, remove that build scope. If a new row/
service duplicates source authority, HOLD until necessity/reuse is resolved.
Pre-build repeat inspection; post-build update evidence/mount status and subsequent
contracts against actual output. No old manifest/READY can reactivate superseded work.

## Revalidation evidence and limits

Eight feature reports identify current symbols, schemas, callers, missing behavior
and complete feature-plan obligations. Fresh test groups and unperformed checks
are in the feature index; earlier aggregate test counts are historical, not fresh
proof. C01/C03A/C17A are retained foundations, not complete feature acceptance.
No new schema, production DB inspection, donor edits, install or provider calls.
This correction merges missing scope into the existing planning authority; it does
not introduce new product features or make distant schema proposals executable.
Detailed Phase02 review still required before any new build contract is READY.
