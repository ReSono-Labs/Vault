# Production Package Evidence — 2026-08-29

## Verified package

- Multi-stage production image built successfully.
- Compose package initialized `vault` as a private PostgreSQL database owned by
  `vault_runtime` with pgvector `0.8.6`.
- Vault ran non-root, healthy, with all Linux capabilities dropped and
  `no-new-privileges` enabled.
- LAN TLS health passed at `https://192.168.1.170:8765`.
- `/vault-local-ca.crt` returned the generated package CA.
- Production volumes were exactly `resono-vault-data` and
  `resono-vault-postgres-data`; the test volume remained separate.

## Lifecycle evidence

- A disposable master onboarding created exactly one owner and one private
  workspace with both user and workspace key files.
- The disposable package was removed with the exact confirmed factory-reset
  workflow and reinstalled cleanly.
- The current installed package is at clean first run with zero active users.
- A package backup completed with a PostgreSQL custom dump, data archive and
  SHA-256 manifest.
- Verified restore completed and returned to healthy state.
- An image rebuild/reinstall preserved the setup state and production volumes.

## Regression evidence

- Final backend suite after per-user vector composition: `226 passed in 134.90s`.
- Browser Voice suite: `9 passed`.
- Production TypeScript/Vite build: passed.
- The pytest database guard accepts only `resono_vault_test` and refuses manual
  or production database names.
- User/workspace storage tests prove private modes, separate key material,
  atomic provisioning, identity-metadata validation, symlink rejection,
  deletion cleanup and interrupted-commit reconciliation.

## Packaged memory-vector evidence

- The exact provider behavior was ported from R1
  `runtime/resono_runtime/providers/openai/embeddings.py` and credential access
  from `runtime/resono_runtime/memory/embedding_access.py`.
- The package schema creates pgvector and stores every embedding in a real
  `vector` column while retaining JSON only for donor-compatible readback.
- Integration proof stores a scoped memory through the real pipeline and
  verifies PostgreSQL `vector_dims(embedding)` equals the provider dimensions.
- Provider resolution is per user/workspace and honors Vault's encrypted
  shared-or-individual access policy.
- New Voice memories embed during ingestion. Startup and pre-search backfill
  repair missing vectors without inventing a fallback vector.
- Provider absence or failure leaves lexical memory operational and records
  the absence honestly; it never creates hash, random or keyword embeddings.
- The memory reviewer remains a model-backed capability hosted by the fixed
  Background Agent. No third system-agent identity was created.

## Security limitation retained fail-closed

The host Bubblewrap probe passes. A Bubblewrap probe inside the unprivileged
Docker container fails because nested namespace creation is denied. Relaxing
seccomp or AppArmor individually did not fix it. Disabling both made the probe
run but was rejected because it removes two outer container security layers;
privileged/SYS_ADMIN/Docker-socket workarounds were likewise rejected. Imported
executable capabilities therefore fail closed; the package never falls back to
unsandboxed process execution.
