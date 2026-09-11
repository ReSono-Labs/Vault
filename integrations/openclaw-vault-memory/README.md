# ReSono Vault memory plugin for OpenClaw 2026.8.1+

This native memory-slot plugin keeps Vault canonical and uses only Vault's
loopback HTTP contract. It does not modify OpenClaw core or connect to Vault's
database.

After installation, run `resono-vault-memory-pair`. It opens Vault, where the
signed-in user selects **Connect** once, and writes the credential to
`~/.openclaw/.env`. Configure the plugin credential as the
`RESONO_VAULT_MEMORY_CREDENTIAL` environment reference, enable the plugin and
select `resono-vault-memory` in `plugins.slots.memory`.
Set `baseUrl` only when Vault is not at `https://127.0.0.1:8765`. Trust Vault's
local CA through the Node process trust configuration; TLS verification is not
disabled by this plugin.

`startupMemory` defaults to `true`. On the first prompt in each session, the
plugin loads the same bounded, non-sensitive startup profile used by Vault
Voice. Set it to `false` to use query-based recall only.

OpenClaw local dreaming must remain off because Vault owns classification and
ingestion. The pairing command explicitly sets `dreaming.enabled` to `false`.

To disconnect cleanly, run
`node ~/.openclaw/extensions/resono-vault-memory/pair.mjs --disconnect`. This
revokes the Vault integration, removes the local credential, restores the
`memory-core` slot and disables this plugin. Use `--local-only` only when Vault
is unavailable or the connection was removed elsewhere. Uninstalling the
disabled plugin afterward is optional.

Selecting this exclusive slot replaces OpenClaw `memory-core`. OpenClaw's
unrelated native SQLite runtime state remains unchanged.
