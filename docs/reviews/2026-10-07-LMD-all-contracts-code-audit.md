# All build contracts versus baseline and built code

2026-10-07, revision r1. Owner-required duplication audit; internal source review.
No implementation authority, production DB access, paid calls or source edits.
BASELINE LIMIT: owner subsequently reports a full build a few days ago with only
Decisions deferred. That completed build has NOT been located. Main is the proven
previous checkout here, not yet proven to be the owner's completed build baseline.
All missing-code labels below apply ONLY to inspected checkout; do not use them
to authorize rebuilding or assert the owner's reported build never happened.
This replaces the unsupported remaining-build count. Every allocation in the
register is reviewed below; entries without standalone contracts are identified
as allocations, not exact reviewed build instructions.

## Baseline and comparison method

Previous branch is main: reflog records checkout main -> feature/live-memory-decisions
on 2026-10-05. Both refs point to ea39a6f9da89a2999c4f7e14f686428d2088f480.
git diff main...HEAD is empty: ALL change work is uncommitted. Therefore inspect
git diff main AND untracked packages, not committed diff alone.
Tracked app/frontend changes versus main are ONLY memory/service.py and
local_identity/repository.py. New runtime packages: conversation (4 files),
memory_search (3), decision_routing (3). No frontend, SDK or composition delta.
Existing source cited below is present in main unless explicitly called new.
Canonical source snapshot: LMD-all-contracts-code-audit.sha256 next to this review.
No graph available for understand-diff; direct source/diff/call-site review used.

## Every standalone contract document

| Document | Comparison with code | Disposition |
|---|---|---|
| 2026-10-05-LMD-C01-memory-search-boundary.md r1 | Same search-seam allocation superseded by r2/r3 | Historical, NOT another build despite old READY |
| 2026-10-07-LMD-C01-memory-search-boundary.md r2 | Same files/interfaces now present as r3 | Historical, NOT another build despite old READY |
| 2026-10-07-LMD-C01-memory-search-boundary-r3.md | MemoryService now delegates existing MemoryRetriever through new LegacyMemorySearchBackend | Built; retain, no ranking/store duplication |
| 2026-10-07-LMD-C03A-conversation-identity.md | New three-table private finalized-text foundation; unmounted, no model | Built, but identity/history overlap and repeated auth must be resolved before integration; tests are not necessity proof |
| 2026-10-07-LMD-C03-evidence-capture-contract.md | Existing provider events, transcripts, invocations/results already supply substantial evidence | Rewrite pending gap-only contract; stale C08 dependency and wholesale new-ledger proposal not approved |
| 2026-10-07-LMD-C03B-submitted-turn-evidence.md | Proposed user_final row repeats actual submitted-turn reference/fingerprint; no package/table built | BLOCKED, READY withdrawn; extra row necessity unproven |
| 2026-10-07-LMD-C17A-selector-boundary.md | New offline mapping/parser present; no existing equivalent standalone finite selector located | Built, no transport/tool dispatch; do not rebuild mapping in parent |
| 2026-10-07-LMD-C17-decisions-adapter-contract.md | C17A already owns types/projection/parsing; credentials and provider resolution already exist | Parent must be superseded by transport-only C17B using actual C17A interfaces, not reimplement choose/parser |
| 2026-10-05-live-memory-build-contract-register.md | Mixes parent allocations, historical contracts and future slices | Inventory only; corrected next-build freeze, audit matrix authoritative for existing-code distinction |

## Source-backed disposition of every allocation

Labels: RETAIN = built slice, EXTEND = existing owner with verified missing duty,
NEW = missing capability in inspected code, HOLD = necessity/design unresolved,
EVALUATION = tests/research/release work, not another runtime implementation.
No row below is READY just because absence was observed.

