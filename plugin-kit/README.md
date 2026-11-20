# ReSono Labs Vault Plugin Kit

Build capabilities for Vault using Agent Plugins, Agent Skills and MCP without
changing Vault itself.

## Quick start

Requires Python 3.11 or newer and the `jsonschema` package. Run the commands from
the `plugin-kit/` folder:

```bash
cd plugin-kit
python -m cli.vault_plugin new my-plugin --language python   # creates plugin-kit/my-plugin
cd my-plugin
python ../cli/vault_plugin.py validate .
python ../cli/vault_plugin.py inspect .
python ../cli/vault_plugin.py package .
```

Use `--destination DIR` to create the plugin somewhere else.

Choose `--language typescript` for the TypeScript starter. The generated ZIP is
ready for Vault's **Plugins** page. Installation never grants a tool
automatically; the user chooses whether Voice, the Background Agent, or both
may use it.

Vault-specific data goes under `extensions["com.resonolabs.vault"]` in
`plugin.json` and a `com.resonolabs.vault/` folder; a root `vault.json` is still
accepted for existing packages. `validate` checks `plugin.json`, every skill and
`mcp.json` with the same rules Vault uses at import.

The SDK folders are optional helpers. Any conforming Streamable HTTP MCP server
can be used. Vault does not load plugin Python or JavaScript into its own
process.

The complete guide is [docs/VAULT-PLUGIN-KIT.md](../docs/VAULT-PLUGIN-KIT.md). It
also ships inside the kit download as `GUIDE.md`. The image build replaces
`schemas/plugin.schema.json` with the copy in
`app/vault_runtime/extensions/standards/`, so change the schema there.
