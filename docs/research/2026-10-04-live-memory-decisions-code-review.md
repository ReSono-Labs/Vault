# Live memory, learned decisions, and Vault chat — code review

Date: 2026-10-04
Revision: `LMD-REVIEW-2026-10-04-r2`
Baseline: `ea39a6f9da89a2999c4f7e14f686428d2088f480` (initial worktree clean).
Type: internal self-review; source inspection and bounded baseline checks.
Scope: the proposed input/retrieval/routing/learning chain and its existing Vault owners. This is not a security audit of every Vault subsystem or live deployment verification.

This file records evidence, not implementation authority. Requirements and
material decisions live in [the change grounding](../planning/2026-10-04-live-memory-decisions-grounding.md).
The original product boundary remains [GROUNDING.md](../../GROUNDING.md).

## Overall finding

The proposal fits several existing service boundaries, but is not already
implemented. Vault has canonical scoped memory, real provider embeddings,
transcripts, model-backed memory review, tool authorization, and two fixed
system agents. It lacks revisioned speculative input, indexed semantic runtime
retrieval, procedural decision storage/learning, and a general conversation
composer. Reuse the existing authorities; do not fork them into a parallel
agent runtime.

## Observed ownership and gaps

| Concern | Existing owner / inspected source | Observation | Gap relative to owner request |
|---|---|---|---|
| Composition | `app/vault_runtime/composition.py` | Wires memory, reviewer, embeddings, providers, fixed agents, tools, and extensions | No live preparation or learned-decision composition |
| Memory contracts | `memory/contracts.py`, `memory/schema.py` | R1 taxonomy, private/workspace visibility, evidence, versions, lifecycle | Memory type `decision` is recalled knowledge; it is not an executable decision rule |
| Memory authority | `memory/repository.py::_require_membership`, `_scope_sql` | Checks active user/workspace membership; queries constrain workspace and private/shared visibility | New indexes/caches must preserve these checks; filtering after retrieval cannot replace authorization |
| Embeddings | `memory/openai_embeddings.py` | Real remote OpenAI embeddings, default 1536 dimensions; scoped credential factory; validation; no fabricated vectors | Locally stored vectors do not mean locally generated embeddings; draft disclosure and cost need resolution |
| Vector storage | `memory/schema.py` | `CREATE EXTENSION vector`; both `vector_json` and real `embedding vector`; legacy upgrade | No HNSW/IVFFlat index in inspected application schemas; unconstrained vector dimension needs index-compatible migration design |
| Semantic search | `memory/retrieval.py`, `repository.py::embeddings_for` | Reads scoped vectors from JSONB and computes cosine in Python; per-hit record lookup | No SQL nearest-neighbor operation; current code would not use a newly added HNSW index |
| Search service | `memory/service.py::search`, `ensure_vectors` | Repairs up to 256 missing vectors before factory-backed lookup; truthful lexical fallback | Repeating repair on every draft revision risks unbounded latency/provider work relative to interactive demand |
| Voice startup context | `voice/context.py::VoiceContextBuilder.build` | Eight profile memories and previous summary injected at session creation | No per-utterance preparation/context handoff |
| Realtime startup | `voice/provider.py`, `voice/openai_realtime.py` | Provider-neutral request; OpenAI payload transcription and server VAD; coordinator sets automatic response creation | Current turn-taking can start response before final transcript/preparation validation |
| Browser event handling | `frontend/src/browser-voice/BrowserVoiceApp.tsx::receiveRealtimeEvent` | Final user transcripts; assistant transcript deltas; status text | No user-partial revision tracking, debounce, cancellation, or prepared-state cache |
| Other voice providers | `BrowserVoiceApp.tsx::receiveProviderWebSocketEvent`, `captureNormalizedTranscript` | Gemini text events normalized into transcript entries; xAI uses Realtime-style handler | Shared revision contract and partial/final semantics are not established across providers |
| Home presentation | `BrowserVoiceApp.tsx` home / `HomeVoice` | Large microphone button and current status/transcript display | No general text composer or durable conversation message list |
| Existing text UI | `DocumentsPanel.tsx::HelpAssistantPanel`, `help_assistant.py` | Bounded support chat, textarea, messages; documentation/source retrieval | Useful presentation evidence, but support service is not the general Voice/Background tool runtime |
| HTTP boundary | `local_api/app.py`, frontend `localApi.ts` | Authenticated Voice start/events/tools/close/finalize routes | No general chat-turn or draft-preparation contract in inspected routes |
| Tool identity/dispatch | `tools/definitions.py`, `tools/catalog.py` | `tool_id`, name, effect, fixed audiences, scopes, availability; dynamic sources replace/remove | No demonstrated semantic capability-to-provider resolution for interchangeable accounting implementations |
| Execution authority | `voice/tools.py` | Grants, scoped calls, invocation claims, read failure vs write/delete `effect_unknown` | Learned routing must enter this authority, not invoke handlers directly |
| Session evidence | `voice/events.py`, `voice/evidence.py`, `memory/evidence.py` | Final transcript and bounded/redacted tool evidence | No durable record of matched rule, selected candidates, rule/generation version, corrections, or final successful route |
| Memory learning | `memory/voice_learning.py`, `pipeline.py`, `openai_reviewer.py` | Structured, cited model review; reconciliation; summary; embedding; fingerprint ingestion | No procedural decision reviewer/compiler/publication boundary |
| Close/finalize | `local_api/app.py` close/finalize; `BrowserVoiceApp.tsx::closeVoice` | Browser waits for pending transcript writes; API close directly calls memory finalization | Post-session review exists, but this path is synchronous; durable async retry/recovery cannot be assumed |
| Link | `link_companion/`, `agent_network/`, Compose, existing Link integration records | Existing optional routing/A2A integration; Background handles inbound work | Does not establish that a separately installed Link Personal/Business intelligence runtime exists in this repository |