| ID | Baseline/current built evidence | Actual remaining delta and required validation | Classification |
|---|---|---|---|
| C01 | memory/service.py:search; memory/retrieval.py:MemoryRetriever; new memory_search/legacy.py delegates it | Search seam is built and tested; no repeat build. Default backend remains old retriever | RETAIN |
| C02 | memory/schema.py:vault_memory_embeddings contains real vector; repository.py:embeddings_for loads vector_json; retrieval.py calculates cosine in Python; no HNSW SQL in schema | Add scoped indexed SQL query/index over EXISTING embeddings, not a second store/embedder. Actual PostgreSQL explain/index-use/recall tests needed | EXTEND |
| C03 parent | voice/events.py capture; memory/schema.py transcript entries; voice/schema.py provider events/invocations/results; local_api/app.py events/close/finalize handlers | Existing data stays authoritative. Missing atomic projection repair, model-call/summary attribution, prediction-versus-final-use and coverage must be proven individually. New ledger necessity unproven | HOLD; gap-only extension review |
| C03A | New conversation/schema.py header/segment/turn; repository.py submission-key/history-version behavior; no composition import/mount | New schema adds text submission semantics absent in Voice, but broader session ownership overlaps. Repeated _require_authority predicate versus voice/repository.py is confirmed. Review reuse/adaptation and no dual history before mounting | RETAIN code, integration HOLD |
| C03B | Actual submitted turn already stores input_text/hash/history version; proposed events are metadata copies, no implementation | Remove automatic build route. Prove whether event identity beyond turn identity is necessary; prefer source references/views where sufficient | HOLD |
| C03C | Existing VoiceToolRuntime/LocalToolAuthority persist claims/results/errors/unknown effects; sdk_runner.py collects provided summaries; catalog has observer setter but composition does not set it | Reuse those producers/stores; wire missing evidence, do not rebuild execution ledger. Denials before claim and replay distinction need explicit tests; summary unsupported remains missing | EXTEND existing producers; design HOLD |
| C04 | MemoryPipeline.finalize already formats transcript, reviews, validates citations, reconciles, embeds and completes ingestion; OpenAIMemoryReviewer slices input at 100000 chars | Complete bounded source coverage/consolidation and durable review recovery are gaps, not missing reviewer/pipeline. Extend same factual authority; no replacement reviewer/store | EXTEND |
| C05 | Current factual memory retrieval/review exists; no VoiceMem adapter in inspected runtime | Comparative experiment only, not another canonical memory system. Must remain optional to basic chat/decisions unless evidence establishes dependency | EVALUATION |
| C06 | Existing final-transcript handling in BrowserVoiceApp; Help draft onChange only updates React state; no live_memory controller/package or corresponding draft API found | New revision/debounce/cancel/current-token controller and parallel scoped retrieval; reuse MemoryService and C17A, no provisional tool effects | NEW orchestration over existing services |
| C07 | Existing settings/account/provider UI and authority; no Live Memory preference or live controller found | Add only live-preparation preference to existing settings persistence/API/UI; normal search/review unchanged. Default remains explicit unresolved release gate | EXTEND settings |
| C08 | help_assistant.py:ask already resolves selected text model/provider and answers; DocumentsPanel HelpAssistantPanel submits text; existing Voice tools/grants/credential stores | General persistent tool-enabled text conversation/stream/cancel and summary observation are missing, but text provider access and tool authority are NOT missing. Evaluate existing helper/SDK ports without copying Help-specific document learning into general Chat | EXTEND text/provider/tool infrastructure |
| C09 | DocumentsPanel.tsx HelpAssistantPanel already displays messages, draft textarea, waiting/error state; BrowserVoiceApp owns persistent Voice state | Separate general Chat navigation/composer/voice button still missing. Reuse visual patterns and assess reusable Help primitives before adding UI library; do not replace Voice screen/runtime | EXTEND UI with new Chat surface |
| C10 | Existing transcripts/summaries/ingestion fingerprints; new unmounted ConversationRepository.load; Help history is client-limited last8 | Scoped list/paginated history/resume/context checkpoints and coverage not implemented as general conversation APIs. Reuse canonical sources, never duplicate transcripts or replay tools | EXTEND history/read APIs; schema HOLD |
| C11 | workspace_files service/manager/local_operations already upload files; BrowserWorkspaceFileBrowser existing upload/editor UI | Chat attachment tray, scope-bound model input refs/extraction/capture are missing; new upload store/manager not justified. Existing uploads do not establish multimodal model capability | EXTEND existing files + new model-input adapter |
| C12 | Existing voice/openai_realtime.py, gemini_live.py, xai_realtime.py, oauth.py, credentials.py; BrowserVoiceApp final transcript/event handling | Dedicated incremental transcription/preparation handoff not existing. Reuse current microphone/auth/provider boundaries; no second OAuth store. GPT-Live excluded; this allocation is conditional, not required to rebuild working Voice | CONDITIONAL extension |
| C13 | MemoryService.ensure_vectors plus ScopedOpenAIEmbeddingFactory; pipeline embeds accepted records; current search repairs vectors | Maintenance scheduling/epoch-safe indexed cutover may be needed after C02. Existing embedding generation/backfill logic must be reused, not recreated | EXTEND |
| C14 | memory_type='decision' in factual records; existing factual reviewer. No decision_definitions/examples/generation store or procedural reviewer found | NEW inactive procedural learning/schema, separate from factual decisions. Reuse authorized evidence/provider/validation primitives; do not copy canonical factual pipeline. Requires capture sufficiency first | NEW |
| C15 | Existing LocalToolAuthority/catalog enforce grants; new DecisionSelector is classification only, no execution | NEW learned-rule eligibility/routing integration; use existing tool grants/dispatch and immutable C17A mapping. No second permission engine, no selection-implies-authority | NEW routing integration |
| C16 | Existing unit/integration suites and prior build evidence, not end-to-end live/learned release proof | End-to-end accuracy/latency/cost/rollback/erasure evaluation; not another product module | EVALUATION |
| C17 parent | Offline selector already built; VoiceProviderCredentialStore resolves existing scoped providers | Do not implement parent as new selector; adapt only remaining transport/account integration under C17B | Superseded parent, HOLD |
| C17A | New decision_routing contracts/selector, actual 107-case suite in prior evidence | Already built offline boundary; no SDK/network execution. Existing tools do not duplicate this finite parser | RETAIN |
| C17B | No openai_decisions transport file; sdk_runner is ordinary model/Agents runner, not Decisions transport | NEW optional transport injected into existing selector. Existing credentials reused; SDK compatibility/access/authorized experiment still required; no duplicate parser | NEW adapter, conditional |

