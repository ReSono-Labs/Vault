# C06C/r1 internal source/attack review

Same-context review PASS bounded adapter. Existing MemorySearchBackend and
PreparationPorts already define required interfaces; no third search/decision
protocol or new scheduler is necessary. Indexed backend already uses canonical
MemoryRetriever ranking and SQL scope/fingerprint/model compatibility checks.
CurrentStateGuard already checks current scope/epochs/canonical DTOs; controller
checks it before work and publication. Avoid duplicate per-method state checks.

Legacy MemoryService can repair missing embeddings during search, violating the
no speculative canonical writes boundary. Select direct read-only backend and
reuse only scoped factory availability behavior, not interactive repair. No
OpenAI transport/schema/dependency change is in this contract.

Exact query/context equality is a provable reuse baseline. Changed prefixes may
still retrieve identical IDs, but only fresh current-query ranking justifies
rebinding; embeddings cannot certify unchanged action semantics. Negation/person/
context changes never carry complete prior preparation blindly. No learned rules
or independent interpretation buffer is seeded. Required shared-context builder
and decision callback remain actual consumer dependencies, not defaults.

Existing candidate_set_fingerprint owns finite-choice structural validation;
do not duplicate it or equate it with permission. Actual procedural eligibility
still requires C14/C15 and external guard. Positive vectors/decision callbacks in
tests are synthetic, not historical learning or production quality evidence.

Counterexamples reviewed: default legacy repairs during draft, factory accesses
another workspace, changed-person old cache marked complete, fresh memory reaches
only memory branch, callback choices malformed, provider revocation publishes old
lexical payload, missing context treated as certainty. Source-frozen proof and
actual PG/controller checks required, not standalone helper existence.
