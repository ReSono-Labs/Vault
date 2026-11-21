# What Vault supports

This table covers the extension standards in this release. Anything not listed here is
not supported. Import reports skipped or invalid parts one by one, and the healthy
parts still install. After install, each part of a plugin shows one status for you:
skipped as unsupported, skipped as invalid, could not reach the server, needs a sign-in,
tools not checked yet, available but not granted to you, or ready.

## Agent Plugins 1.0.0

| Part | Supported | Notes |
|---|---|---|
| `plugin.json` (pinned 1.0.0 schema) | Yes | Validated before install |
| `skills/` | Yes | Each skill is checked on its own; a bad one is skipped with a reason |
| `mcp.json`, Streamable HTTP servers | Yes | One connection per server; nothing is granted on import |
| `mcp.json`, `stdio` servers | No | Skipped with a message; never started |
| `mcp.json`, HTTP+SSE (`sse`) servers | No | Skipped with a message; never connected |
| Vault data under `extensions.com.resonolabs.vault` | Yes | Root `vault.json` still works for existing packages |
| Other clients' `extensions.*` namespaces | Ignored | They never block an import |
| Import from ZIP or TAR | Yes | |
| Import from a folder | Yes | Only folders you were given under Settings → Folders; Vault installs the copy it checked |

## Agent Skills

| Feature | Supported | Notes |
|---|---|---|
| `SKILL.md` with YAML frontmatter | Yes | `name` follows the upstream reference validator and must match the folder |
| Progressive disclosure | Yes | List, then the selected body, then a requested file |
| Bundled files (references, scripts, assets) | Read only | Scripts can be read as files; Vault never runs them |
| Same name from two sources | Yes | Chosen by install; a name alone never picks one silently |
| Voice, Chat and Background | Yes | Same list everywhere, per grant |

## MCP

| Feature | Supported | Notes |
|---|---|---|
| Protocol 2026-07-28 | Yes | Tried first |
| Protocol 2025-11-25 | Yes | Fallback in a separate adapter, with sessions |
| Protocol 2024-11-05 (HTTP+SSE) | No | Reported as unsupported |
| Transports | Streamable HTTP | stdio and HTTP+SSE are not connected |
| Tools | Yes | Discovery with pages, exact grants per person, workspace and agent |
| Resources, prompts, sampling, elicitation, tasks | No | Vault advertises only tools |
| Input-required results | No | Reported as unsupported |
| Content types | Text, image, audio, resource link, embedded resource | Non-text parts are described to the agent |
| Structured output and `outputSchema` | Yes | Schemas resolve only references inside the same document |
| `x-mcp-header` parameters | Yes | Tools with invalid annotations are not offered |
| Streamed (SSE) answers | Yes | Size-limited while reading |
| Authorization (OAuth 2.1) | Yes | PKCE S256, resource indicators, issuer checks, refresh, revocation, scope step-up |
| Client registration | Pre-registered, Client ID Metadata Document, Dynamic Client Registration | In that order |
| Credentials | Personal by default | Shared only when the device owner shares one and grants it; never another person's |
| Hosted packages (`mcp.package.json`) | Yes | Supervised process per install, confined by Linux Landlock to its own package and data; it can still use the network |

## People and workspaces

| Rule | Behaviour |
|---|---|
| Who installs, updates and removes | The device owner |
| Private workspaces | Nobody else can list, read, grant or use what is installed there |
| Shared workspaces | Members use only what they were granted, for the agent it was granted to |
| Leaving a workspace or losing a grant | Takes effect at the next use |
| Same name in two workspaces | Two independent installs (files, data, versions, removal) |
| Safe mode | Device-wide; stops hosted processes and keeps them stopped |
| Hosted process file access | Only its own package (read), its own data folder and its workspace's files folder (read and write) and system files; enforced by the kernel |
| Hosted process resources | Each package gets a share of what Vault may use (default 25% of memory, half the CPUs at lower priority, 64 processes); over the memory or process limit it is stopped with a reason. Settings → Packages |
| Hosted process network | Standard (default): web ports, DNS, its own workspace's packages and owner-listed ports; Open: any port |
| Web interface from another computer | LAN, Tailscale or a reverse proxy work as long as the browser's address reaches Vault; other addresses go in `RESONO_VAULT_TRUSTED_ORIGINS` |
