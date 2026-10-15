# C14B/r1 — durable procedural review checkpoint evidence

Bounded contract/internal prebuild review precedes implementation. Reuses canonical
conversation scope/segment identity, existing neutral authority locks/connection
pattern and SQL CAS. Only owned decision_learning schema/repository, narrow C14A
validation hardening, tests and docs changed. No memory/Voice/composition/identity
runtime changes, production DB access, donor mutation or paid model execution.

## Delivered code and actual behavior

`vault_decision_reviews` stores scoped review identity, source hash, learner
contract, lease/token/attempt, status, derived proposals, model/provider and output
hash. It does not store another transcript or provider payload. Its composite FK
points to the existing canonical conversation segment; deletion cascades from
existing conversation erasure. No active rule pointer or permission authority.

`DecisionReviewRepository` requires an explicit transaction-local source-current
gate and current principal authority. Atomic insert/CAS yields one owner for a
snapshot; unexpired/completed rows are not reclaimed. Retrying or expired work
gets a new token and incremented attempt, fencing late workers. Completion checks
source hash, current gate, active lease, scoped segment and strict proposal DTO;
then commits result/status atomically. Exact result retry is acknowledged;
different output/model/provider or stale worker conflicts. Retryable failure stores
a fixed safe code, not provider error strings. Scoped exact-ID get returns output.

C14A hardening rejects serialized result overflow and unchecked model-copy contract
changes at the durable boundary; no silent slicing or reconstructed summaries.
The existing configured model reviewer still runs outside DB transactions.

## Targeted executed evidence

- Units: **28 passed**, existing memory-review compatibility + procedural reviewer
  + five new repository-boundary cases; no broad suite rerun.
- Actual isolated PostgreSQL: **3 passed in 6.69 seconds** after final durable
  validation changes; earlier same three passed in 6.79 seconds, not additional
  distinct coverage.
- Total distinct coverage **31 passing tests**, no failures/skips.
- Tests prove simultaneous claims yield one owner, exact completion retry, no
  overwritten output, same-workspace foreign-user denial, expiry/retry fencing,
  changed/stale source rejection, invalid output contract, repeated schema install,
  actual secondary-account erasure cascade preserving owner's conversation, and
  revoked session authority. No arbitrary sleep or fabricated vectors/provider.
- `git diff --check` passed. Test harness stopped; volume retained.

Synthetic source gates/DTOs are explicit fixtures, not proof that production
causality/source/forget qualification exists. No real historical session was read.

## Remaining full Decisions work

This is **review-result publication**, not learned-rule publication. Trusted
production source/forgotten-fact gate, worker scheduling/heartbeat/shutdown,
definitions/examples/versioned generations, real vectors/HNSW, activation/current
capability checks and actual after-session mount remain. It is deliberately
unmounted until those prerequisites are implemented. Retention of derived review
output does not authorize learning from forgotten facts or raw drafts.

Removing the optional repository/reviewer does not delete source history, memory
or grants. Dropping a derived generation later cannot cascade into canonical
session evidence. C14A's old implementation manifest is historical because its
reviewer/test received bounded validation hardening; new C14B hashes record it.
