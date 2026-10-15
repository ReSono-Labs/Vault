# C06E/C13C — mounted Chat preparation and indexed startup checkpoint

Branch `feature/live-memory-decisions`; existing dirty work preserved. Original
grounding remains authoritative. This is bounded implementation evidence, not
full-build/release acceptance or evidence of paid-provider success.

Actual composition mounts `live_memory/chat_runtime.py`: authenticated bounded
revision/status/discard routes, existing VoiceMem external-text lifecycle and
parallel canonical ports, current scoped memory SQL retrieval and current-granted
tool catalog selection using the standalone Decisions transport. The Chat observer
renders actual returned candidates, invalidates on edits/IME/empty input and clears
on Send. Drafts never become canonical turns or execute tools. The exact immutable
final can reuse preparation after the existing current-state gates; ordinary final
retrieval remains the fallback. Current tool routes are explicitly catalog proposals,
not learned-rule matches. The existing selector supplies its explicit fallback.

`memory_search/maintenance.py` replaces the old one-shot repair thread. Owned
concurrent HNSW/lexical migration runs outside schema/request transactions. Successful
validation switches normal lookup to the existing indexed backend. Operator rollback:
`RESONO_VAULT_INDEXED_MEMORY_ENABLED=false`; live preparation reports unavailable.
Maintenance rotates a bounded 32-row scope batch, includes stale fingerprints,
resumes from canonical missing-vector records, signals cancellation between records,
and never repairs vectors during indexed reads. A provider call already in flight
retains its existing timeout; shutdown does not claim to kill that thread.

Mounted testing exposed a real PostgreSQL serialization conflict: authenticated
polling updates session rows while coherent repeatable-read authority captures lock
them. `LiveStateLoader.capture` now retries only SQLSTATE 40001, at most three fresh
transactions, materializing selected IDs once. No model or tool work is retried.

Verification (isolated `127.0.0.1:55436/resono_vault_test`, synthetic providers):

- 162 focused live/selector/canonical recall/embedding/catalog unit tests pass.
- Two maintenance, four transport, and seven snapshot/current-state tests pass.
- Four mounted Chat preparation/final runtime checks pass, including actual default
  indexed cutover, semantic recall, dependent reconsideration, authentication/CSRF,
  no draft turns/tool effects, deletion/late revision fencing, and exact-final reuse.
- Production TypeScript/Vite build succeeds; nine Chat/controller/observer tests pass.
- Actual Chrome fixture with populated provisional memory/tool preview passes at
  360×800, 390×844, 768×1024, 667×375. Geometry/screenshots:
  [mobile metrics](2026-10-07-C06E-mobile/metrics.json). Synthetic fixture is layout
  evidence only, not provider end-to-end evidence. Physical keyboard testing remains.

Transport follows the [official standalone Decisions guide](https://developers.openai.com/api/docs/guides/decisions),
fixed API endpoint, separately scoped API key, bounded response and safe failures;
no GPT-Live or SDK upgrade. Provider credentials, raw exceptions and draft content
are excluded from operational diagnostics. Existing structured live events retain
revision/phase, lookup/reconsideration/staleness, counts and timing for stress analysis.

Incremental-display follow-up: validated memory becomes visible while the same
parallel attempt waits for selection; tool proposals remain absent until fresh-memory
reconsideration finishes. Mounted acceptance explicitly blocks synthetic selection,
observes interim actual SQL memory with no tools, then releases selection and verifies
final reuse. After this change, 62 targeted component/current-state/transport checks
and the mounted preparation check pass; the maintenance suite now has three checks.

Still open: learned active-example consumer/qualification, complete Chat factual and
procedural session learning, complete Voice causal/window coverage and live mount,
remaining original provider/attachment/parity/release gates. Do not mark parent
contracts complete from this checkpoint. Removal is optional preparation host/UI
plus maintenance rollback; canonical history, memory, permissions and tools survive.
