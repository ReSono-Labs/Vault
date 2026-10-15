# C14H — Chat procedural analysis on canonical completed evidence

Lifecycle correction: [C14I](2026-10-08-LMD-C14I-chat-session-boundary.md) supersedes
the per-turn dispatch below. Projection/shared executor remain; analysis now runs
at an explicit ended segment, not after each completed turn. Earlier bounded
evidence remains historical and does not approve repeated prefix review.

Classification: NEW joining adapter; REUSE existing C14G model execution, scoped
claims, durable assessments, canonical Chat events and invocation/result ledger.
Owner authority: continue implementation, reuse the memory model/runner with a
separate procedural prompt; analyze tool/context/result/satisfaction independently.

Exact reused sources under `/home/christian/Documents/Projects/ReSono-Labs-Vault/`:
`app/vault_runtime/decision_learning/{voice_review,repository,reviewer}.py`,
`app/vault_runtime/conversation/{runtime,runtime_store,model_capture}.py`,
`app/vault_runtime/conversation_tools/runtime.py`, `app/vault_runtime/composition.py`.
No donor mutation, new agent, transcript ledger, grants or provider runner.

Decision: analyze the current completed Chat prefix after a final turn, using the
existing bounded turn worker after response publication. Do NOT close a resumable
conversation on navigation/New Chat or pretend a completed turn closes a session.
Open-prefix coverage stays unknown and cannot create rules. Later final turns
produce a new fingerprint containing later corrections; retries reuse checkpoints.
Alternative of auto-sealing navigation breaks continuation and is rejected.
Full source-qualified session closure/publication/activation remains separate work.

Projection reads only scoped current canonical rows, ordered immutable turns/events
and original invocation results. Links tools to final input via actual turn IDs and
original call IDs; context and summaries must precede the call. Assistant finals
are linked by turn, not timestamp. Later final user turns remain session evidence,
not fabricated feedback links. Missing feedback/outcome stays unknown. Reject
in-flight/incomplete, ambiguous, oversized or noncontiguous capture. No paid calls
in tests. Callback failure cannot change the published response or repeat a tool.

Internal prebuild review: CONTINUE for bounded analysis only. Counterexamples:
correct tool/wrong entity, failed tool with succeeded transport state, absent
reasoning, post-call summary, changed prefix during completion, denied tool,
cross-scope rows and retry. Validate projection and actual runtime callback seam;
schema-only tests do not prove deployment or semantic judgment accuracy.