Paths in the table are relative to `app/vault_runtime/` unless explicitly
prefixed. Existing module ownership is evidence for later planning, not a
prescription for new files.

## Material findings for the later plan

### 1. Real vector storage is present; indexed retrieval is absent

`MemoryRetriever.retrieve` calls `embeddings_for`, iterates vectors, calculates
Python cosine, and fetches each matching memory. The schema contains a real
vector column but retrieval does not order by its distance operator. The
current unit retrieval test tests cosine arithmetic only. This is neither a
fake embedding system nor the requested database ANN runtime.

A later change must prove both an index and an index-compatible repository
query. Preserve lexical/exact behavior and existing reconciliation. An index
alone would leave current performance unchanged. Query-plan and recall
evidence must use a representative authorized dataset; a tiny table may
legitimately cause PostgreSQL to choose an exact scan.

### 2. Authorization filters must precede exposure

The owner's “vector first, structured validation second” describes candidate
selection, not permission to fetch globally and filter in Python. User,
workspace, visibility, embedding compatibility, and active generation need
to constrain eligible database results. Runtime checks then validate tool
availability, required slots, current permissions, and rule status/version.
The cache cannot preserve authority after membership/grant revocation.

ANN results may contain too few eligible rules or too many examples of one
rule. The later plan needs bounded recovery and evidence for these cases;
silently accepting the first nearest example is not sufficient.

### 3. Speculative preparation is not speculative execution

Input revisions can be wrong, deleted, abandoned, or corrected by ASR. Even a
read tool may contact an external system. No existing inspected path makes
tool execution safe merely because a likely intent was recognized.
Preparation must be distinguished from invocation, durable learning,
delegation, and external communication. Permission and final-input validation
remain independent of rule confidence.

### 4. Turn detection is a real integration boundary

The current coordinator sets `turn_detection_create_response=True`. The UI
marks speech stop as responding and accepts provider-created responses.
Changing retrieval does not by itself make “finalize, validate, then respond”
true. Partial transcription availability, corrections, final-event ordering,
context injection, interruption, and response gating need provider-specific
documentation and tests in planning. Do not assume one transcript event is
the provider model's exact interpretation of the audio.

The proposal's two audio paths are conceptual. This review does not prove a
second transcription service is necessary, free, or available. Existing
provider transcription should first be assessed as a reuse candidate.

### 5. Cloud draft processing is a separate privacy decision

