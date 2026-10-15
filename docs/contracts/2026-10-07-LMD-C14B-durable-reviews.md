# C14B/r1 — durable independent procedural review results

Owner asks to finish Decisions using existing memory model logic. C14A supplies
reviewer; current learning plan owns scoped durable review identities/leases.
This child builds the review-job/result relation only, not active rule routing.
No new memory analysis, source payload ledger, provider or agent identity.

Existing absolute Vault donors: conversation/schema.py composite segment FK,
conversation/repository.py connection pattern/current-authority locks;
live_memory/preferences.py atomic SQL CAS; C14A typed review/input validation.
NEW decision_learning/schema.py/repository.py join these. Schema metadata owns
decision_reviews_v1; no inline changes to memory schema/composition/identity.
Review rows cascade from existing conversation segments, so existing logical
user erasure (deleting conversations) removes them without another cleanup loop.

One row per scope/conversation/segment/source fingerprint/learner contract.
Queued/retryable or expired-running claims atomically become running, increment
attempts and acquire fresh token/deadline. Lease seconds supplied explicitly;
no default test threshold becomes production policy. Unexpired/completed claims
return no work. Attempts plus token fence late workers, even same caller identity.

Mandatory source_current(cursor,principal,snapshot) gate, no default True.
It must perform bounded transaction-local source/forget/capability qualification,
not provider work. Current local session/scope locks and owning segment SHARE lock
hold through commit; never use another user's current workspace as review owner.
Fail closed on incomplete envelope, missing/foreign segment or stale source gate.
No claim that the production gate exists merely because callback is required.

Completion validates current lease/attempt, exact input fingerprint and C14A
proposal contract/citations before atomically committing completed output, model,
coverage and output hash. Exact retry acknowledges the same result; differing
result/worker/source conflicts, no overwrite. Unknown effects are not successes.
Failed live lease transitions retryable with safe fixed error code. Public read is
exact scoped ID, not unbounded history. Stored output is derived proposals, not
copied input text/source payload. No provider execution while DB locks are held.

Internal prebuild review: schema reuse/necessity established above; narrow child
does not activate rules or bypass forget policy. Attack tests: duplicate concurrent
claim, expired lease/late completion, exact retry/conflicting output, changed source,
revoked scope, foreign segment, deletion cascade and repeated schema install.
Only exact isolated test harness; no actual model/provider/history access.
CONTINUE bounded unmounted durable review store. Definitions/examples/vector HNSW,
generation publication/activation and trusted source loader remain following work.
