# Public Release Hardening Evidence

Date: 2026-09-01  
Status: implemented and locally verified  
Authority: owner request; `GROUNDING.md`; Phase 5 extension contract

## Scope

- Preserve installer-controlled networking and the loopback HTTP compatibility
  bridge.
- Deny remote MCP access to private, link-local, metadata, multicast and
  reserved networks, including resolution immediately before I/O.
- Review quarantined Plugin bytes without executing package content or adding
  a Vault agent identity.
- Exclude local donor and knowledge-graph state from publication.
- Add public-facing project, security, contribution and licensing documents.
- Mark cookies `Secure` on direct HTTPS while preserving the loopback-only HTTP
  bridge.

## Rights finding

The inspected R1 donor is licensed under PolyForm Noncommercial 1.0.0 with a
required ReSono Labs notice. The repository therefore describes the current
release as source-available/noncommercial, not OSI-approved open source.
Relicensing remains conditional on a complete ownership and donor-rights audit.

## Verification

```text
Focused Python tests: 25 passed
Full Python unit suite: 180 passed
Frontend tests: 9 passed
Frontend production build: passed
Docker image build: passed
Vault container: healthy, loopback HTTPS 127.0.0.1:8765
Link bridge: healthy, loopback HTTP 127.0.0.1:8766
PostgreSQL: healthy, Compose-network only
Direct HTTPS health with generated CA: passed
Bridge HTTP health: passed
```

Existing production volumes were preserved. No factory reset, database drop,
or public-network binding was performed.

## Dashboard documentation follow-up

The public Vault User Guide and Documents dashboard were updated with plain
language explaining Plugin review, MCP destination protection, the supported
Docker host address, and a dedicated Common issues section. Vault Help now
prefers that user-facing guidance and avoids technical implementation details
unless the user asks for package-author help.
