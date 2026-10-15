# C14K — qualified Chat review to existing inactive rule/vector publisher

REUSE exact Vault `decision_learning/{voice_review,service,rules,repository}.py`,
`decision_routing/example_index.py`, existing scoped embedder factory and composition.
NEW joining adapter `decision_learning/chat_learning.py` only. No second reviewer,
rules schema, similarity scan, agent, grants, provider or background scheduler.

CONTINUE: post-completion hook consumes exact committed review/checkpoint. Extract
existing publication/embedding stage into a reusable service method; it cannot call
the reviewer. Unknown source or no changing proposals skips publication. Changing
complete qualified output builds existing inactive generation and real embeddings;
owned HNSW index initialization reuses existing concurrent/advisory/identity checks
before publication. Failure preserves completed review and ordinary Chat answer;
same ended-segment retry resumes publication/vectors, never reruns model/tools.

No automatic activation claimed in this slice: existing mandatory compiler gates
and live active-reader mount remain next. Current credentials and source-current
gate checked before database publication; no fake vectors on provider failure.
Safe operational logging records state/counts, not prompts, sources or credentials.
Disabling existing decision-review configuration removes hook and review together.
Counterexamples: duplicate retry, source erased after review, index conflict, model
re-execution on embedding failure, unknown capture publishing. Internal prebuild
review CONTINUE bounded inactive publication; prove mounted synthetic provider and
real isolated pgvector storage before verification.
