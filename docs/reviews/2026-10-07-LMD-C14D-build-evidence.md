# C14D/r1 — end-to-end independent learning unit

New DecisionLearningService joins existing C14A model review, C14B fenced claims
and C14C generation/example/vector writes. Claim precedes model, completion
precedes publication, actual scoped embedding occurs outside DB locks. No memory
publication, tools, routing or activation. Completed review is independently
recoverable; missing vectors resume without another model call. Pending live lease
does not call model. Null/incompatible embedding remains pending, never fabricated.

Actual isolated PostgreSQL **2 passed in 5.04 seconds**, synthetic shared configured
model/executor and synthetic vectors only. Tests prove full qualified DTO -> model
-> durable completion -> generation -> real vector storage; duplicate call preserves
same result with one model review; vector availability resume keeps same review/
generation; pending lease and stale source suppress model; changed provider binding
does not overwrite completed review. `git diff --check` passed; harness stopped.

No production source loader/provider binding/worker mount is delivered. Explicit
provider argument must be bound to the actual selected runner by composition;
service does not establish that fact by receiving a string. Source-current gate
must qualify causality, capability state and forgetting in production. This child
is an unmounted caller-owned sync unit, not heartbeat/restart/shutdown scheduling.
Generation remains inactive; complete C14 and original full build are not claimed.

Repository only adds exact source-status read; C14B original manifest remains
historical. Canonical memory capture/analysis and all grants remain unchanged.
