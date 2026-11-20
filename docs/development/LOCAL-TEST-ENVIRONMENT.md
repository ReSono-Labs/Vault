# Local test environment

Tests run against an isolated PostgreSQL database in Docker. They never use an
installed Vault's database.

## Requirements

- Docker with Compose
- [uv](https://docs.astral.sh/uv/) (CI uses 0.8.14) and Python 3.12. The image
  and CI use 3.12. `pyproject.toml` allows 3.11 or newer.
- Node.js 22 and npm, for the web app

## The test database

`compose.test.yml` runs PostgreSQL 16 with pgvector:

- container `resono-vault-test-postgres`, volume `resono-vault-test-postgres-data`;
- listening only on `127.0.0.1:55436`;
- database `resono_vault_test`, user `vault_test`. The password is test-only and
  must never be reused for a real installation.

`tests/conftest.py` refuses to start pytest when `VAULT_TEST_DATABASE_URL` points
anywhere else: it accepts exactly
`postgresql://vault_test:<password>@127.0.0.1:55436/resono_vault_test`. You can
change the password in `.env.test` (copy `.env.test.example`). The host, port,
user and database name are fixed.

## Commands

Run these from the repository root:

```bash
python3 scripts/test_env.py up        # uv sync --extra dev, start the database
python3 scripts/test_env.py test      # the whole Python suite (default -q)
python3 scripts/test_env.py test -q tests/unit/test_folders.py   # extra arguments go to pytest
npm --prefix frontend ci              # once, before test-all
python3 scripts/test_env.py test-all  # Python suite, then frontend tests and build
python3 scripts/test_env.py status
python3 scripts/test_env.py stop      # stop the container, keep the volume
python3 scripts/test_env.py reset     # delete the test volume
```

`test` sets `VAULT_TEST_DATABASE_URL` and holds `.runtime/test-database.lock`
while pytest runs. Integration fixtures drop and recreate the schema, so two
runs at the same time would break each other. Runs are serial by design.

Frontend checks on their own (what CI runs):

```bash
cd frontend
npx tsc --noEmit
npx vitest run
npm run build
```

## How the suite is organised

- `tests/unit/` needs no database.
- `tests/integration/` needs the test database. Everything there is marked
  `integration` automatically, so `-m "not integration"` runs the unit tests only.
  Without `VAULT_TEST_DATABASE_URL` the integration tests are skipped, unless
  `VAULT_REQUIRE_INTEGRATION=1` is set (as in CI), which makes a missing database
  an error.
- `tests/support/` holds shared helpers. Test modules never import each other.
- The `mounted` fixture (`tests/integration/conftest.py`) builds the real
  production composition with every production switch on. A test that needs a
  switch off says why with `@pytest.mark.flags_off("reason")`.

## Guard tests

Some tests fail on purpose when a change has wider effects than intended:

- **API routes:** `tests/integration/test_local_api_routes_postgres.py` compares
  every route and its responses with `tests/integration/snapshots/local_api_routes.json`.
  When you change the API on purpose, regenerate the snapshot and review the diff:

  ```bash
  UPDATE_ROUTE_SNAPSHOTS=1 python3 scripts/test_env.py test tests/integration/test_local_api_routes_postgres.py
  ```

- **Migrations:** `test_migrations_runner_postgres.py` checks order, recorded
  checksums, refusal of changed or unknown migrations, and the frozen baseline.
- **Public tree:** `python3 scripts/check_public_tree.py` fails when a tracked file
  contains an absolute local path or a maintainer-only folder is tracked.

## Adapter tests

```bash
cd integrations/hermes-vault-memory
PYTHONPATH=src uv run --frozen --extra dev --project ../.. python -m pytest -q tests
```

`test_pairing_ca.py` runs anywhere. `test_provider.py` imports a Hermes agent
checkout from `HERMES_DONOR_PATH` (default `~/.hermes/hermes-agent`), so CI runs
only `test_pairing_ca.py`. The OpenClaw adapter has no automated tests.

## A test Vault for manual browser testing

`scripts/internet_test_env.py` runs Vault from source against a separate database,
`resono_vault_browser_test`, in the same test container. See
[INTERNET-CONNECTIVITY-TESTING.md](INTERNET-CONNECTIVITY-TESTING.md). To start that
test Vault from scratch:

```bash
python3 scripts/factory_reset_test_vault.py --confirm RESET-TEST-VAULT
python3 scripts/internet_test_env.py start
```

The reset stops the harness, recreates only `resono_vault_browser_test`, and
deletes `.runtime/internet-test/`, including its credentials and certificates. It
does not touch the pytest database or an installed Vault.
