# Evolving-input memory retrieval — research

Date: 2026-10-05. Revision: LMD-RESEARCH-r1. Evidence, not design authority.
Inputs: grounding r7 and owner correction selecting OpenAI live transcription.
Research completed before the feature-plan candidate was written. No candidate
installed or executed; source inspection is not runtime proof.

## Closest match and adoption screen

**VoiceMem is the closest inspected match for live memory retrieval.** It has
an external partial-text input, speculative searching, and replaceable factual
retrieval components. Recommendation: investigate a bounded factual-retrieval
subset against Vault's canonical store, not adopt its full memory/audio stack.
Mem0 provides a larger comparison baseline. No candidate currently proves all
of Vault's revision, authorization, quality and speed requirements.

GitHub API observations on this date (counts change):

| Repository | Stars | Reported license | Inspected commit |
|---|---:|---|---|
| [xzf-thu/VoiceMem](https://github.com/xzf-thu/VoiceMem) | 2,351 | Apache-2.0 | `6cacb3c1e7fca2679f3bf95451f6b480efd9a783` |
| [rohansx/primd](https://github.com/rohansx/primd) | 3 | Not established | `83d561de3bea8cb4563c7621e68ef420a3eb4751` |
| [usemoss/moss](https://github.com/usemoss/moss) | 789 | BSD-2-Clause | `a3ae0c7dcbe3889cce6039708c47219939a6c599` |
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | 66,613 | Apache-2.0 | `c93420c49a6b14c3d446bdb156d96811908fd90a` |

License metadata is screening only; any copying needs file-level license and
notice verification in its contract. Source was fetched read-only to `/tmp`.
No external repository code was imported into Vault.

## VoiceMem: behavior checked in actual source

[stream.py at the inspected commit](https://github.com/xzf-thu/VoiceMem/blob/6cacb3c1e7fca2679f3bf95451f6b480efd9a783/voicemem/stream.py)
exposes `feed_partial(text, ended)`, `_kick`, `_speculate`, and `_confirm`.
Its partial interface bypasses built-in ASR. Search runs in a thread; changed
text cancels the pending task and starts another. Factual retrieval separates
classification and candidate narrowing from ranking. Its local classifier uses
E5; repository v2 combines entity/slot candidates and widens some temporal
queries. This is relevant reuse evidence, not a PostgreSQL adapter or a proven
Vault deployment.

Four concrete gaps prohibit wholesale reuse:

1. `_confirm` can attach the final text to results computed for earlier text.
   Last-word negation or an identifier change can invalidate those memories.
2. `feed_partial` ignores empty text, so deletion needs an explicit adapter
   invalidation path. `_ready_memory` can retain older results while newer work
   runs; display/preparation must never imply that older data is valid.
3. Cancelling an asyncio task awaiting threaded work does not establish that
   the underlying search/provider work stops. A worker limit and revision
   rejection are required independently of task cancellation.
4. Character-count triggering is not a bounded semantic debounce strategy.
   Inspected streaming code does not establish workspace membership checks,
   grant epochs, durable review recovery or model-wide intent handling.

Other inspected files at the same commit: `core.py`, `config.py`,
`memory_api.py`, `leftbrain/brain.py`, `leftbrain/memory_repository.py`,
`leftbrain/memory_repository_v2.py`,
`leftbrain/cognitive_graph/local_query_classifier.py`,
`tests/test_session_context.py`, and `pyproject.toml`. The package carries Mem0
and local-model dependencies; its stores/taxonomy cannot replace mandatory R1
memory behavior. No emotion, persona, voiceprint, new ASR or reply-model scope
is authorized by investigating its factual subset.

[VoiceMem's paper](https://arxiv.org/html/2608.26005v1) describes staged matching,
embedding and retrieval overlapped with turn detection. Its reported 134 ms
retrieval result is an author measurement, not our end-to-end result. Its
benchmark and local embedding configuration do not establish similar quality
or latency with Vault's scoped PostgreSQL and remote embedding provider.

## Other memory/retrieval candidates

| Candidate | What was established | Why it is not selected wholesale |
|---|---|---|
| [Mem0 search](https://github.com/mem0ai/mem0/blob/c93420c49a6b14c3d446bdb156d96811908fd90a/mem0/memory/main.py) | Async search and scoped query retrieval; inspected implementation; documentation describes semantic/keyword/entity signals | Query search is not evolving-draft cancellation/finalization; replacing canonical learning would violate scope. Managed benchmarks do not prove OSS results |
| [Primd query context](https://github.com/rohansx/primd/blob/83d561de3bea8cb4563c7621e68ef420a3eb4751/primd-core/src/query_context.rs) | Partial observation, speculative cache and final signature handling | Only 3 stars; final reuse permits a Hamming-distance threshold; README disclaims high-recall focus. Not a fit for near-perfect retrieval without stronger proof |
| [Moss](https://github.com/usemoss/moss) | Search runtime and voice integration; inspected Pipecat retrieval service loads an index and delegates to a processor | Fast search claims do not establish partial-query revision semantics. Different index/cloud setup conflicts with selected PostgreSQL direction if adopted wholesale |
| [Graphiti](https://github.com/getzep/graphiti) | Reputable temporal/relationship retrieval with provenance; README and official overview inspected | Real-time ingestion is different from evolving-input retrieval; requires graph infrastructure. No inspected partial-draft scheduler; not chosen as a new datastore |

Mem0/Graphiti are useful quality references; VoiceMem is the closest live-input
reference. Star counts do not outweigh functional counterexamples. Further
subset selection requires an isolated comparative experiment and a contract,
not a guessed claim that any one system is production-ready.

## Selected voice source, not a voice-runtime survey

[OpenAI live transcription](https://developers.openai.com/api/docs/guides/realtime-transcription)
documents `gpt-live-transcribe` text during incoming speech, item-correlated
deltas and committed finals. Its transcription session needs application turn
control; server/semantic VAD are unsupported for this model. Delay settings
trade early text against quality. Events need item correlation because finals
can arrive out of order. There are no word-confidence values to use as a
stability guarantee. Verify account/model access before a paid experiment.

OpenAI transcription remains the owner's choice. VoiceMem receives accumulated
text through an adapter; its ASR is excluded. Existing Vault currently uses
`gpt-4o-mini-transcribe`, automatic response creation and final-only capture:
those existing settings do not establish the selected live path. Integrating
live transcription does not require changing the conversation model. A second
concurrent audio stream, if necessary, needs explicit latency/cost evidence.

Early LiveKit/Pipecat investigation was superseded by the owner's correction;
neither becomes an implementation dependency. Their cancellation patterns
are auxiliary references only, not the answer to memory-system selection.

## Feature-by-feature research disposition

| Feature | Research / inspected reuse | Remaining proof before build readiness |
|---|---|---|
| Live memory / intent during voice and typing | VoiceMem factual subset, Mem0, Primd; above | Comparative quality, correct revision/final reuse, worker bounds; intent ambiguity is not solved by slot matching |
| HNSW/hybrid lookup | [pgvector](https://github.com/pgvector/pgvector), [PostgreSQL full text](https://www.postgresql.org/docs/current/textsearch.html); local retrieval/service/schema | Extension version/dimensions, scoped recall, SQL plan, lexical ranking, index migration |
| Chat/composer | Existing Documents Help UI, Home and localApi inspected | General scoped chat backend; no additional UI framework needed |
| Live switch/settings | Existing local identity and extension settings boundaries inspected | Owner confirmed partial-only Off; dedicated preference owner/default still proposed |
| Session reasoning evidence | October 4 source review, [OpenAI reasoning docs](https://developers.openai.com/api/docs/guides/reasoning#reasoning-summaries) | Turn correlation, missing/truncated states; no blanket voice summary guarantee |
| Decision learning/generations | Existing R1 memory pipeline and [LangMem concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/) distinguish hot-path retrieval from background learning | Durable retry, promotion and retention policies; do not import another memory authority |
| Finite intent selector | [Aurelio hybrid router](https://docs.aurelio.ai/docs/semantic-router/client-reference/routers/hybrid) documents dense/sparse routing | Not proof of contextual intent or future Decisions API compatibility; optional adapter only |
| Capability interchange and caches | Existing tools/catalog, grants, evidence | Stable semantic references, current grant/tool/version validation |

## Quality and speed together

All candidates need the same authorized final queries and memory corpus. Test
partial-prefix ambiguity, last-word reversal, name corrections, temporal
supersession, missing/contradictory facts, multi-memory synthesis, language
changes, no-match and private/workspace isolation. Query streams must include
real timestamps and edits, not only complete questions.

Measure relevant evidence coverage, precision, unsupported-answer rate and
abstention alongside end-of-speech/Send to first useful answer/audio. Include
embedding time, final validation, playback, discarded work and contention.
Compare live-off final retrieval, live-on, and full authorized retrieval as a
quality oracle. Do not lengthen endpointing to manufacture hidden retrieval.
Numerical acceptance limits remain owner decisions after evidence.

## Local baseline checked

2026-10-05: six targeted backend files (memory retrieval/contracts/evidence,
scoped catalog, agent inventory, voice schema): **19 passed in 0.25 s**.
Frontend BrowserVoiceApp/localApi: **11 passed**, two files, 3.89 s. These are
existing regression checks, not candidate evaluation or live provider proof.
One raw source fetch batch had connection resets; selected VoiceMem files were
retrieved via GitHub contents API. No donor code was executed, no database or
provider experiment was run. Research is sufficient for a conditional plan;
it does not settle backend reuse or production numerical acceptance.

Current source inventory, owner role correction, benchmark-image assessment
and required full-session/HNSW changes are in the
[implementation review](2026-10-05-current-memory-implementation-review.md).
This initial research does not select a full VoiceMem store or analysis system.
