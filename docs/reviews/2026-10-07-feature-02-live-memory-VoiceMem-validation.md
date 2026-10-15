# Feature 02 — live revisions, preference and VoiceMem validation

Read COMPLETE live-memory-runtime-plan r2 and evaluation-plan r2, applicable
grounding R02–05/R27–33 and pinned donor cut-point research. Internal code audit
2026-10-07; no runtime/provider/DB change. Scope remains existing plans, not a new
choice to discard VoiceMem. This replaces name-search-only inference.

## Verdict

VoiceMem retrieval-only integration/evaluation and the shared live revision
controller are NOT IMPLEMENTED in current code. Existing final transcript capture,
Help draft state and offline selector validity guards ARE IMPLEMENTED; none is
the documented revision controller. Preference is also not implemented.

Actual input traces: Help textarea onChange only setDraft; ask on form submit calls
localApi.askHelp. No preparation call on edit/delete. OpenAI BrowserVoiceApp user
capture branch recognizes transcription completed events; assistant transcript
deltas update display. Neither branch calls live search/controller. Existing
MemoryService search is request-driven. C17A selector accepts a caller-provided
is_current callback; no production controller supplies it or schedules it.

| Plan obligation | Code/wiring/evidence compared | Verdict / remaining delta |
|---|---|---|
| Separate replaceable live preparation | No live_memory runtime module or preparation composition/API; new memory_search is legacy query adapter only | NOT DONE new controller, existing search reused |
| Authenticated utterance/provider item/content revision identity | Existing Voice IDs/entry indices; selector InputIdentity has fields; no input-event coordinator | PARTIAL primitives, NOT evolving-input state owner |
| Every edit/delete/empty/abandonment invalidates immediately | Help onChange updates React draft only; final Voice capture stores final entries | NOT DONE shared invalidation |
| Meaningful coalescing/debounce plus max-wait | No draft API/scheduler/worker or corresponding tests | NOT DONE |
| One current/one pending and real underlying-worker accounting | Offline synchronous selector has deadline checks; no underlying work pool | NOT DONE; selector cancellation is not physical cancellation proof |
| Parallel memory/intent/procedural lookup and bounded context reconsideration | No live route; existing memory search final-only; no rule store | NOT DONE orchestration |
| Exact current prepared memory IDs/versions/authority/preference/generation | C17A ValidationToken compares fields through injected callback; no prepared memory producer/cache | PARTIAL DTO/parser guards, missing runtime producer/validation |
| Final Send freezes new turn | C03A immutable submit_text does exist, unmounted; Help sends client message directly | PARTIAL storage foundation, not connected final handoff |
| Changed negation/name/amount forces final-relevance validation | No prep context used in mounted conversation | NOT DONE; cannot claim correct speculative reuse |
| Current-memory batched validity without new embedding RTT | No memory retrieval epoch/batch validator | NOT DONE |
| No provisional tool effects/durable draft learning | Existing Help only sends on submit; no live feature | No pre-Send executor introduced, but planned experimental enforcement NOT TESTED |
| Live Memory On/Off, epoch, persistence, late result invalidation | No setting/preference record/route/client controller in current code | NOT DONE; Off semantics locked, default/scope proposal not silently fixed |
| OpenAI partial/final source correlation and controlled response handoff | Current final transcript handler exists; no dedicated partial prep adapter | NOT DONE experimental handoff; separate transcription feature audited next |
| VoiceMem feed_partial/_kick/_speculate/_confirm subset adaptation | Plan names stream.py and live_memory/voicemem_adapter.py; no code import/copy/symbol/adapter in app/frontend/dependencies/test sources | NOT DONE source adaptation; VoiceMemoryLearning factual finalize is NOT upstream VoiceMem |
| VoiceMem factual/entity slot hints/local classifier/brain candidate organization | Pinned local_query_classifier.py/leftbrain paths not ported; no hint translator/service | NOT DONE; classifier adoption conditional on quality/hardware evidence |
| Correct donor changed-final reuse/empty deletion/thread cancellation defects | No donor adapter/controller and no live tests | NOT DONE; do not copy faulty finalization unchanged |
| Exact donor file/license/NOTICE/change provenance | Research has upstream commit/license, no integrated copied-code manifest | Research DONE; implementation provenance NOT DONE |
| Same-corpus final/indexed/VoiceMem held-out experiment | Existing tests use memory fixtures, no experiment harness/report satisfying evaluation plan | NOT DONE comparative evidence; no performance credit from donor paper |
| Recall, relevance, temporal/entity evidence and scoped gold | No frozen live benchmark corpus/tuning-vs-heldout report | NOT DONE; index recall differs from semantic gold |
| Input/queue/embedding/SQL/ready/Send/useful-response/audio timestamps | No live preparation instrumentation or paired On/Off data | NOT DONE performance evidence |
| Chat geometry/IME/reconnect, independent learner/selector disable and prediction/usefulness calibration | Existing baseline frontend/backend tests do not mount new live feature | NOT DONE integrated acceptance; thresholds remain undecided |
| Exclude donor store/ASR/persona/emotion/voiceprint | No donor subsystem introduced by built slices | Preserve exclusion; do not build those as missing scope |

Repository-wide donor-symbol and behavior searches complement the positive input/
composition traces; they are not the sole proof. No runtime consumer/import of
DecisionSelector found outside its own module/tests. Prior107-case C17A tests prove
offline parsing/stale rejection, not live input, VoiceMem or scheduling. No new
test run specific to a nonexistent controller. Evaluation assumptions/paid budget
not invented. Reuse MemoryService/selector/scoped auth; NEW modular controller/
client and licensed adapted subset only under reviewed contract. No replacement
memory pipeline/store, no pre-final tool execution. This feature remains unfinished
and must be carried in build planning without duplicating existing primitives.
