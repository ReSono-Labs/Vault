# Changelog

## 2026-10-15 — Recover dropped Voice tool calls; Chat shares the live tool route

- "Load failed" during Voice: the phone's tunnel dropped long tool requests (every Web search, ~4 s in)
  while Vault kept running them. A replay of the same toolCallId now returns 202 pending, then the
  stored result; the browser retries only connection failures, so the answer still reaches the agent.
- Chat Send hands the text model the live tool route chosen while typing (sticky, authority rechecked)
  as a named proposal it may call directly; memory is searched at Send when none was reused.

## 2026-10-15 — Live tool route reaches the agent; no spurious "stale"

- Provisional live checks read the session row without a lock. Every authenticated request updates
  `last_seen_at`, and the locked read inside a REPEATABLE READ snapshot failed whenever a poll overlapped.
- Tool selection runs during speech (at most once per second, latest words), keeps the last good route,
  and the selected tool is sent to the Voice agent as a provisional hint (no pre-execution).
- Decisions calls reuse one pooled HTTPS client. The panel never shows "stale" for the tool route.

## 2026-10-15 — Voice tool selection no longer stale; no duplicate memory lookups

- Live Voice preparation no longer fences on the transcript count. Saving the utterance's final
  transcript and the agent's reply at the end of a turn had made every tool selection stale (14/14).
- The Voice agent is told that live memory was already searched for the current request and uses
  memory_lookup only when it does not cover the question.

## 2026-10-15 — Live search continuity, Decisions API, review recovery

- Live memory publishes as soon as it is found and stays visible for the whole utterance (last
  authorized result kept, rechecked each poll); "stale" now only answers a superseded revision.
- Tool selection waits for a 0.6 s pause and uses the OpenAI Decisions API (`gpt-6-luna`, API-key
  capability, 4 s deadline). Measured on the real 48-tool catalog: ~170 ms warm. Selector prompt V2
  (12/14 vs 11/14 on the same synthetic probe). D1 and its runtime, mount and image layer removed.
- Count-only `memory_delivered` and per-utterance `utterance_summary` diagnostics.
- Procedural review no longer fails a whole session when the model cites sources not linked to a
  point: those claims become unknown and cannot teach. Failure logs now name the rule that failed.

## 2026-10-15 — OAuth conversation with API-key transcription and Web search

- OpenAI live transcription and Web search now use the retained API key even while ChatGPT OAuth
  is the selected method (`API_KEY_CAPABILITIES` in the credential store; `resolve(..., capability)`).
  Every other feature keeps following the selected method. A missing key fails with a clear message.
- `liveTranscription` no longer depends on the selected method; the browser uses the dedicated
  session's text whenever it is open and ignores the conversation connection's own deltas.
- Saving an API key no longer switches the selected method to API key. Connections gains
  "Use API key" / "Use OAuth" when both are connected.
- Removed the unverified OAuth Web search branch (it never produced a completed answer).

## 2026-10-15 — Voice live memory searches while the user speaks

- API-key Voice no longer withholds the model response: the Voice agent always answers
  natively. The turn-end `/preparation/final` handoff, its manual `response.create`, and
  the `managedResponse` flag are removed (`liveTranscription` now only says whether the
  dedicated `gpt-live-transcribe` session should open).
- Transcript deltas from that session feed the shared preparation host during speech;
  retrieved memory is applied through `session.update` (now including `type: "realtime"`)
  and stays in the instructions until the next utterance, so tool follow-up responses keep it.
- The transcription session requests `delay: "low"`. ChatGPT OAuth is unchanged and still
  depends on the conversation connection's own transcript events.

## 2026-10-08 — branch consolidation and build stabilization

- Establish one current project checkpoint and contract register; retain dated
  evidence as history and amend existing contracts without creating new contracts.
- Page retained Chat display separately from model context; preserve original
  history and ensure earlier-page reads cannot replay tools or learning.
- Reuse pending memory actions for later-turn Chat correction/forget confirmation
  and original-turn explicit remember. Commit confirmation and mutation atomically.
- Add Gemini conversation protocol through the shared installed SDK runner.
- Reuse managed storage for private submitted image/document inputs, exact retry
  binding, real model parts, source rehydration, bounded extraction and staged expiry.
