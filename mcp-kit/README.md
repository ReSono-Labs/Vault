# Vault MCP Package Kit

Developer-facing schemas, CLI, and starters for **hosted MCP packages**. User-facing guide: [docs/VAULT-MCP-PACKAGE-KIT.md](../docs/VAULT-MCP-PACKAGE-KIT.md).

## CLI

From the repository root (requires `jsonschema`; the CLI also reads the shared
schemas in `plugin-kit/schemas/`):

```bash
python3 mcp-kit/cli/vault_mcp.py new my.package        # creates ./my.package (--destination DIR to change the parent)
python3 mcp-kit/cli/vault_mcp.py validate mcp-kit/starters/starter.example
python3 mcp-kit/cli/vault_mcp.py inspect mcp-kit/starters/starter.example
python3 mcp-kit/cli/vault_mcp.py package mcp-kit/starters/starter.example --output starter.example.zip
```

The MCP Package Kit is used from this repository; it is not part of the image
downloads.

The package directory name must match `mcp.package.json` → `name`.

Cutover packages may include a `migration/` tree and `migration` block in the manifest. Vault hydrates SQLite and workspace files into `extensions/data/{name}/` on import — see the main kit doc.

## Docker note

Hosted MCP subprocesses run **inside the Vault container** on `127.0.0.1`. They do not use `host.docker.internal`. Supervised packages bind to the allocated `VAULT_MCP_PORT` injected at start.

## Starter

See [starters/starter.example/](starters/starter.example/). Stdlib reference server; production packages should add `requirements.txt` and use the official MCP SDK — see the main kit doc.
