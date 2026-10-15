# Feature 06 — session evidence and complete-session review

Validation date: 2026-10-07. Authority read in full: complete-session-memory-analysis-plan r5. Related procedural requirements are in decision-learning-plan r4. This is source validation, not a production-data inventory or permission to implement.

Verdict: existing scoped Voice transcripts, factual reviewer, reconciliation and embedding pipeline ARE implemented. The planned complete-session coordinator and attributable interactive reasoning/evidence capture ARE NOT implemented. They must extend existing authorities, not replace them.

## Requirement-by-requirement result

| Planned obligation | Actual implementation evidence | Disposition |
|---|---|---|
| Preserve taxonomy, citations and canonical reconciliation | memory/contracts.py, evidence.py, repository.py and pipeline.py already provide these | Reuse; no second canonical memory store/reviewer |
| Retained final Voice transcript and durable tool results | voice/events.py and voice/tools.py record existing scoped sources | Existing foundation, not complete causal coverage |
| Provider event and transcript atomicity/recovery | VoiceProviderEventCapture commits record_provider_event before separate append_transcript; append happens only when event.accepted | Missing shared transaction/outbox recovery; duplicate does not repair absent transcript |
| Server sequence and producer acknowledgments; unequal duplicate conflict | Existing transcript/provider repositories have their legacy identity rules; C03A has immutable submitted text | Planned generalized producer contract absent; do not copy immutable user text merely to create another ledger |
| Final user/assistant/model/selection/correction events with causal call IDs | No canonical conversation event capture owner or mounted interactive conversation runtime | Not implemented; reuse final turns and legacy source IDs where sufficient |
| Actual reasoning summaries per interactive Voice/text model call | background_agent/sdk_runner.py requests summaries and exposes observation_sink; background executor uses it; memory reviewer does not supply a sink | Helper exists, interactive capture/correlation absent. Background progress is not conversation evidence |
| Unsupported/absent/interrupted/truncated summary availability | SDK helper slices each summary to 16,384 characters without the proposed per-call availability record | Not implemented; never reconstruct original reasoning from reviewer inference |
| Capture denials, schema failure, cached replay, actual start/result and unknown effect | VoiceToolRuntime returns denials before claim; replay returns before catalog; catalog observer runs only after handler and swallows observer errors; no production setter caller | Existing invocation/result ledger must be adapted; observer alone cannot satisfy requirement |
| Distinguish transport state, result error and useful request resolution | tools.py complete stores isError and sets invocation state succeeded regardless of that value | Raw facts exist; proposed independent evidence axes and qualified interpretation absent |
| Review every retained source span without truncation | openai_reviewer.py slices input at FINALIZATION_TRANSCRIPT_CHARACTER_LIMIT=100,000, including Gemini path | Not implemented |
| More than 32 supported facts without silent dropping | _parse_review slices candidates at FINALIZATION_CANDIDATE_LIMIT=32 | Pagination/overflow protocol absent |
| Stable oversized-entry spans and global citation mapping | Pipeline joins entryIndex-labelled text in one review call | Window adapter and spans absent |
| Hierarchical bounded consolidation and cross-window corrections | No memory_analysis package or consolidation tables/callers | Not implemented |
| Claim durable leased job before model work; resume windows on restart | Pipeline calls reviewer before claim_ingestion; no window leases/checkpoints | Existing ingestion guard is not planned coordinator |
| Atomic candidate publication and independent retry | store_summary, reconcile_memory and complete_ingestion are separate repository calls | Existing factual publication preserved; new atomic publication/checkpoint seam absent |
| Truthful coverage, dense-overflow failure and semantic quality | Current completed ingestion and summary are not source-range/consolidation coverage records | Not implemented |
| Independent canonical/procedural consumers | Canonical pipeline exists; procedural consumer absent | Keep canonical learning functional while adding optional consumer |
| Resumed contribution deduplication and late corrections | No history coverage/contribution owner | Not implemented; whole-session fingerprint alone insufficient |
| Attachment/extraction hashes and summary source metadata in snapshot | Current TranscriptEntry projection lacks metadata; no submitted attachment model path | Not implemented |
| Forget suppression and authorized historical rebuild | No proposed suppression/reintroduction contract or historical qualification report | Automatic historical rebuild remains blocked, not a reason to block ordinary existing learning |
| Worker stop/erasure invalidation and independently reported embedding status | Existing scoped storage/embedding behavior exists; new worker/caches do not | New owner lifecycle proof absent; FK existence is not worker cleanup |
| Full-context, restart, late-fact and >32-fact semantic acceptance | Existing reviewer units cover bounded current behavior | Integrated acceptance not present |

## Executed validation

`tests/unit/test_openai_memory_reviewer.py`, `test_memory_contracts.py`, and `test_memory_evidence.py`: **16 passed** in this audit. These validate existing behavior, not the missing coordinator. No reviewer/provider call, private history inspection or migration was performed.

## No-duplication instruction

Reuse MemoryRepository, existing reviewer schemas, canonical validator/reconciler, embedding provider and existing Voice invocation recovery ledger. C03A already stores immutable final text. C03B's additional user-final row remains withdrawn pending necessity proof; broader causal metadata/source coverage must be specified against these actual sources before any new durable table is approved.