- Checkpoint Voice factual analysis in existing ingestion rows and publish facts,
  summary and completion atomically. Reuse the review bridge/dispatcher for retries.
- Repair stale tests and isolated DB fixture setup; serialize destructive test suites.
- Full release gaps remain in the existing register; prior deployment is separate
  from the newer completion worktree.

## 2026-10-08 — Chat forgetting provenance

- Include validated original Chat source IDs in the existing canonical forgotten-
  memory replay guard, so null Voice transcript IDs do not bypass same-identity
  paraphrase suppression. Retain history, existing scoping and confirmations.
- No separate store/model; changed-identity/new-source semantic replay remains
  outside this deterministic guard's verified boundary.

## 2026-10-08 — continuous Chat review boundary

- Reuse normal session sealing and review dispatch after completed responses at
  32 turns or48000 input/event bytes, without waiting for idle or closing Chat.
- Preserve original history and message versions; continue through the existing
  current-segment/previous-summary context path. Oversized single turns remain
  explicitly unsupported by the procedural source guards.

## 2026-10-08 — resumable procedural assessment/output windows

- Keep full original source visible while reviewing bounded decision-point groups;
  continue dense proposals explicitly and retain validated pages across retry.
- Merge exact behavior duplicates without losing point/source/example references;
  preserve fixed assessments and validate the complete aggregate before existing
  semantic reconciliation/publication. No partial-page activation.
- Retain explicit source-input and reconciliation overflow guards; this is not
  arbitrary-length procedural source review.

## 2026-10-08 — reuse Voice session context for Chat continuation

- Reuse Voice's bounded prior-summary formatting with existing completed Chat
  review output and current-segment history, rather than resend all old segments
  or introduce another summary-model call. Keep saved originals intact.
- Capture and verify actual segment history and prior-summary source references
  for procedural review; preserve legacy context verification unchanged.
- Large uninterrupted segments and paginated large-history display remain open.

## 2026-10-08 — resumable factual Chat review windows

- Review complete sealed Chat evidence in bounded original-source windows, with
  explicit candidate continuation instead of silently retaining only32 facts.
- Persist validated source/model-bound steps, reuse them after interruption, and
  consolidate exact-key corrections with the existing configured reviewer.
- Keep canonical memory and completion atomic through the existing pipeline;
  retain exact source offsets. Conversational compaction and procedural/Voice
  windows remain separate unfinished work.

## 2026-10-08 — idle Chat review and durable coverage

- Review completed Chat segments after two minutes of inactivity through the
  existing recovery worker; keep the same Chat open and resumable.
- Use text-free throttled edit activity, current authority and a locked idle
  recheck; never learn from drafts or interrupt active responses/tools.
- Persist independent memory/decision coverage, original-source dispositions and
  publication references; retries skip the successful consumer. Empty proposals
  are distinguishable from unreviewed evidence through scoped review-status.

## 2026-10-08 — exact factual review source spans

- Preserve original Chat evidence IDs, SHA256 fingerprints and character offsets
  on canonical memory evidence through the existing publication transaction.
- Add lossless bounded source partition/coverage validation for complete-session
  review; reject missing, reordered or altered spans.
- Retain existing overflow guards until resumable window review/consolidation is
  mounted. No duplicate reviewer, source history, worker or memory store.

## 2026-10-08 — shared Voice live preparation mount

- Connect Voice partial transcription to the existing Chat/VoiceMem preparation
  host, indexed memory search and learned-decision candidates; no second engine.
- Validate the captured final before responding, reject stale partials, and retain
  normal final retrieval when speculative context cannot be reused.
- Preserve ordinary Voice/OAuth; the experimental API-key path uses dedicated
  transcription, with no tool execution from drafts or new permission grants.
- Mounted synthetic-provider/Postgres and focused browser checks are recorded in
  C06F evidence; real microphone/provider acceptance is not claimed.

## 2026-10-08 — durable Chat review recovery

- Queue ended-segment review atomically even when existing worker slots are full.
- Recover explicitly queued Chat reviews after restart using existing workers,
  advisory locks, current local-session authority and factual/procedural checkpoints.
