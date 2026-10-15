# C06C/r1 — canonical recall adapter build evidence

Bounded internal verification, not full production Live Memory acceptance.
Contract and internal review were frozen before implementation. Only three new
source/test files implement this grouping; no existing runtime, schema, dependency,
composition or UI file changed for C06C.

## Actual wiring

`CanonicalPreparationPorts` joins existing `ParallelPreparation`/VoiceMem,
`CurrentStateGuard`, `MemorySearchBackend` and C17A choice validation. The existing
pgvector backend retains SQL/ranking ownership. Query interpretation and decision
retrieval are mandatory injected callbacks consuming the same snapshot; scoped
embedding availability uses the existing factory pattern. Repair-capable search
backends are rejected, so drafts cannot invoke canonical vector repair.

Exact text/context/validity reuse requires the current guard. Changed text drops
old candidates and performs fresh retrieval; the same relevant canonical memory
can return freshly bound. There is no invented semantic-equivalence cache. The
existing controller owns parallel work, memory-dependent reconsideration, stale
publication rejection, final rebind and cancellation/drain.

## Executed evidence

- New adapter plus existing live-component/current-state units: **54 passed**.
- Actual isolated PostgreSQL adapter test: **1 passed** (4.10 seconds).
- Final stricter constructor validation: adapter units **8 passed**, repeat of
  those already counted, not eight additional distinct tests.
- Total distinct targeted coverage: **55 passing tests**, no failures/skips.
- `git diff --check` passed; isolated harness stopped, retained volume untouched.

The DB test uses canonical synthetic 1536-dimensional vectors, the existing
HNSW/GIN migration and actual indexed backend. Evolving ABC drafts retain via
fresh lookup; changing to Sarah drops ABC and retrieves Sarah. Exact repeat avoids
another embedding request; exact submitted final avoids another request too.
Decisions receive the newly recalled memory through the existing reconsideration
path. Foreign private memory is excluded. Actual authenticated/CSRF Off API
invalidates the registered VoiceMem handle. Canonical embedding scans, vector
writes and reconciliation are patched to fail if called during drafts.

Only the exact isolated test URL/container was used. Embeddings and decision
callbacks were synthetic; no paid provider, production database or tool replay.
This small corpus does not establish a naturally selected HNSW query plan; prior
C02 plan evidence remains separate. No broad unit rerun was needed.

## Remaining work, explicitly not delivered

Trusted source-linked context and production query interpretation, real learned
decision retrieval/current eligibility, semantic-quality comparison, durable
vector maintenance/cutover and Chat/Voice enrollment remain. This adapter is
unmounted. Production search still defaults to the legacy backend. No complete
Live Memory, Decisions learning, Chat or original full-build completion claim.

Removal substitutes the existing preparation port; no canonical data deletion,
second scheduler, grant authority or procedural store was introduced.
