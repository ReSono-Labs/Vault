# Phase 7 Linux Release Contract

Status: frozen candidate; entry blocked  
Authority: Grounding, Phase 7 donor inventory, R1 installer patterns

## Entry

Phase 6 and 6B anti-drift exits are complete, including desktop/mobile visual
comparison, and D-07 has an owner/licensor-approved public license/notice
decision. File presence or green unit tests do not satisfy entry.

## Outcome

A non-developer installs, launches, upgrades, backs up, restores and removes
the same standalone Vault on Linux with one ordinary installer. No ReSono Labs
service, developer toolchain or in-product Build Agent is required.

## Build boundary

- Package the existing OS-neutral runtime and exact Browser Voice build.
- Use bounded R1 patterns for closed commands and verify every artifact before
  mutation; do not copy R1 device behavior.
- Bind management to loopback and create private owner-local data/config/key directories.
- Generate the one-time setup proof locally and ensure Phase 2 consumes it.
- Give PostgreSQL/pgvector least-privilege credentials in a dedicated instance.
- Back up before upgrade and retain the prior runnable release until health verification.
- Uninstall preserves data by default and requires an exact choice before deletion.

## Required verification

Clean Linux VM install, restart, offline local use, two-version upgrade,
injected rollback, encrypted-secret survival, backup/restore, both uninstall
choices, tamper rejection, reproducible checksums, SBOM, signature verification,
no unexpected outbound traffic, donor integrity and full regression.

## Stop conditions

Stop if packaging requires hosted authority, changes product behavior, embeds a
secret, adds a third agent, imports R1 device logic, or lacks a
license-compatible public distribution path. Update `INDEX.md` and provenance
for every admitted file before continuing.
