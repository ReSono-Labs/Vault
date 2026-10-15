# C13A/r1 same-context internal review

PASS for bounded prerequisite, not full maintenance/live readiness or acceptance.
Original storage race requirement and existing code, not an invented missing store,
justify correcting canonical store_embedding. Exact contract has no DDL/default
cutover or duplicate authority. Schema epochs/model-generation eligibility still
remain follow-on requirements; version checks are not a substitute for those.

Baseline real PostgreSQL reproduction before runtime edits:
.venv/bin/python scripts/test_env.py test -q
tests/integration/test_vector_write_postgres.py::test_correction_waits_for_checked_vector_write_then_removes_vector
FAILED as expected in 4.45s: correction was not blocked after vector job's content
check; test failure message identifies the unlocked interval. This establishes
the check/upsert race, not speculation from a table field. Fixture synthetic only.
Events released in finally; test connections closed. Reused exact test fixture.

Harness frozen uv sync rebuilt only this editable project following previously
reviewed package-data change; lock/dependencies unchanged. PG image
sha256:9b05db12a35460fff0587e009f9326e414a53e9484555547f96d214a2ba98ef7;
only resono-vault-test-postgres-data mount, loopback55436. No installed Vault DB.

Attack cases: TOCTOU correction, equal-text ABA, delete/cascade, revoke membership
or deactivate user/workspace mid-write, private/shared scope, invalid snapshot
version, producer errors. Select reuse of existing optional helper locks + same
transaction, not another auth query copied into a service. Provider operation
must remain outside locks. Shared authority then memory row lock serializes commits.
Real lock observation and post-commit vector/delete checks required after build.
No numerical product SLA; synchronization timeouts are test safety limits only.

Foundation manifests that name repository/service/pipeline will intentionally
change; previous evidence remains historical. Guard behavior preserved plus
scoped snapshot-safety delta. Run those consumers, not rewrite their manifests.
