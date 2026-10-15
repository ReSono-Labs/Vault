# C06B/r1 internal candidate attack review

Same-context source/internal review PASS bounded guard/lifecycle only. Existing
C13B snapshot queries and C07A get currently open separate connections; naïvely
calling both cannot claim coherent combined state. Extract internal cursor bodies
and use one REPEATABLE READ transaction with existing authority locks. No provider
work while transaction open. Existing public methods remain behavior-compatible.

Final header increment would otherwise defeat exact draft reuse. Actual C03A
SubmittedTurn stores submitted_history_version and exact input_fingerprint;
validate current header==base+1, scope/segment/fingerprint and submitted/running
state, then use base in guard identity. Competing turn/current-source changes
still invalidate. This is not an execution permission or context completeness
guarantee. External source/procedural guard must be required, never defaultTrue.

Scope counters cover additions and record values cover returned DTO compatibility;
same-version metadata changes are not dismissed. Archived/sealed/missing or wrong
scope rejects. Existing session predicate reused; no synthetic LocalPrincipal.

Registry owns only handles to already built streams, not another controller.
Threaded API cannot directly mutate asyncio stream events; use owning-loop
call_soon_threadsafe after immediate registry removal. Fresh guard rejects Off
while callback is queued. Capacity explicit, duplicate key rejected. Existing
workers drain and retain permits, never claim synchronous provider cancellation.
Committed-setting callback failure is truthfully reported, not rollback fiction.

Counterexamples reviewed: mixed snapshots, final text forged, newer turn ignored,
Off callback targets all users, closed loop error hidden, callback failure claims
setting not committed, stale registration sneaks after notification, registry
grows unbounded. Stale registration remains a caller/guard freshness requirement;
guard rejects at publication. No production mount approved here.