- Bound automatic attempts, preserve explicit retry and log scoped lifecycle state.
- No historical backfill, tool replay, new learning model or parallel memory store.
  Full-session windowing and Voice recovery remain separate unfinished scope.

## 2026-10-07 — compiled Decisions catalog and outcome review

- Added additive catalog compilation/atomic scoped pointer, current read-only
  qualification gates, revision fencing and source-erasure invalidation.
- Added guarded active pgvector candidate reads through the existing SQL owner.
- Extended the same-model procedural reviewer with an explicit goal, separate
  correctness/satisfaction axes and durable evidence-linked failure assessments.
- Existing memory analysis unchanged; production source/worker/live mounts and
  final whole-flow review remain. Evidence/status live in the contract register.

## 2026-10-07 — C13A vector snapshot publication safety

- Fixed reproduced canonical vector check/upsert race using existing scoped
  authority/memory locks; both embedding producers pass captured memory versions.
- 49 real database tests and 243 focused units pass; full units 532 pass with
  four prior failures. No schema, provider or production cutover change.

## 2026-10-07 — bounded VoiceMem/shared-context extraction

- Added isolated external-text VoiceMem subset and one parallel memory/decision
  preparation lifecycle; explicit guard/reuse ports, no production mount.
- Tested revision invalidation, validated retention, late-context reconsideration,
  final validation and actual worker lifetime. 41 new tests; 239 focused passes;
  full units 528 passed with four previously recorded failures.
- Preserved canonical implementations and original grounding. Comparative quality,
  real epoch/relevance wiring, preferences and Chat/voice integration remain separate.

## 2026-10-07 — bounded C02 SQL/index group and shared live-context clarification

- Added removable indexed PostgreSQL search adapter and explicit concurrent HNSW/
  GIN migration over existing memory; preserved one rank policy and canonical store.
- Verified39 isolated DB tests,25 new unit tests;487 full-unit passes, four known
  failures. Natural HNSW/GIN and synthetic scoped exact-recall/restore proof saved.
- Production cutover remains separate. Recorded shared parallel recall/decision
  context and active VoiceMem/controller next grouping; original grounding unchanged.

## 2026-10-07 — C03R bounded existing-source repair

- Shared the existing Voice provider/transcript transaction; exact retries repair
  missing projections and conflicting transcript retries fail without overwriting.
- No new table, provider or tool execution. Final proof: 19 focused unit passes,
  31 PostgreSQL passes; full units 462 passed, four previously recorded failures.
- Current authority/register/checkpoint aligned; original grounding unchanged.

## 2026-10-07 — grounded document authority consolidation

- Established one current document entry with one owner per concern.
- Corrected capture dependencies, historical build directions, capability/historical
  audit allocations and donor/NEW provenance; original groundings unchanged.
- Historical reviews/manifests preserved; no runtime change in this correction.

## 2026-10-07 — planning/source validation correction

Added eight feature-by-feature planning-to-code reports and reconciled remaining
work with existing owners. Preserved built C01/C03A/C17A; withdrew proposed C03B
extra-event readiness pending necessity proof. No runtime change in this audit.

## 2026-10-07 — offline Decisions selector foundation

- Added unmounted, replaceable finite-choice mapper/parser and no-op with immutable
  candidate identity, bounded metadata and cancel/deadline/stale-result guards.
- C17A/r1 internally verified:107 selector tests/181 focused regressions pass;
  broader suite retains four existing failures. No SDK upgrade or provider call.
- Classification does not authorize tools or activate learned workflows.

## 2026-10-07 — conversation persistence foundation

- Added unmounted scoped conversation/segment and finalized-text storage with
  atomic versions, exact-content retry and current session authority.
- Added account-erasure integration for shared-workspace conversations.
- C03A/r1 internally verified:51 real isolated-Postgres tests,74 focused units/
  regressions and14 existing identity integrations pass. No chat UI/model activation.

## 2026-10-07 — memory-search foundation

- Implemented replaceable read-only search backend with legacy default parity and
  optional interactive vector-repair policy; existing caller interfaces unchanged.
