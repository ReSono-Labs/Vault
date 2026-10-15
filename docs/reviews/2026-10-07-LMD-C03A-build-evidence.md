# LMD-C03A/r1 — Phase03 build evidence

2026-10-07. PASS for bounded C03A/r1 implementation; VERIFIED, not owner acceptance.
Internal same-context review only. Owner continuation authorizes one READY slice.

## Restart and material gates before implementation

Contract hash matched frozen READY identity f20ff2c3cd7ee2bcdac753e9bef9964c6037cac6c3b4924a4b47ece583ea51df.
Planning-input manifest all OK; source manifest all OK except MemoryService,
the intentional verified C01 edit. C01 exact six-file implementation manifest all OK.
Split review hash matches frozen identity. No stale C03A owner sources found.
Existing local_identity/repository.py has no working diff before this slice.

Requirement: private scoped persisted identity/final text with exactly-once retry
and current local-session authority. Owner: new conversation module. Paths:
four named conversation files, two named tests, one erasure-list entry. Forbidden:
production mounting, Voice/provider/model/tool/learning calls, drafts, UI, dependencies.
Next check: typed-validation units then real isolated-Postgres contract scenarios.

NEW owner-directed work, not claimed donor parity. Existing conventions reused from
absolute Vault sources /home/christian/Documents/Projects/ReSono-Labs-Vault/app/vault_runtime/
local_identity/{schema,repository,models}.py and voice/repository.py:_require_authority.
No donor repository edits or new copied donor feature; C03A explicitly authorizes NEW.

Gate: authorization from saved conversation/login identity or live authority?
Authority C03A and split review S04 plus inspected current Voice auth predicate.
Alternatives saved identity only, live query without locks, live scoped query with
FOR SHARE through commit. Select last: revoked/expired credentials and inactive
membership/user/workspace deny; private rows require exact user/workspace.
Counterexample: another member/owner reads private row or revocation commits before
append finishes. Dependents capture/chat; CONTINUE bounded unmounted repository.

Gate: acknowledge speculative drafts, overwrite a repeated key, or preserve exact
final text and idempotent identity? Authority C03A submitted-only contract. Select
final text + SHA256 and key check before history comparison, header lock for
atomic ordinal/version. Counterexamples duplicate increment, changed-content retry
accepted, stale concurrent append or rollback partially advancing header.
Dependents canonical capture/reviewer; CONTINUE with real DB negative tests.

Gate: user FK cascade alone or explicit existing erasure-list integration?
Actual owner_remove_user tombstones user, so FK alone fails shared-workspace erasure.
Select only specified optional-table entry + existing scoped cascades. Counterexample
removed user's shared-workspace turns retained or another member's rows erased.
Dependents activation/erasure; CONTINUE, no cleanup scheduler or production mount.

Test safety: resolved Compose database resono_vault_test, host127.0.0.1 port55436,
volume resono-vault-test-postgres-data inspected. scripts/test_env.py resolved DSN
also asserted exact target without printing credentials. Container initially stopped.
Destructive fixture must independently reject unsafe DSN before schema cleanup;
no volume reset/down --volumes or production DB access authorized.

## Frozen candidate and actual verification

Exact candidate: [seven-file implementation manifest](2026-10-07-LMD-C03A-implementation.sha256).
Identity excludes this evidence, manifest, lifecycle metadata and documentation
checkpoints. It includes the complete changed identity repository (one new list
entry), four new conversation files and two new tests. Earlier planning/source/
READY manifests remain historical; C01 and this slice intentionally change source
and lifecycle metadata, not the unchanged remaining contracts or planning inputs.

Environment: Python3.13.2, psycopg3.2.3, existing PG16 pgvector test image and
locked dependencies. HEAD ea39a6f9da89a2999c4f7e14f686428d2088f480, branch
feature/live-memory-decisions, dirty owner work preserved. No new dependency,
frontend/composition/API edit, donor mutation, provider traffic or commit.

