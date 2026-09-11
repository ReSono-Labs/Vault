ReSono Labs Vault — Docker
================================

Requirements: Docker Engine or Docker Desktop, Docker Compose, and zstd or gzip.

1. Open a terminal in this folder.
2. Run: ./vault install
3. Run: ./vault setup
4. Open the setup link that is shown.

Installation automatically detects the computer's local address and prepares
Vault for both the computer and phones on the same local network before setup
begins. No setup restart is required.

Vault:  https://127.0.0.1:8765
Bridge: http://127.0.0.1:8766

The bridge is loopback-only. It verifies Vault's local certificate and supports
HTTP and WebSocket connections. PostgreSQL is private and is never published as
a host port. Saved data remains in named Docker volumes during updates and a
normal uninstall.

Useful commands:
  ./vault status
  ./vault logs
  ./vault stop
  ./vault start
  ./vault update
  ./vault uninstall
