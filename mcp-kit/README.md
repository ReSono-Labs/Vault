# Vault MCP Package Kit

Developer-facing schemas, CLI, and starters for **hosted MCP packages**. User-facing guide: [docs/VAULT-MCP-PACKAGE-KIT.md](../docs/VAULT-MCP-PACKAGE-KIT.md).

## CLI

From the repository root (requires `jsonschema`):

```bash
python3 mcp-kit/cli/vault_mcp.py new my.package
python3 mcp-kit/cli/vault_mcp.py validate mcp-kit/starters/starter.example
python3 mcp-kit/cli/vault_mcp.py package mcp-kit/starters/starter.example --output /tmp/starter.example.zip
python3 mcp-kit/cli/vault_mcp.py inspect mcp-kit/starters/starter.example
python3 mcp-kit/cli/vault_mcp.py package mcp-kit/starters/starter.example --output /tmp/my.package.zip
```

The package directory name must match `mcp.package.json` → `name`.

Cutover packages may include a `migration/` tree and `migration` block in the manifest. Vault hydrates SQLite and workspace files into `extensions/data/{name}/` on import — see the main kit doc.

## Docker note

Hosted MCP subprocesses run **inside the Vault container** on `127.0.0.1`. They do not use `host.docker.internal`. Supervised packages bind to the allocated `VAULT_MCP_PORT` injected at start.

## Starter

See [starters/starter.example/](starters/starter.example/). Stdlib reference server; production packages (Business, CRM) should add `requirements.txt` and use the official MCP SDK — see the main kit doc.
