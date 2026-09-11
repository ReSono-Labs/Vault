ReSono Labs Vault — Native Linux (x86_64)
================================================

This package runs Vault directly as a Linux system service. Docker is not used.

Supported base: 64-bit Debian 12 or a compatible Linux distribution.

Before installing, provide:
  - systemd
  - PostgreSQL running locally
  - the pgvector extension for that PostgreSQL version
  - bubblewrap for sandboxed third-party capabilities

Install:
  sudo ./install.sh
  resono-vault setup

Open the one-time setup link that is shown. Vault listens only on:
  https://127.0.0.1:8765

Useful commands:
  resono-vault status
  resono-vault logs
  sudo resono-vault restart

Vault data is stored in /var/lib/resono-vault. The application is installed in
/opt/resono-vault. Existing Vault data is preserved when this package is
installed again.