## Confirmed defects and overstatements

1. Repeated local authorization policy SQL in new ConversationRepository and
   VoiceSessionRepository. Conversation adds FOR SHARE; it is not a byte-identical
   duplicate, but repeats the same principal/membership eligibility policy.
2. C03B extra final-user event was marked READY without proving why turn identity
   and stored source fields were insufficient. Withdrawn before implementation.
3. Three C01 contract revisions retained READY prose, creating apparent extra
   work; historical contract labels must explicitly prohibit rebuilding.
4. C03/C17 parents describe already-consumed scope and stale interfaces/dependencies.
   Freeze/supersede rather than independently build them.
5. Baseline Help text chat and existing file upload were understated. General Chat
   and model attachment support remain gaps, but blanket no-chat/no-upload claims
   are false. Assess adaptation rather than reinvention.
6. Existing VoiceToolEvidenceObserver class is NOT wired in composition. Main also
   constructs ToolCatalog without set_invocation_observer. Existing durable tool
   results do exist; complete transcript tool projection is not established.
7. Real vector storage already exists. HNSW indexed query does not. Do not conflate
   these facts or build a second embedding datastore.

No second factual memory store, reviewer, reconciliation engine, embedding provider,
tool dispatcher or permission store was introduced by the three built slices.
That limited statement does NOT clear new conversation identity architecture or
justify the now-blocked proposed event ledger.

## Validation performed and limits

Executed focused command covering new boundaries and existing memory/reviewer,
Voice schema, Help and catalog tests: 180 PASS in 1.48s. Full tests/unit:
443 PASS, four FAIL in 13.31s: Mail capability audience, prohibited frontend
build-agent wording, MCP migration assessment, prohibited runtime build_agent
markers. Same failures recorded previously; relevant baseline source untouched.
No green whole-suite claim. Implementation manifests for C01/C03A/C17A checked.
git diff --check clean. No actual-user historical DB read or migration.

Prior C03A evidence records 51 real isolated-Postgres tests; not rerun in this
non-mutating audit. Current passing unit tests establish tested behavior, not
production mounting or necessity. Frontend source reviewed; browser/TS build not
performed. Absent-package/symbol searches are scoped repository evidence, not
proof that no reusable implementation exists in any donor or external system.

## Mandatory next gate

No build READY. Use this matrix to revise gap-only contracts and governing plans.
First locate/reconcile the owner-reported completed build. This is a material
baseline blocker; the inventory below cannot substitute for that comparison.
For each proposed change, name baseline owner, reused function/table, actual missing
behavior, minimal allowed delta and positive/negative checks against existing code.
Resolve conversation identity/history and C03B necessity before selecting any new
capture schema. Do not delete existing work or use a new remaining-count estimate
as architecture evidence. Future remainder must be validated against actual built
interfaces/mounts, not assumptions in old plans. Complete runtime integration and
actual provider/DB evidence are required before corresponding readiness claims.
