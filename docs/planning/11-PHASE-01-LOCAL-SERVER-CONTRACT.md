# Phase 1 Local Server Contract

Status: accepted extraction slice 1B

## Donor evidence

Primary donor root:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/`

| File | SHA-256 | Extracted behavior |
|---|---|---|
| `app/vault_runtime/local_api/app.py` | `afd7518c93c55e56a0aac0e6a00c981f49663a7ec1c60c4786634a6f6598f5f7` | `LocalApiResponse`, `/health`, store health projection, not-found response |
| `app/vault_runtime/local_api/server.py` | `b810fa11b5dbb3f91306fbf0b8678f19040f56e39fce043d371abd80cd78479f` | threaded HTTP server, request-size guard, JSON response handler, logging |
| `tests/unit/test_vault_runtime_local_api.py` | `198cec72b58ad5ce6c2536528f7383bfcfad10199359a283c97c775ab96ba6b0` | support-safe health contract and HTTP-handler behavior |

## Cut decision

The donor app and server cannot be copied whole in Phase 1: they directly
construct Postgres, hosted platform/provider clients, notification/external-AI
sidecars, Browser media, deferred R1 tunnel, and package-agent paths. This slice
extracts only the exact foundation behavior above. It does not approximate or
replace any later endpoint.

The only added lifecycle behavior is a bounded wrapper around donor
`ThreadingHTTPServer`: start in a daemon thread, expose the actual bound address,
and perform `shutdown`, `server_close`, and thread join. This is required by the
frozen deterministic start/stop exit gate.

## Acceptance

- loopback bind comes only from validated `VaultLocalApiConfig`;
- `GET /health` returns status and store health without secrets;
- unknown routes return JSON 404;
- oversized bodies return JSON 413 without application dispatch;
- responses use `Cache-Control: no-store`;
- stop releases the bound port and is idempotent;
- no cloud, tunnel, extension, agent, provider, or datastore implementation is
  imported by the slice.

## Local datastore health closure

Voice `app/vault_runtime/local_store.py` supplies the PostgreSQL health query
and proves PostgreSQL/pgvector is the existing Vault datastore architecture.
Phase 1 extracts that query behind `PostgresVaultHealthStore`; it does not port
the donor file's package-agent, Foundry, autonomy, email, or later-phase data
methods. The dependency pin `psycopg[binary]==3.2.3` is copied from the Voice
donor `pyproject.toml`. Schema creation remains Phase 2/3 work.
