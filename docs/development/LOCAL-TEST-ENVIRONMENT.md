# Local Test Environment

## Factory reset the manual Browser Voice test Vault

This destructive workflow targets only the guarded
`resono_vault_browser_test` database and its ignored local runtime files. It
does not touch donor projects, the pytest database, or a deployed Vault:

```bash
.venv/bin/python scripts/factory_reset_test_vault.py --confirm RESET-TEST-VAULT
.venv/bin/python scripts/internet_test_env.py start
```

The reset command stops the test harness, verifies the exact database identity,
terminates only that database's sessions, recreates it, and removes only the
test Vault's ignored data/runtime directories. It intentionally requires the
literal confirmation phrase. `.env.test` is optional, matching the main test
harness; when absent, Docker Compose uses the isolated test defaults.

Vault has one project-owned development environment:

- Python dependencies live in the ignored repository `.venv` and are locked by
  `uv.lock`;
- PostgreSQL 16 with pgvector runs in Docker Compose;
- the database listens only on `127.0.0.1:55436` by default;
- the Compose project, container, database, network and named volume are
  isolated under `resono-vault-test`; and
- tests receive the database URL only through `VAULT_TEST_DATABASE_URL`.

The default database username and password are intentionally test-only. They
must never be reused for a real Vault installation.

## Commands

From the repository root:

```text
python3 scripts/test_env.py up
python3 scripts/test_env.py status
python3 scripts/test_env.py test
python3 scripts/test_env.py test-all
python3 scripts/test_env.py stop
```

`test` runs the complete Python suite. `test-all` additionally runs Browser
Voice tests and its production build. Extra pytest arguments may follow
`test`, for example:

```text
python3 scripts/test_env.py test -q tests/integration/test_memory_postgres.py
```

`stop` removes the container and network while retaining the test database
volume. The explicit destructive reset removes the test-only volume:

```text
python3 scripts/test_env.py reset
```

To override the loopback port or test credentials, copy `.env.test.example` to
the ignored `.env.test` and edit it. The management script reads only its four
documented test database keys.

This environment is for local development and automated tests. It does not
deploy Vault to a hardware device and does not touch donor repositories.

## Verified baseline

On 2026-08-29, the project-owned environment was created and verified with:

```text
python3 scripts/test_env.py test-all -q
```

Results:

- locked `.venv`: 48 packages audited;
- Docker PostgreSQL/pgvector: healthy on `127.0.0.1:55436`;
- backend: `194 passed in 100.82s`;
- Browser Voice: `6 passed`; and
- TypeScript/Vite production build: PASS.

The database container and named volume were intentionally left running for
continued local testing. `stop` preserves the volume; `reset` explicitly
deletes only this project's test volume.
