# Owner-reported completed build: baseline discrepancy

Owner reports full branch build a few days ago, with planning references awaiting
Decisions API and everything else already built. Preserve that statement as the
expected comparison target; do not substitute newly generated contract statuses.

Read-only checks performed 2026-10-07:
- Local heads/remotes/tags list only main, feature/live-memory-decisions and
  origin/main, all ea39a6f9da89a2999c4f7e14f686428d2088f480. One worktree.
- Reflog checkout on October5: main -> feature/live-memory-decisions at that commit;
  all-ref reflog contains no other newer completed-build commit. Git fsck
  --no-reflogs --unreachable completed with no unreachable objects reported.
- October4/5 PROJECT-STATE checkpoints at lines1066–1190, CHANGELOG and
  October5 Phase02 review describe documentation/planning, Decisions deferred,
  no full feature implementation. They do NOT independently prove a later build.
- Existing baseline DOES implement canonical memory/reviewer/vector storage,
  Voice transcript/finalization, tool ledgers/authority, text Help and file uploads.
- standalone-vault-test README points to prebuilt resono-labs-vault:local, not
  another source checkout. Its named user-data volumes were NOT inspected.
- Actual installed resono-vault-vault-1 image matches local image
  sha256:3943843df557bc0ac5c4778cc171a2543259dc197f80c0bb8d4f5f6f359ecc8f,
  created 2026-09-21T07:44:39.617681778-04:00, no revision label. Read-only source
  listing /opt/resono-vault/app/vault_runtime includes baseline memory/voice/Help,
  no conversation/decision_routing/memory_search/live_memory/decision_learning
  packages. No restart/build/migration or production record access occurred.
- User asked asynchronously for branch/build name/location; unresolved.

Disposition: completed-build reference remains UNLOCATED, not disproved. Current
all-contract audit is checkout-scoped only. No rebuilding missing-looking features,
new readiness or remaining-build count until expected artifact is found or owner
resolves baseline. Do not discard code/history to reconcile contradictory records.
Need branch/commit, other checkout, build-evidence file or artifact identifying
that full build. Existing tests verify this checkout, not an unlocated branch.
