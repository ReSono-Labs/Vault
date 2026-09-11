# Phase 1B Local Server Evidence

Date: 2026-08-29  
Result: PASS

## Provenance

The exact Voice donor files and hashes are recorded in
`docs/planning/11-PHASE-01-LOCAL-SERVER-CONTRACT.md`. The extracted Vault file
hashes are:

| File | SHA-256 |
|---|---|
| `app/vault_runtime/local_api/app.py` | `b822fc6bfc147d1fbc89d981bbb1801c709a60dd82f08966eaa87fb0762e5c1b` |
| `app/vault_runtime/local_api/server.py` | `efc5b7b90349622154843610dce47ddf575c1d15b80e27527d3dc4941ef3bd25` |
| `app/vault_runtime/local_api/stores.py` | `d918c816595fa853148579a8366a98329422882f3a8cffc31f316b3f3ef5aacd` |
| `app/vault_runtime/local_api/__main__.py` | `4aa0ae29e122cf51972813cb76f89a035696183d839d34e18f2db95b191a727e` |
| `pyproject.toml` | `4d3075e5f9aaeaa598932281717a4cff7ef12a40015fb74a7490a7eda6e0fcd6` |
| `uv.lock` | `4d5744d385caca0c951653337684faf436119e288c27f2a1ee87ca1d3b7bd4b3` |

## Verification

- `uv sync --extra dev` created an isolated Vault environment and installed
  donor-pinned `psycopg 3.2.3` and `pytest 8.3.4`.
- `.venv/bin/python -m pytest -q` returned `24 passed in 1.10s`.
- compilation and public package imports passed.
- prohibited-import scan returned no cloud client, service API key, R1 tunnel,
  Foundry, Hub, or package-agent reference in product code.

A disposable `postgres:16` container was bound to an ephemeral loopback port.
The proof created only the `vault_private` schema, constructed the extracted
`PostgresVaultHealthStore`, started `VaultLocalServer`, requested `/health`, and
stopped it. Result:

```json
{"status":"ok","store":{"database":"ok","databaseName":"vault","databaseUser":"vault","pgvectorVersion":null,"schemaReady":true}}
```

The disposable container was removed and a post-check found no remaining
container with the proof name. pgvector is intentionally `null` because Phase 1
does not install the Phase 3 memory schema/extension.

## Donor immutability

Before and after Phase 1:

- tracked diff fingerprint:
  `0d9a4ce77e3707940c4f3becc5ecbfb641eb50f4df975c7e971f52e14e6942da`;
- full porcelain status fingerprint:
  `c04e2a6182a1630afee7e46b6662dd2fbc5cf6c52c3267b9c9cb4750ff542332`.

The already-dirty donor was neither modified nor cleaned.
