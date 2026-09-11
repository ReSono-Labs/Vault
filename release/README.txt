ReSono Labs Vault 0.1.0 Release Packages
=========================================

resono-labs-vault-docker-0.1.0.zip
  Recommended for most users. Contains the prebuilt Vault image, its verified
  local bridge, and a preconfigured Docker Compose application. Docker fetches
  the pinned PostgreSQL/pgvector and Nginx bridge base images during install.

resono-labs-vault-linux-x86_64-0.1.0.zip
  Native 64-bit Linux build. Does not use Docker. Includes Vault, its web UI,
  locked Python packages, and its Python runtime. Requires systemd, local
  PostgreSQL with pgvector, and bubblewrap.

SHA256SUMS
  SHA-256 checksums for verifying both ZIP files before installation.

Each ZIP contains a user-facing README with installation instructions.
