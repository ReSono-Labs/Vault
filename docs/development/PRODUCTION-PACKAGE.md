# Production Package Operations

This is the installed Vault workflow. It does not use the test database.

## Install locally

```bash
./vault-package install
./vault-package setup
```

Open the one-time HTTPS setup URL printed by `setup`. The raw setup credential
is not printed separately. The local CA is available from the running Vault at
`/vault-local-ca.crt` for browsers that need to trust the package certificate.

## Install for the local network

```bash
./vault-package install --lan
./vault-package setup
```

The generated certificate includes the detected LAN address. PostgreSQL remains
private inside Compose even when the Vault HTTPS port is available on the LAN.

## Operate and inspect

```bash
./vault-package status
./vault-package logs
./vault-package stop
./vault-package start
```

Re-running `install` rebuilds/upgrades the image without deleting database or
private user data.

## Connect ReSono Link

The production package publishes a compatibility bridge for Link at:

```text
http://127.0.0.1:8766
```

In Link, add a **Custom HTTP/WebSocket** service (**Services → Add service**)
with local destination that address. The bridge is
host-loopback-only and forwards HTTP and WebSocket traffic to Vault's unchanged
`https://vault:8765` service. It verifies Vault's certificate with the generated
local CA; TLS verification is never disabled. Incoming forwarded host and HTTPS
scheme headers are preserved.

Set `VAULT_LINK_BRIDGE_PORT` in `.runtime/production-package.env` only when the
default host port conflicts with another loopback service. The container still
listens on port `8766` internally.

## Backup and restore

```bash
./vault-package backup
./vault-package restore .runtime/package-backups/<timestamp> \
  --confirm "RESTORE VAULT BACKUP"
```

Backups are stored under `.runtime/package-backups/`, include a hash manifest,
and are verified before restore.

## Uninstall or factory reset

```bash
./vault-package uninstall
./vault-package factory-reset --confirm "DELETE ALL VAULT DATA"
```

Uninstall removes containers/network and preserves the two production volumes.
Factory reset permanently removes those production volumes and requires the
exact confirmation phrase. It does not target the test volume.
