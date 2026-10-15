# C03R/r1 — bounded final implementation evidence

2026-10-07. Internal same-context contract/code review, not independent assurance,
owner acceptance or integrated release readiness. Built on existing
`feature/live-memory-decisions`, HEAD ea39a6f9da89a2999c4f7e14f686428d2088f480.
Dirty owner work preserved; no commits, branch switching, reset or donor writes.

## Requirement and actual wiring

[Reviewed contract](../contracts/2026-10-07-LMD-C03R-source-capture-repair.md)
implements only the R01/R12/R22/R26/R31/R32, DA-R04–07/11 consistency delta.
Composition's existing VoiceMemoryLearning -> VoiceProviderEventCapture mount and
local_api events endpoint remain unchanged. Existing provider event and final
transcript now use one supplied connection to the same configured database.
No new table/schema/migration, endpoint, event framework or source authority.

Runtime allowlist satisfied: voice/repository.py exposes the existing transaction
and supplied-connection event primitive; memory/repository.py exposes supplied-
connection append with opt-in strict role/type/text/metadata comparison;
voice/events.py orchestrates both and translates transcript conflict into existing
VoiceSessionConflictError after rollback. Existing hash/auth/membership/storage
implementations are reused, not copied. Public signatures and TranscriptEntry
shape unchanged; unrelated public append retains legacy duplicate behavior.
Shared pure validators preserve invalid public arguments failing before DB connect.
The existing scoped session FOR UPDATE serializes capture with close.

Exact duplicates return accepted=False and ensure final projection exists;
missing legacy projection is repaired only in an authorized still-open session.
Changed provider content uses the original hash/type/role/index check; changed
transcript fails without overwrite. Exceptions roll back both writes. No-transcript
capture still stores only provider event. No tool/model replay or external effects.

## Final verification

| Exact command / check | Actual result |
|---|---|
| `.venv/bin/python -m pytest -q tests/unit/test_voice_capture_transaction.py` | 19 passed, 0.08s |
| `.venv/bin/python -m pytest -q tests/unit` | 462 passed, 4 failed, 14.22s; same four recorded in prior C17A evidence |
| `.venv/bin/python scripts/test_env.py test -q tests/integration/test_voice_runtime_postgres.py tests/integration/test_memory_postgres.py` | Final source: 31 passed, no skips, 67.87s. Before validator-order correction: 31 passed, 68.67s |
| Existing C01/C03A/C17A implementation manifests | All files OK; unchanged foundations |
| Original grounding hashes against alignment-review manifest | GROUNDING.md, Oct4 r11 and Oct7 amendment r2 unchanged |
| `git diff --check` | No whitespace errors |
| `scripts/test_env.py stop` then `status` | Empty running inventory; retained test volume |

Full-unit failures: mail tool audience, DocumentsPanel prohibited marker, MCP
migration workspace-source assessment, runtime workspace-files prohibited markers.
[Prior C17A evidence](2026-10-07-LMD-C17A-build-evidence.md) recorded all four;
affected tests/email_tools/path_areas/DocumentsPanel hashes still match the prebuild
feature-validation-source manifest. They remain unresolved, not a green full suite.

Real DB proof includes failures before transcript and after transcript before
commit (both source counts zero), exact retry, legacy missing-projection repair,
changed transcript with unchanged provider payload, index occupied by another
provider (new provider rollback), concurrent duplicates, close waiting for capture,
wrong scope, revoked login and closed session. Existing provider replay-conflict
and Voice/memory regression tests pass. Synthetic isolated fixtures only: resolved
loopback 127.0.0.1:55436, exact DB resono_vault_test. Existing global gate rejects
other DB names; inspected container mount only resono-vault-test-postgres-data,
existing PG16/pgvector compose.test.yml harness. Fixture replaces only test schema.
Container/network removed through existing stop command; volume retained.
No production DB/private history access, provider calls, package deployment or
dependency changes. Existing frozen uv package audit only.

## Evidence boundaries / next step

[Implementation manifest](2026-10-07-LMD-C03R-implementation.sha256) freezes three
runtime and two test files. Earlier source/build-ready manifests remain dated
prebuild evidence; never rewrite them to approve later code/lifecycle edits.
Original grounding unchanged. No HNSW/indexed SQL, general Chat/text model, live
revision controller, reasoning-summary/tool-causal coverage, complete-session
review, procedural learning or actual Decisions transport delivered by this slice.
Closed-history repair and new midtransaction grant-revocation locks excluded.

Contract rollback/auth/duplicate/concurrency/bounded-scope gates PASS for this pair
only. C03C retains missing full capture coverage. Register owns status. Next safe
activity is source-backed C02 indexed-query contract review, reusing existing C01
and canonical storage. No later allocation earns readiness from this result.
