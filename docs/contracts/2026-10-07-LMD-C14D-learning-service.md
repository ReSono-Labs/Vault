# C14D/r1 — end-to-end procedural review/publication service

Owner authorizes same model logic sequentially after or parallel with memory.
Reuse C14A DecisionReviewer, C14B fenced checkpoint and C14C inactive generation/
vector repository; no new source/model/store/agent. NEW decision_learning/service.py
is one caller-owned synchronous unit, not a durable worker or Background goal.
Existing source-current gate remains mandatory. It never calls memory publication,
tools, activation or selectors. It may be invoked after memory independently.

Claim before model call; completion then idempotent generation publication, then
scoped embedding outside DB locks and checked vector write. If no lease acquired,
inspect exact source review: running -> pending; completed -> recover immutable
output/model and resume publication/vector maintenance without repeating model.
Provider/model identity at completed review is read from existing selected-provider
configuration; actual reviewer returns model. Selected provider must be bound to
the runner call, not guessed by service. Alternatives: extend runner observations
or require explicit call-bound identity. For this child select the latter, avoiding
another change to existing memory/provider contracts: receive provider from the
caller; service verifies completion against immutable stored value on retry. Production
composition must bind that identity to actual runner; unbound source/selection
remains not mountable. No default arbitrary provider in active use.

Explicit scoped embedder factory; absent/unavailable/incompatible embedding remains
pending, never substitute vectors. Returned counts/states distinguish proposals
stored, generation published, vectors ready/pending and review pending/failed.
Review failure records retryable lease when still owned. Source/publication failure
does not undo memory or completed procedural review; next call retries publication.
Lease expiry prevents late model result publication. No silent exception strings.

Narrow repository addition: exact source-status read with current source authority,
returns review ID/state/provider/model/output; bounded one row, no raw input. Never
infer complete evidence from completed flag; input/source gate still required.
Tests actual isolated DB with synthetic shared model and embedder: new successful
flow, no second review after completion/retry, embedding failure resumes without
another model, source guard failure prevents model, pending lease prevents model.
Internal prebuild review CONTINUE unmounted end-to-end service only. Production
source loader, provider binding, worker process, activation and UI integration remain.