- C01/r3 verified by internal review and 41 focused tests. Broader suite has four
  unrelated failures reproduced with baseline service; no whole-feature completion.
- No database, live drafts, Decisions API, SDK upgrade or chat UI changes in this slice.

## 2026-10-07 — planning only

- Reviewed build entry: separate scoped conversation identity/final-turn storage
  and offline Decisions mapping contracts remove circular/live-provider prerequisites.
  Exact erasure integration accounts for tombstoned users. C01/r3, C03A/r1 and
  C17A/r1 ready as bounded slices; no implementation or production activation.

- Completed Phase02 internal self-review and source corrections: unwired/missed
  tool observations, SDK mismatch, atomic capture, semantic capability gaps and
  scoped database relationships. Defined evidence versus disposable decision storage.
- Reviewed C01/r2 bounded foundation; drafted dependency-blocked C03/C17 contracts.
  No whole-feature READY claim.20 existing focused tests passed; no runtime changes.

- Executed Phase01 prompt directly: planned optional dynamic-choice selector,
  contextual draft scheduling, independent evidence axes, qualified historical
  audit and inactive learning; updated owned plans and froze candidate for review.

- Grounded documented Decisions API availability without adopting GPT-Live.
- Recorded finite-choice mapping, speculative/final/tool/hindsight evidence,
  historical coverage limits, inactive learning proposals and removable-module
  requirements in the new grounding amendment.
- Marked affected plans/review/contracts for revalidation; preserved historical
  manifests and existing branch/working changes. No feature implementation.

Notable release changes are recorded here. The project is currently preparing
its first public development release.

## Unreleased

- Grounding r5 records provisional owner permission to process partial drafts
  with configured providers before Send for testing; reassess after evidence.

- Grounding r4 records owner confirmation that Vault is the Link Personal/Business
  Agent package; draft-provider choice subsequently recorded in r5.

- 2026-10-04 grounding r3: added live draft edit/delete/Send handling, proposed
  code/model memory-selection ownership and optional reranking, plus latency,
  discarded-work, cost and quality evaluation cases. Documentation only;
  recommendations remain conditional and no performance gain is asserted.

- 2026-10-04: recorded modular live-input memory, procedural decision learning,
  and Vault chat grounding plus code review. Identified existing real-vector
  storage versus missing HNSW query/index and preserved theoretical Decisions
  API, privacy and lifecycle boundaries. Documentation only; no feature shipped.
- 2026-10-04 grounding r2: verified Presentation and existing Vault text SDK
  reasoning-summary capture paths; added session-review evidence requirements,
  text-model wiring and dynamic parallel draft/context acceptance cases. Voice
  summary availability remains conditional. No runtime implementation changed.

- Connections AI & Voice lists OpenAI Luna (`gpt-5.6-luna`) as a Background text model selection. Default remains `gpt-5.6-sol`. Provider catalog `textModels` owns the list the same way `voiceModels` owns Voice models.
- Hermes and OpenClaw memory pairing rewrite the host Vault CA from `GET /vault-local-ca.crt` so a container recreate does not leave a stale dashboard certificate. Pairing POSTs and memory HTTPS stay verified.
- Connections AI & Voice can connect xAI/Grok with the same device-code OAuth Hermes and OpenClaw use (`auth.x.ai`, SuperGrok or X Premium+). The selected xAI OAuth token is what the Background Agent uses; Voice over that token is not required.
- Docker Link Companion uses the packaged host-gateway to reach the host connector. Outbound Agent Network still uses Link `https://…:8443` URLs; companion does not ask the operator to configure a proxy.
- Link collab clients that POST `/a2a/v1` are accepted on the Background Card (same JSON-RPC as `/`).
- The Background Agent Card on `:8768` answers `GET /.well-known/agent-card.json` without a bearer so Link can discover it. JSON-RPC still requires `Authorization: Bearer`.
- After Link Companion is paired, Link Agent Network apply fills External agents with Link peers (`https://…:8443` Card/RPC and directional tokens). Callers presenting a Link inbound grant bearer are accepted on the Background Card. Unpair removes those Link-managed rows. Inbound from host Hermes/OpenClaw uses published `8768`.
- External agents includes **Set up Link Companion**: confirm a pairing code from `sudo resono-link-connector companion setup vault`. Vault stores only the pairing receipt, not the host connector token. Disconnect there (or disconnect Vault in Link) ends the pairing.
- Voice starts Background Agent goals through Goal Intake (`voice_mode_switch` then `goal_start`). The Background Agent page uses the R1 delegated-work layout (run logs, progress rail, reasoning logs) and does not submit work. Empty requested tool names freeze every Background-visible tool (including MCP grants restored at run start). Background uses the same selected-provider credential and background model as Voice.

