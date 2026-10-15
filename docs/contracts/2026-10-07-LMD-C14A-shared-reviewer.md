# C14A/r1 — reuse memory model execution for procedural review

Owner explicitly authorizes the same model/code logic with a separate Decisions
prompt, running parallel or after memory review. Select sequential independent
calls initially; no concurrency/budget change or new agent identity. Governing
learning plan/DA-R04–09 and BP-R02–03 remain unchanged.

Reuse exact existing Vault memory/openai_reviewer.py selected-provider,
background_access credentials/model, SDK executor, reasoning and Gemini structured
request. Extract a public structured-review method on the same reviewer; memory
review delegates with its original prompt/schema/100000-character slice. Do not
change memory parsing, taxonomy, publication, finalization or existing callers.
Gemini method gains optional prompt/schema parameters preserving existing defaults.
No provider client duplication, SDK upgrade or new network configuration.

NEW decision_learning/reviewer.py: strict typed finalized source envelope, linked
decision observations, existing definitions and current capabilities. No raw
draft source type. Explicit complete coverage required before the model call;
unknown/incomplete envelopes fail closed. Reject oversized input, never slice it.
Separate structured output proposes create/add_example/revise/no_change/
insufficient_evidence. Check exact contract, citations/point identities, current
capabilities and existing target IDs. Changing proposals require linked finalized
input and non-error, completed, resolved outcome; uncertainty yields no automatic
successful rule. This is a conservative initial proposal gate, not activation.
Do not equate summary text or tool transport success with solved request.
Output retains immutable fingerprint/model and validated proposals, not rules
already published. Source freshness/permissions remain publisher responsibilities.

NEW decision_learning/finalization.py: sequential callback coordinator returns
independent memory/decision outcomes; attempts Decisions even when memory fails.
No swallowing error as success, raw exception strings or new durable job store.
Unconfigured decision callback explicitly disabled. This component is unmounted
until trusted source loader and C14 durable scoped storage/publication exist.
No default empty evidence, fabricated capabilities or second source ledger.

Allowed files: existing openai_reviewer.py narrow extraction; new module files;
targeted tests and documentation. No composition/Voice/API/schema changes.
New module is CAPABILITY_ONLY; no registration in system-agent inventory.

Internal prebuild review: necessity established by owner and inspected reusable
provider code. Attack checks: malformed/extra output, forged citations/targets,
draft ingestion, unresolved/error/unknown-effect evidence, input/output overflow,
provider failure, memory failure and independent procedural failure. Generic
structured review changes are covered by unchanged existing memory reviewer tests.
CONTINUE for this bounded unmounted reviewer/coordinator; full C14 storage,
embedding/HNSW, source projection, retries, forgetting and production mount remain.
No acceptance claim beyond deterministic synthetic executor tests. Official
structured output guide fetched October7 supports typed schema use, not semantic
truth: https://developers.openai.com/api/docs/guides/structured-outputs .
