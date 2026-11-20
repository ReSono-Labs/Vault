# Production package from source

`./vault-package` (a wrapper for `scripts/vault_package.py`) builds and runs Vault
from this checkout with `Dockerfile` and `compose.yml`. It never uses the test
database. The distribution packages under `packaging/` are covered at the end.

## What runs

`compose.yml` (project `resono-vault`):

| Service | Purpose | Host port |
|---|---|---|
| `initialize` | One-shot: creates the data root, secrets and certificates, then exits | none |
| `postgres` | PostgreSQL 16 with pgvector, database `vault` | none (private to Compose) |
| `vault` | The Vault process | `8765` (HTTPS; loopback, or all addresses in LAN mode), `127.0.0.1:8768` (A2A), `127.0.0.1:8790-8810` (MCP package ports) |
| `link_bridge` | nginx compatibility bridge to `https://vault:8765` | `127.0.0.1:8766` |

Data lives in two named volumes, `resono-vault-data` and
`resono-vault-postgres-data`. The `vault` container drops all Linux capabilities
and is limited to 3 CPUs and 6 GB of memory.

## Install

The image bundles the local embedding runtime from `packaging/local-embeddings/`,
which is not in git. When it is missing, `install` stages it from a local
[Ollama](https://ollama.com/download) installation (pulling `embeddinggemma:300m`
if needed) with `scripts/stage_local_embeddings.py`. Install Ollama before the
first install from a fresh clone.

```bash
./vault-package install          # loopback only
./vault-package install --lan    # also reachable on the local network
./vault-package setup            # prints the one-time setup link
```

`install` writes `.runtime/production-package.env` (bind address, TLS hosts,
port) and `.runtime/compose.folders.yml` (your home folder and drives, made
visible to Vault). Then it builds the image and starts the services. Nothing in
those folders is used until access is given in setup or **Settings → Folders**.
In LAN mode the certificate includes the detected LAN address. PostgreSQL stays
private either way.

Running `install` again rebuilds and upgrades the image and keeps all data. It
does not take a backup first, so run `backup` before an upgrade you may want to
undo.

## Operate

```bash
./vault-package status
./vault-package logs     # last 200 lines of vault, link_bridge and postgres
./vault-package stop
./vault-package start
```

The local CA is served at `https://127.0.0.1:8765/vault-local-ca.crt` for
browsers that need to trust it.

## Link bridge

ReSono Labs Link connects through `http://127.0.0.1:8766`: in Link, add a
**Custom HTTP/WebSocket** service with that address. The bridge listens on host
loopback only, forwards HTTP and WebSocket traffic to Vault, and verifies Vault's
certificate with the local CA.

To use another host port, set `VAULT_LINK_BRIDGE_PORT` in your shell when you run
`./vault-package start`. Do not put it in `.runtime/production-package.env`:
`install` rewrites that file.

## Backup and restore

```bash
./vault-package backup
./vault-package restore .runtime/package-backups/<timestamp> --confirm "RESTORE VAULT BACKUP"
```

`backup` writes `vault.dump` (the database), `vault-data.tar.gz` (keys, private
files, extensions and configuration, without the database URL and API token) and
`manifest.json` with SHA-256 hashes and the schema version.

`restore` checks the hashes and refuses a backup from a newer schema than this
code ships. It replaces the data and database, then runs `reconcile-restore`:
work that was in flight is cancelled and routines are paused, so nothing runs
twice.

## Uninstall and factory reset

```bash
./vault-package uninstall                                          # keeps both data volumes
./vault-package uninstall --delete-data --confirm "DELETE ALL VAULT DATA"
./vault-package factory-reset --confirm "DELETE ALL VAULT DATA"    # deletes both data volumes
```

The confirmation phrases are exact. These commands never touch the test volume.

## Distribution packages

`scripts/release/build_artifacts.py [--version X]` turns an existing
`resono-labs-vault:local` image into release archives in the untracked `release/`
folder, with a `SHA256SUMS` file. It needs Docker and zstd. The version comes from
`pyproject.toml`.

- **Docker package** (`packaging/docker-release/`): a prebuilt image, `compose.yml`,
  and the `vault` (Linux, macOS) and `vault.ps1` (Windows) scripts with
  `install`, `update`, `setup`, `enable-lan`, `start`, `stop`, `status`, `logs` and
  `uninstall`. `install` and `update` back up existing data to `backups/<time>/`
  first. LAN mode is on by default.
- **Native Linux package** (`packaging/linux-release/`): a systemd service with data
  in `/var/lib/resono-vault`. It uses the local PostgreSQL with pgvector.
