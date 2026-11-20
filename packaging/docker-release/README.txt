ReSono Labs Vault — Docker
================================

Requirements: Docker Engine or Docker Desktop, Docker Compose, and zstd or gzip.

Linux and macOS:
1. Open a terminal in this folder.
2. Run: ./vault install
3. Run: ./vault setup
4. Open the setup link that is shown.

Windows (Docker Desktop only; no Ubuntu or WSL steps):
1. Start Docker Desktop.
2. Open PowerShell in this folder and run:
   powershell -ExecutionPolicy Bypass -File .\vault.ps1 install
   The setup link opens in your browser.

Folders: installation makes your home folder and drives visible to Vault.
Nothing is used until you choose folders in the setup wizard or in
Settings > Folders. On macOS and Windows, a drive connected later appears after
the next start; on Linux it appears right away.

Installation automatically detects the computer's local address and prepares
Vault for both the computer and phones on the same local network before setup
begins. No setup restart is required.

Vault:  https://127.0.0.1:8765
Bridge: http://127.0.0.1:8766
A2A:    http://127.0.0.1:8768  (Agent Card; only accepts work when Agent2Agent is on)

The bridge is loopback-only. It verifies Vault's local certificate and supports
HTTP and WebSocket connections. PostgreSQL is private and is never published as
a host port. Saved data remains in named Docker volumes during updates and a
normal uninstall.

Useful commands:
  ./vault setup                show the one-time setup link again
  ./vault status
  ./vault logs
  ./vault stop
  ./vault start
  ./vault update               install a newer package from this folder
  ./vault enable-lan [address] use another local network address
  ./vault uninstall            keeps your data

When Vault data already exists, install and update first back it up to
backups/<date-time>/ in this folder.