The existing embedder sends text to a remote provider and allows a 30-second
network timeout. Running it before Send would transmit unsent and subsequently
deleted text. The phrase “free locally installed agent” establishes neither
free provider usage nor an offline embedding/routing/review model.

No latency win has been measured. Provider RTT, debounce, cancellation,
backfill, multiple simultaneous users, and review contention all affect the
claim. Record total cost and final-to-response latency as well as database
query latency; select budgets only with evidence and owner constraints.

### 6. Learned behavior must remain rebuildable and constrained

The current memory type `decision` can record “we selected outbound
connectors.” It must retain its meaning. A procedural rule selecting a route
needs separate authority and lifecycle. Model output and retrieved examples
are untrusted proposals, not new grants or executable instructions.

The sample `decision_key UNIQUE` is not a production schema: uniqueness must
be evaluated against scope/generation/version. Definitions, examples, edges,
versions, embedding identity, and source evidence need coherent references.
An example cannot silently retrieve a superseded definition.

Generation rebuild must preserve retained session history, canonical memory,
tools, and grants. It cannot undo completed external actions. It also must
not reconstruct information the user deleted merely because old evidence
remains. Retention and deletion semantics are unresolved.

### 7. Confidence and similarity are different signals

Cosine similarity is candidate relevance, not calibrated action confidence.
“Observed 14 / successful 13” is useful evidence, not proof a rule applies to
this utterance. One payment-status success does not authorize combining
invoice lookup, outstanding balance, and payment history into one action.
Preserve distinct sub-intents/required identifiers, ambiguity handling,
failures, user corrections, and policy at execution time.

### 8. Modularity requires removal behavior

Adding modules to the tree is not proof of isolation. Later acceptance must
show that removing live retrieval, learned routing, its selector, or decision
learning leaves a coherent authorized final-input path. Removing decision
learning must not remove memory learning. Replacing a provider must not alter
grants. Component timeouts cannot stall the conversation indefinitely.

Current product grounding makes canonical memory learning mandatory. The
owner's experimental removability requirement needs explicit reconciliation
if extended to disabling that existing core behavior in a supported release.
The latest request authorizes evaluating replacement boundaries; it does not
require physically deleting existing services or weakening authorization.

### 9. Existing text support is reusable evidence, not a chat backend

The Help panel already demonstrates Browser Voice message/composer patterns.
Its backend reads project docs/source and has a support-only purpose. Wiring
general personal/business requests into it would mix responsibilities.
The requested Home change is an explicit, narrow visual-lock exception:
conversation window, text input, voice control on its right. It does not
authorize a new design system or another system-agent identity.

## External evidence checked on 2026-10-04