- Docker Vault publishes host loopback `8768` (override `VAULT_A2A_PORT`) and binds inbound A2A on all container interfaces so Link and other host peers can reach the Agent Card. Standalone still binds `127.0.0.1`. The Agent2Agent option remains the on/off switch for accepting work.
- Collab uses the Hermes A2A coordinator automatically whenever Agent2Agent is on. There is no separate Collab switch. Turning Agent2Agent off stops collab tools.
- Agent2Agent inbound requires `Authorization: Bearer` (not a dashboard cookie, Basic, or this Vault's outbound connection token). The Agent Card advertises Bearer; outbound connect refuses reusing the inbound secret.

- Workspace page uses the signed-in name as `{name}'s Workspace`, drops the private-files subtitle, keeps the folder title above `Up one folder`, and adds Close on file preview.
- Connections AI & Voice no longer shows Use API key or Disconnect provider; Connect OAuth and Disconnect OAuth are mutually exclusive.
- Settings Linked folders heading is larger, centered, and spaced below the separator.
- Platform Guide matches current Workspace chrome, Connections AI & Voice buttons, and Library page headings.

- Added public installation, contribution, security, conduct, and licensing
  documentation.
- Hardened remote MCP destinations against private-network and DNS-rebinding
  targets while preserving explicit loopback integrations.
- Added non-executing Plugin package risk review to extension preflight.
- Added transport-aware `Secure` session cookies while preserving the
  loopback-only HTTP compatibility bridge.

- Live memory change: created `feature/live-memory-decisions`; saved research, current-memory/VoiceMem overlap review and separate Phase 01 working drafts. Required actual HNSW retrieval and complete-session review; preserved memory agent/store/embeddings and live-only switch semantics. Documentation only; no implementation.

### 2026-10-05 — explicit modular live-memory planning candidate

- Documented module ownership and narrow existing-code adapters, additive pgvector/HNSW query cutover and scoped embedding maintenance.
- Added complete-session coverage/retry/publication schema, OpenAI live transcription/OAuth conditional integration, conversation/evidence and procedural schema proposals.
- Froze Phase01 conditional draft with SHA-256 identities; no runtime, dependency, migration or deployment changes.

### 2026-10-05 — separate Chat planning expansion

- Preserve current Voice page and persistent mode; plan independent Chat with
  explicit interaction-quality tests and shared live-memory pipeline.
- Research/document prior-session continuation and per-contribution ingestion
  coverage, image/document capture/import, and existing authorized write tools.
- Supersede affected candidate; documentation only.

### 2026-10-05 — Phase02 codebase review and first build contract

- Corrected preference HTTP method, streaming/permissions seams, typed metadata
  prerequisites, erasure/worker ownership and readiness claims in modular plans.
- Recorded37 requirement traces and scoped same-context review; created/reviewed
  READY LMD-C01 search-boundary foundation contract and later contract register.
- Saved exact candidate/source identities and restart handoff; documentation only.
# 2026-10-07 — C03B bounded evidence planning review

- Reviewed atomic submitted-turn evidence contract against verified conversation
  storage; exact paths, schema, retries, authorization and database checks frozen.
- Updated governing plans and register; full Voice/tool/reasoning capture remains
  follow-on C03C, not inferred complete from user events. No runtime edits.
# 2026-10-07 — duplication validation hold

- Withdrew C03B READY after code audit identified unproven need for redundant
  final-user event metadata; no implementation of that ledger occurred.
- Recorded repeated authorization SQL in new conversation repository and existing
  Voice repository. Halted implementation pending source-to-plan reconciliation.
