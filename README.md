# ReSono Labs Vault

ReSono Labs Vault is a local-first Voice and personal-data platform packaged
for direct development use and Docker-based installation. It provides local
accounts and workspaces, Browser Voice, memory, background work, Mail,
Contacts, Calendar, and owner-controlled Skills, Plugins, and MCP connections.

Vault does not require a ReSono Labs cloud account or hosted control plane.
The supported Docker package binds the main HTTPS service and compatibility
bridge to loopback by default. Network exposure, tunnels, VPNs, reverse
proxies, firewall policy, and remote DNS remain the installer's responsibility.

## Install with Docker

Prerequisites are Docker Engine or Docker Desktop with Compose support.

```bash
./vault-package install
./vault-package status
./vault-package setup
```

Open `https://127.0.0.1:8765`. The generated local certificate may require a
one-time browser trust step. Applications that cannot use the local HTTPS
certificate can use the loopback-only compatibility bridge at
`http://127.0.0.1:8766`.

See [the platform guide](docs/PLATFORM-GUIDE.md),
[Windows installation](docs/WINDOWS-INSTALLATION.md), and
[production package documentation](docs/development/PRODUCTION-PACKAGE.md).

## Development

Python 3.11 or newer, Node.js/npm, Docker, and `uv` are used by the development
workflow. Tests use a separate, allowlisted PostgreSQL database and must never
be pointed at installed Vault data.

```bash
uv sync --dev
npm --prefix frontend ci
./scripts/test_env.py start
./scripts/test_env.py test
```

## Security model

- Local listeners bind to loopback by default.
- Non-loopback API binding requires TLS.
- Local account sessions, CSRF protection, workspace authorization, encrypted
  extension credentials, extension safe mode, and explicit capability grants
  remain authoritative regardless of network transport.
- Plugin archives are quarantined and reviewed without executing package code.
- Remote MCP endpoints are revalidated before I/O and cannot target private,
  link-local, metadata, multicast, or reserved networks. Explicit loopback MCP
  endpoints remain supported for locally installed integrations.
- Plugin content never creates another Vault agent. Vault contains exactly the
  fixed Voice Agent and Background Agent.

Report vulnerabilities according to [SECURITY.md](SECURITY.md).

## License and provenance

This repository is currently distributed under the PolyForm Noncommercial
License 1.0.0 terms recorded in [LICENSE.md](LICENSE.md). That is a
source-available, noncommercial license rather than an OSI-approved open-source
license. Do not relabel or redistribute it under a permissive license until the
rights to every donor-derived portion have been verified.

Architecture, donor provenance, current limitations, and verification evidence
are maintained under `docs/`.
