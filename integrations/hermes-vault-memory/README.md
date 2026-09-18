# ReSono Vault memory provider for Hermes

This is a standalone Hermes `MemoryProvider`. It does not patch Hermes core and
does not make Hermes a Vault system agent.

After installation, run `resono-vault-memory-pair`. It opens Vault, where the
signed-in user selects **Connect** once. The command stores the resulting local
credential in `~/.hermes/.env`; no credential copy/paste is required.

1. Install this directory into the Python environment used by Hermes.
2. Run `resono-vault-memory-pair` and approve the connection in Vault.
3. Restart Hermes.
4. Set `RESONO_VAULT_MEMORY_URL` if Vault is not at
   `https://127.0.0.1:8765`. Pairing rewrites `RESONO_VAULT_CA_FILE` from
   Vault `GET /vault-local-ca.crt`. Pairing POSTs stay verified.
5. Select `resono-vault` as Hermes's active memory provider.

Startup memory is enabled by default and uses the same bounded, non-sensitive
profile selection as Vault Voice. Set `RESONO_VAULT_STARTUP_MEMORY=false` to
disable it while retaining query-based recall.

To disconnect cleanly, run `resono-vault-memory-pair --disconnect`. This
revokes the Vault integration, removes the local credential and runs
`hermes memory off`; Hermes's built-in `MEMORY.md`/`USER.md` memory remains.
Use `--local-only` only when Vault is unavailable or the connection was removed
elsewhere. Uninstalling the Python package afterward is optional.

Hermes receives scoped recall before turns and submits completed primary-agent
turns as proposals. Vault performs classification and reconciliation. Hermes
can correct or forget scoped memory only when those exact operations were
granted when the connection was created. Revocation stops future operations.

Non-primary Hermes contexts never submit automatic proposals. TLS verification
is never disabled.