| Source | Establishes | Does not establish |
|---|---|---|
| [pgvector official documentation](https://github.com/pgvector/pgvector#hnsw) | Real ANN indexes; cosine operator class; dimensional limits and index/query constraints | Vault has HNSW, the illustrative SQL is deployable, or local latency meets a target |
| [pgvector filtering](https://github.com/pgvector/pgvector#filtering) | ANN filtering can underfill results; iterative scans require compatible extension version | Database authorization policy or a chosen partition layout for Vault |
| [PostgreSQL JSONB](https://www.postgresql.org/docs/current/datatype-json.html#JSON-INDEXING) | JSONB supports indexed containment/key operations | Arbitrary conditions are safe executable policy |
| [PostgreSQL index types](https://www.postgresql.org/docs/current/indexes-types.html) | B-tree/GIN serve different query shapes | Every JSONB field needs an index |

Current pgvector docs describe HNSW `vector` indexing up to 2000 dimensions,
and dimension-compatible casts/partial indexes for mixed storage. A fixed
1536-dimensional embedding fits that limit; the existing unbounded column
still requires an explicit index design. Filtering/iterative behavior must
be checked against the actually installed extension, not a floating image tag.
Compose currently specifies `pgvector/pgvector:pg16`; no installed extension
version or production query plan was inspected.

No Decisions API endpoint, schema, availability, pricing, confidence contract,
or latency is established by this review. Its unavailability is recorded as
the owner's stated boundary. Provider integration waits for published
documentation; this review does not fabricate a substitute API.

## Donor/provenance readiness

Reuse candidates already in Vault: canonical memory, identity, tool catalog,
grants/invocation recovery, provider credential resolution, transcript learning,
Browser Voice tokens/components, and the Documents Help presentation.

Known original donor locations from the existing borrowing matrix:

- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/frontend/src/browser-voice/`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/pipeline.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/retrieval.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/agents/memory_reviewer.py`

Path availability was checked; no new donor subset was copied or declared
build-ready. Live revisions, procedural learning, capability resolution and
general chat are gaps relative to the inspected Vault implementation. They
remain potential `NEW` work pending targeted donor search and Phase 01/02,
not a claim that no reusable code exists elsewhere.

Link was inspected only for working-tree/integration orientation. Its
pre-existing untracked files were left untouched. No Link or drift-protection
files were edited. Separate Link product identity and installation ownership
remain an open dependent question in the grounding.

## Verification evidence and limits

Executed in the existing Vault environment:

```text
.venv/bin/python -m pytest -q tests/unit/test_memory_retrieval.py tests/unit/test_memory_contracts.py tests/unit/test_openai_memory_reviewer.py tests/unit/test_memory_evidence.py tests/unit/test_tool_catalog.py tests/unit/test_scoped_tool_catalog.py tests/unit/test_system_agent_inventory.py tests/unit/test_voice_schema.py
25 passed in 1.26s

cd frontend
npm test -- src/browser-voice/BrowserVoiceApp.test.tsx src/browser-voice/localApi.test.ts
2 files passed; 11 tests passed
```

These baseline tests do not prove live transcription, new chat, ANN index use,
procedural learning, production isolation, provider credentials, or latency.
No integration database, migration, deployment, microphone, provider call, or
hardware operation was run. Existing PostgreSQL tests include hybrid/fallback
retrieval and fingerprint finalization, but were inspected rather than run.

Recovery concern observed in `pipeline.py`: review happens before ingestion
claim; claim uses insert-on-conflict-do-nothing; writes span repository calls.
Concurrent requests can therefore perform duplicate reviews, and post-claim
failure recovery/partial writes need investigation. This is a grounded concern,
not a newly reproduced production failure or authorization to fix it here.

Grounding self-review checked the original request for omitted requirements,
invented API promises, expanded specialist-agent scope, new tool families,
unmeasured performance claims, and duplicate storage/authority. Findings above
are preserved for planning rather than silently resolved into a design.

## Reasoning capture and dynamic chat — owner clarification addendum

Inspected Presentation source exactly as requested:
`/home/christian/Documents/Projects/ReSono-Labs-Presentation/app/sdk_agent_runtime.py`.
Donor HEAD: `4a1bf3941d41f53c3b7e020d400ffe4b54f5d5a8`; inspected file SHA-256:
`46f1ef41b6ce5094ce7dc8a5a9622b5a2e2119651e0507aad1c958faa2ce1ee9`.
The donor file and four builder/reviewer configuration files were already
modified by the owner. This review describes the working file, not clean HEAD.
No Presentation file was changed or executed.

### Established source path

Presentation `_run_config` uses the Responses-backed SDK provider and requests
`reasoning={effort: ..., summary: "auto"}` for models recognized by
`is_agency_model`. `_sdk_items_json` serializes `result.new_items`;
`_reasoning_summaries` finds `raw_item.type == "reasoning"`, extracts
`summary[].text`, and limits each text to 2200 characters. Builder/reviewer
rounds retain these in `SdkAgentTrace.reasoning_summaries`, evidence callbacks
and `sdk_agent_report.json`. Collection occurs after each synchronous run,
not as incremental draft processing. `_safe_json` also bounds serialized
items, so this is useful provenance, not proof of lossless capture.

It requests `reasoning.encrypted_content` separately. Opaque continuation
state is not summary text or evidence a reviewer can read. Full SDK raw-item
dumping and the builder/reviewer execution sequence are not automatically
appropriate for Vault. Only identity-neutral, bounded extraction is a reuse
candidate; the existing fixed-agent inventory remains intact.

Vault already has a closer reuse owner:

- `app/vault_runtime/background_agent/sdk_runner.py::run_agent_turn` requests
  `Reasoning(..., summary="auto")` when reasoning effort is not `none`.
- Its SDK `ObservationHooks.on_llm_end` calls `_observe`, which extracts
  actual response reasoning-summary text, bounds each to 16 KiB, and emits
  `AgentTurnObservation` to the caller.
- `background_agent/openai_executor.py` passes an observation sink and calls
  `progress.reasoning` for returned summaries.
- `background_agent/service.py::RunProgressRecorder.reasoning` persists scoped
  `reasoning_summary` activity via the Background repository; the progress
  projection exposes it to the existing Background UI.

This proves an existing text observation/persistence path. It does not prove
general chat session wiring, complete turn/tool correlation, total session
evidence limits, provider-wide compatibility, or post-session decision learning.
The structured memory reviewer calls the SDK runner without a session
observation sink; a reviewer's own reasoning is different from captured
conversation reasoning and must remain separately attributed.

### Official provider boundary checked 2026-10-04

[Official OpenAI reasoning documentation](https://developers.openai.com/api/docs/guides/reasoning#reasoning-summaries)
confirms opt-in summaries are in the reasoning output item's `summary` array;
supported summary settings depend on the model. These are summaries, not raw
internal reasoning. That supports the inspected text extraction approach.

[Realtime documentation](https://developers.openai.com/api/docs/guides/realtime)
and inspected Vault voice adapters do not establish identical summary capture
for every configured voice transport/model. Absence from this inspection is
not a claim that no voice product supports it. Provider-specific verification
is still required. Record availability for each turn/session rather than
inventing a missing provider summary. A separate model's retrospective
explanation must be labeled as such if later authorized; it cannot replace
original evidence under the same name.

### Required reviewer evidence

The owner explicitly wants reasoning summaries to help add/update learned
decisions. Retain their session/turn/model attribution and order, tied to the
final request, actual selected rule, relevant memory references, tool calls,
results, errors and user corrections. A summary describing an intended route
is evidence of intent; observed execution establishes what worked. Empty,
unsupported, interrupted, duplicate, or truncated summary events need truthful
handling and existing scoping/redaction. No summary can grant permissions.

### Draft/context concurrency acceptance boundaries

The latest clarification makes concurrent interpretation and contextual memory
explicit. It requires a text model connected to the real conversation/tool
runtime, and interpretation that can change when retrieved memory arrives.
This is distinct from running a new final conversational response on every
keystroke. Scheduler/model invocation details remain planning work.

Required counterexamples for the later plan:

1. User types a simple weather question, then replaces it with “what did we
   decide about the customer meeting?” The old simple route cannot suppress
   new relevant memory retrieval. Weather/reminder requests may themselves
   require saved location/person/timezone context; examples are not hardcoded
   no-memory categories.
2. Draft revision changes while both route and memory requests are running.
   Each branch's late result is rejected independently; route from one revision
   cannot be paired with memory from another.
3. User deletes all text or changes an entity before debounce fires. Invalidate
   previous preparation immediately; late work cannot repopulate the cleared
   draft. Debounce governs new work, not continued validity of old work.
4. A memory hit disambiguates “that project” after an initial route proposal.
   Interpretation may be reconsidered only against the still-current draft and
   context; contextual enrichment needs bounded work and attributable state.
5. Send arrives with preparation incomplete, or typing continues during a
   sent response. Finalize a specific sent turn; later draft work must not alter
   it. Cold retrieval/model fallback stays available with current grants.

Summary extraction/reasoning evidence, draft scheduling, memory retrieval,
route selection, final text execution and post-session review must remain
distinct duties. No API/schema/module scaffold was created by this addendum.

Addendum verification: existing `_observe` exercised with mocked SDK output;
summary extraction, non-reasoning exclusion and absent-summary behavior passed.
`.venv/bin/python -m pytest -q tests/unit/test_background_openai_executor.py tests/unit/test_background_progress.py`
passed (2 tests, 2.84s). These checks do not exercise a live provider or prove
conversation-session wiring. Presentation worktree status was unchanged after
inspection. Official OpenAI documentation informed the summary/voice capability
boundary; no model/provider migration or API call was performed.
