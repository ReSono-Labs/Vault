# C03R/r1 — source/contract review

2026-10-07. Internal same-context review, not independent assurance/owner acceptance.
Owner explicitly authorizes aligned contracts/build on feature/live-memory-decisions.
Current source methods, composition/VoiceMemoryLearning, events API, existing Voice
tests, global safe-DB gate and test harness inspected; no C03R runtime delta yet.
Dirty owner files/untracked foundations preserved. Source hashes must verify.

| Gate | Source-backed attack / result |
|---|---|
| Goal/necessity | Actual dual commits and duplicate skip lose transcript. Original R12/R31/R32 require truthful final evidence. PASS bounded repair, not new architecture |
| Reuse | Existing provider hash/replay and authorization are reused; one insert implementation per repo, no new schema/event store/authority. PASS |
| Compatibility | Public append/provider signatures and result DTOs retained. Only capture enables exact transcript guard; legacy append behavior unchanged.201/200 unchanged. PASS candidate; regression proof required |
| Atomicity/close | Existing connection context and _session_cursor(for_update) support shared UOW; close already locks row. PASS design; real fault/concurrency proof required |
| Replay | Exact open-session legacy missing projection can be repaired; changed text/metadata conflicts. No historical closed repair, overwrite or tool replay. PASS |
| Scope | Existing login/member/user/workspace/originating Voice session checks reused; no stronger unproved midtransaction revocation guarantee. PASS bounded invariant |
| Modularity | Minimum transaction adapters in existing capture/source owners, not scheduler/model/business logic in hosts. Existing mounted caller needs no API/composition rewrite. PASS |
| Effects/privacy | Final sources only; no drafts, model/tools/provider/network, retention or grants. PASS |
| Test safety | Exact resono_vault_test/loopback55436/isolated volume/global pytest gate; preflight before schema-dropping fixtures. CONDITIONAL operating check |
| Evidence limits | Fake ports insufficient; rollback after each write, concurrency, changed/legacy replay and existing scope regressions mandatory. No full-session/summary/HNSW completion claim. PASS |

Material alternatives: new ledger/outbox; separate commits/retry; shared existing
connection. Select last for same-DB pair. Counterexample: nested connect, orphaned
commit, swallowed mismatch, deadlock, changed public append behavior or private
scope leak. Stop/reopen on any; no scope widening/test weakening. Result **PASS
to READY for C03R/r1 only**, subject to verified hashes and safe test-target preflight.
All other unreviewed allocations remain unready; prior VERIFIED code retained.
