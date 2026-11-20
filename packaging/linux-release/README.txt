ReSono Labs Vault — Native Linux (x86_64)
================================================

This package runs Vault directly as a Linux system service. Docker is not used.

Supported base: 64-bit Debian 12 or a compatible Linux distribution.

Before installing, provide:
  - systemd and runuser
  - PostgreSQL running locally, with psql
  - the pgvector extension for that PostgreSQL version
  - bubblewrap (bwrap); the installer checks for it

Install from your own account (not a root login):
  sudo ./install.sh
  resono-vault setup

Vault runs as your account, so files it writes in your folders belong to you.
Your home folder and drives become visible to Vault; nothing is used until you
choose folders in the setup wizard or in Settings > Folders.

Open the one-time setup link that is shown. Vault listens only on:
  https://127.0.0.1:8765

Useful commands:
  resono-vault setup
  resono-vault status
  resono-vault logs
  sudo resono-vault start
  sudo resono-vault stop
  sudo resono-vault restart

Vault data is stored in /var/lib/resono-vault. The application is installed in
/opt/resono-vault. Existing Vault data is preserved when this package is
installed again.
