# ReSono Labs Vault Plugin Kit

Build capabilities for Vault using Agent Plugins, Agent Skills and MCP without
changing Vault itself.

## Quick start

Requires Python 3.11 or newer for the offline kit command.

```bash
python -m cli.vault_plugin new my-plugin --language python
cd my-plugin
python ../cli/vault_plugin.py validate .
python ../cli/vault_plugin.py inspect .
python ../cli/vault_plugin.py package .
```

Choose `--language typescript` for the TypeScript starter. The generated ZIP is
ready for Vault's **Plugins** page. Installation never grants a tool
automatically; the Vault owner chooses whether Voice, Background Agent, or both
may use it.

The SDK folders are optional helpers. Any conforming Streamable HTTP MCP server
can be used. Vault does not load plugin Python or JavaScript into its own
process.

See the in-product **Vault Plugin Kit** document for the complete guide.