| Exact check / command | Expected | Actual / exit | Date |
| --- | --- | --- | --- |
| Frozen input manifest and C01 implementation manifest `sha256sum -c`; C03A/review direct hashes | Match reviewed inputs plus intentional C01 | Match; historical source differs only verified C01 service before C03A | 2026-10-07 |
| `.venv/bin/python -m pytest -q tests/unit/test_conversation_identity.py` | Typed validation and dependency tests pass | 26 passed, 0.48s / 0 | 2026-10-07 |
| `.venv/bin/python scripts/test_env.py up` | Start existing isolated harness only | Healthy / 0; frozen sync audited48 packages, no lock change | 2026-10-07 |
| `docker inspect resono-vault-test-postgres --format '{{range .Mounts}}{{.Name}} {{.Destination}}{{println}}{{end}}{{json .NetworkSettings.Ports}}'` | Test volume and loopback port | resono-vault-test-postgres-data at /var/lib/postgresql/data;127.0.0.1:55436 | 2026-10-07 |
| `.venv/bin/python scripts/test_env.py test -q tests/integration/test_conversation_identity_postgres.py` | Real DB proof, zero skips | 51 passed,79.95s / 0 | 2026-10-07 |
| Combined focused unit/regression command below | C01 and account storage compatible | 74 passed,0.79s / 0 | 2026-10-07 |
| `.venv/bin/python scripts/test_env.py test -q tests/integration/test_local_identity_postgres.py` | Existing identity/account behavior, table-absent cleanup compatible | 14 passed,31.79s / 0 | 2026-10-07 |
| `git diff --check` | Whitespace clean | No output / 0 | 2026-10-07 |
| C01 manifest recheck after C03A | Prior implementation intact | All six OK / 0 | 2026-10-07 |
| `sha256sum -c docs/reviews/2026-10-07-LMD-C03A-implementation.sha256` | Frozen implementation intact | All seven OK / 0 | 2026-10-07 |
| Scoped test-DSN read of current_database/server_version/to_regnamespace after fixtures | Test DB only; fixture schema removed | resono_vault_test, PostgreSQL16.15, vault_private absent / 0 | 2026-10-07 |
| `.venv/bin/python scripts/test_env.py stop`; `.venv/bin/python scripts/test_env.py status` | Restore stopped harness without deleting volume | Container/network stopped/removed; status empty / 0 | 2026-10-07 |

Combined focused check:

```sh
.venv/bin/python -m pytest -q tests/unit/test_conversation_identity.py tests/unit/test_memory_search_boundary.py tests/unit/test_memory_search_boundary_callers.py tests/unit/test_memory_retrieval.py tests/unit/test_memory_contracts.py tests/unit/test_memory_evidence.py tests/unit/test_scoped_tool_catalog.py tests/unit/test_tool_catalog.py tests/unit/test_memory_adapter_package_contract.py tests/unit/test_workspace_storage.py
```

All new checks passed first execution; no failed-test correction or weakened
existing test. Broader unit suite not rerun in C03A; prior C01 evidence records
four independently reproduced unrelated failures. No whole-suite PASS claimed.

## Review of complete actual change set

Internal same-context review PASS against frozen implementation, source authority,
contract and module r5. Four runtime files own only identity/validation/persistence;
no provider/model/tool/scheduler/reviewer/cache or JSON evidence duties. Current
host imports none of the conversation package; schema installation is explicit,
not production startup. One canonical conversation store, no fake Voice sessions.
Only existing runtime change is the specified optional erasure-list entry.
Imports point to neutral existing LocalPrincipal/Cursor, not Voice runtime.
Reviewed actual tracked identity diff, all untracked module/tests, imports, SQL
parameters, constraints and caller-visible returns; no source deletions/renames.

Functional evidence: ten create retries share header+segment; ten equal submission
retries share one exact persisted text/turn/version; changed-key-content rejects;
old retry after newer turn returns original committed submit version. Four concurrent
creates produce one identity; concurrent different submits at same version produce
one commit and one conflict. Exceptions injected before/after turn insert and
after header increment roll back both; create failure after segment insert leaves
neither header nor segment. Exact UTF8 boundary is accepted, extra byte rejected
before writes; whitespace preserved and SHA256 matches actual bytes.

Every operation checks live session/user/membership/workspace under shared locks,
and queries exact private scope. Shared workspace/device ownership does not reveal
another user's conversation. Forged principal workspace denied. Revoked membership,
session, inactive user/workspace and expiry deny reads, creates and duplicate retries.
New login can read prior finalized turn; no login-session FK deletes history.
Real concurrent revocation was observed waiting in pg_stat_activity with
wait_event_type='Lock' while append held authority; it commits afterward, and the
next read denies. No hidden retry or claimed physical provider cancellation.

Independent direct SQL tests reject cross-user/workspace/conversation segment
references, invalid states, negative ordinals/versions, malformed fingerprint size,
oversized/empty text, duplicate keys/ordinals, excessive title and second open segment.
Repeated schema installation retains rows and fingerprint. Actual remove_user
tombstone erases removed user's shared rows and retains owner rows; separate
physical-user and workspace deletion tests prove cascade cleanup. These prove
database behavior, not mocked-only scoping or production deployment readiness.

## Current state and limits

C03A/r1 VERIFIED, not CLOSED. No active Chat, stream, drafts, event ledger,
reasoning-summary capture, Decisions transport, session review or learning yet.
No historical user content inspected. Internal65536-byte bound is not a final
Chat/model limit. No title/state/segment continuation mutation interface introduced.
Rollback of unmounted module is possible; never disable erasure with retained
owned rows, and never drop existing production content to reverse this slice.

Test fixture cleans only verified test schema (no production data). Test-only volume
created by existing harness and preserved; stop harness after verification to
restore initial stopped state. Other user work remains untouched and uncommitted.

Exactly one next route: Phase03 C17A/r1 offline selector boundary after restart and
input verification, then stop/checkpoint. C03B/C08 require dependent-contract review
against this exact verified output; no runtime evidence capture is assumed present.
