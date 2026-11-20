# Vault documentation

## User guides

These seven guides ship in the image. The **Guides** page serves them and Vault
Help reads them first.

- [PLATFORM-GUIDE.md](PLATFORM-GUIDE.md): the user and administrator manual.
  Installation, accounts, sharing, connections, agents, memory, extensions,
  backup, removal and current limits. Its **Common issues** section covers
  Plugin and Skill imports, MCP address warnings, missing capabilities, local
  bridge sign-in and package startup problems.
- [WINDOWS-INSTALLATION.md](WINDOWS-INSTALLATION.md): install and run Vault on
  Windows with Docker Desktop and WSL 2.
- [RESONO-LABS-LINK.md](RESONO-LABS-LINK.md): add a ReSono Labs Link Custom
  HTTP/WebSocket service that targets the local Vault bridge.
- [LOCAL-CONNECTION-BRIDGE.md](LOCAL-CONNECTION-BRIDGE.md): the optional local
  HTTP/WebSocket compatibility bridge and when to use it.
- [HERMES-OPENCLAW-MEMORY.md](HERMES-OPENCLAW-MEMORY.md): install and pair the
  Hermes/OpenClaw memory adapters.
- [VAULT-PLUGIN-KIT.md](VAULT-PLUGIN-KIT.md): build and validate Agent Plugin
  packages, including `vault.json` migration.
- [VAULT-MCP-PACKAGE-KIT.md](VAULT-MCP-PACKAGE-KIT.md): build and validate
  hosted MCP packages (`mcp.package.json`).

## Developer documentation

Start with the architecture document, then the contributing guide.

- [development/ARCHITECTURE.md](development/ARCHITECTURE.md): how Vault is built.
  It covers the repository map, startup, request path, agents, tools, approvals,
  the background engine, memory, data and migrations, extensions, configuration,
  the rules that keep Vault consistent, and known gaps.
- [../CONTRIBUTING.md](../CONTRIBUTING.md): workflow, checks and rules for changes.
- [development/LOCAL-TEST-ENVIRONMENT.md](development/LOCAL-TEST-ENVIRONMENT.md):
  the isolated test database, test commands, guard tests and the manual test Vault.
- [development/PRODUCTION-PACKAGE.md](development/PRODUCTION-PACKAGE.md): building
  and running the package from source, backup and restore, and the distribution
  packages.
- [development/INTERNET-CONNECTIVITY-TESTING.md](development/INTERNET-CONNECTIVITY-TESTING.md):
  testing a disposable Vault over the internet through an authenticated tunnel.
- Kits and adapters have their own READMEs: [plugin-kit](../plugin-kit/README.md),
  [mcp-kit](../mcp-kit/README.md), [Hermes](../integrations/hermes-vault-memory/README.md),
  [OpenClaw](../integrations/openclaw-vault-memory/README.md).

Vault Help reads this file and `development/`, along with the user guides and the
`app/` source.
