# Phase 10 M3 Hermes Adapter Evidence

Date: 2026-08-31  
Status: standalone package built; live-session acceptance remains open

## Donor boundary

The pinned Hermes checkout remains read-only at commit
`41447a6d7063b2772b0c2f26a5b22d9bd444fb43`. The adapter follows its documented
standalone `MemoryProvider` entry-point contract and does not patch Hermes core.

## Delivered

- pip-discoverable `hermes_agent.memory_providers` entry point;
- native `MemoryProvider` lifecycle and setup schema;
- profile-scoped Hermes secret resolution;
- TLS verification with optional private-CA file;
- scoped recall/prefetch and deterministic recall status;
- nonblocking completed-turn proposal submission;
- automatic proposal writes disabled outside the primary Hermes context;
- explicit search, granted correction and granted forget tools; and
- no database access or client-selected Vault scope.

Package source is `integrations/hermes-vault-memory/`. Its wheel contains the
provider module, `plugin.yaml` and the `resono-vault` entry point.

## Verification

```text
Hermes provider unit tests: 2 passed
Python compilation: passed
sdist and wheel build: passed
wheel content and entry point inspection: passed
```

Current wheel SHA-256:
`d2d2f13a9b0c6096d0d78b15baeb6d09680504ed56b4b4d5fa82d3ff3018167e`.

## Remaining M3 exit proof

The package has not been installed into the user's Hermes environment and no
live Vault credential has been copied into Hermes. Therefore a real Hermes
session recall/proposal trace is not claimed. Installation is a separate
environment mutation and is unnecessary until the owner chooses to activate
the integration.
