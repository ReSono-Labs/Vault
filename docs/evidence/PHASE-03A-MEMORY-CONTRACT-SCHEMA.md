# Phase 3A Memory Contract and Schema Evidence

Date: 2026-08-29  
Status: PASS — bounded slice only; Phase 3 remains open

## Scope proved

- Frozen Voice/R1 memory merge contract.
- Exact R1 reviewer contract v2 label validation.
- PostgreSQL translation of the eight admitted Phase 3 relations.
- Phase 2 local user/workspace foreign-key boundary.
- No document relation, cloud identity, routing feature or agent identity.

## Unit proof

Command:

```text
.venv/bin/pytest -q tests/unit
```

Result:

```text
46 passed in 3.02s
```

The added tests reject unknown domain, type, authority, confidence,
sensitivity, intent and visibility values and verify normalized candidates
retain the exact admitted names.

## Real PostgreSQL proof

A disposable `postgres:16-alpine` instance was bound to loopback only. The
existing Phase 2 identity schema was installed first, followed by
`ensure_memory_schema`.

Observed result:

```text
phase3_relations 8
fingerprint_recorded True
```

The disposable container `resono-vault-phase3-schema` was then stopped and
removed by its `--rm` lifecycle.

## Anti-drift review

- Primary structure remains Voice Vault under `app/vault_runtime/`.
- R1 names/lifecycle are a required merge, not a second SQLite store.
- There is no reviewer-agent registration. Review remains a capability of the
  two fixed system-agent paths.
- There is no Build Agent.
- Shared external memory, Browser Voice, Link/Tailscale and document storage
  remain outside this slice.
- Donor repositories were read only.

## Remaining Phase 3 work

Repository operations, reconciliation, evidence redaction, ingestion,
two-step actions, retrieval, embeddings and complete scope/security tests are
not proved by this slice and must not be described as complete.
