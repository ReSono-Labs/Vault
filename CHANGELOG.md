# Changelog

All notable changes to Vault are listed here. The version comes from
`pyproject.toml`.

## Unreleased

### Link

- **Link Front Door v1.** Link's engine can run Vault owner chat over its standard agent
  contract (`/v1/responses` plus `/link/v1` capabilities, approvals and drafts), beside the
  existing companion chat routes. Vault cards arrive as Link Cards v1. Steer, streaming and
  the voice tunnel are reported unsupported; phone voice keeps working as before.

### Extensions

- **Agent Skills:** new skills need a valid `name` matching their folder (the
  upstream reference validator's rules); existing installs keep loading as
  legacy. Agents can read a skill's bundled files, choose between skills with the
  same name, and see the same skill list in Voice, Chat and Background.
- **Agent Plugins:** Vault package data can live under the `com.resonolabs.vault`
  namespace (root `vault.json` still works); other clients' namespaces no longer
  reject a plugin; stdio and SSE servers are skipped with a message; header and
  server names are checked; the kit validates packages the same way Vault does.
- **Per-workspace storage:** the same extension name can be installed in several
  workspaces as independent installs (files, data, versions and removal are per
  workspace). Existing installs are moved into the new layout at startup; an old
  folder two workspaces shared stays in place and stays blocked until the owner
  reinstalls one.
- **Link tools:** discovery reads every page and backs off when nothing changes.
- **MCP 2026-07-28:** Vault speaks the current MCP revision (per-request metadata,
  `server/discover`, the required request headers and `x-mcp-header` parameters) and
  falls back to `2025-11-25` for older servers, kept in a separate adapter. Calls go to
  the address that passed the network check, answers are size-limited while they
  stream, and SSE answers are read. Timeouts, refused credentials, unreachable servers
  and server errors get distinct messages; a timed-out call is never repeated. A tool's
  own error is returned even when it declares an output schema, and images, audio and
  resources are described instead of dropped. Both starters now run a server that
  speaks both revisions, and both pass against the official MCP Python SDK client.
- **MCP sign-in and personal accounts:** Vault implements the MCP authorization flow
  (OAuth 2.1 with PKCE, protected resource and authorization server discovery, the
  `resource` indicator, issuer checks, registration, refresh, revocation, scope
  step-up), tested against the official MCP Python SDK's authorization server.
  Credentials for remote MCP connections are now personal: a tool runs with the
  caller's own account, a shared account exists only when the device owner shares one
  and grants it, and nobody's call falls back to another person's account. Tokens
  saved before this release become the personal token of whoever saved them.
- **Docs:** hosted executable plugins are described as trusted code with Vault's
  access until OS confinement exists.

### Security

- **MCP tool schemas are checked offline.** A schema from an MCP server or
  package may only use references inside itself (`#/$defs/...`). Discovery
  refuses a tool whose schema points at another document (http, https, file or
  any other URI), and Vault never fetches such a reference while validating.
- **Failed upgrades and removals keep shared data.** If installing an update to
  a plugin or hosted MCP package fails, its previous files and data are restored
  byte for byte. Removing an extension deletes its data folder only when no
  other install with the same name, of any kind and in any workspace, still uses
  it. Removing a hosted MCP package now deletes both its current and previous
  versions.
- **Safe mode stops supervised processes.** Turning safe mode on now stops every
  hosted MCP package and supervised plugin process, with its child processes,
  and nothing starts again (install, enable, boot or restart) until the device
  owner turns it off. The safe mode responses now include `"scope": "device"`.
- **One workspace per extension name, for now.** Extension files and data are
  still stored by name for the whole device, so Vault refuses to install a
  skill, plugin or MCP package whose name another workspace already uses. If
  existing installs in different workspaces already share a name, Vault finds
  them at startup, keeps their files, and blocks every use of them until the
  device owner removes one and reinstalls the other. `GET /extensions/runtime`
  lists the blocked names in `storageConflicts` (device owner only).

## 0.1.0 — first public release (not yet published)

The first public version of Vault, a local-first personal data platform for voice
and text agents.

### Conversations and agents

- **Voice** in the browser with OpenAI Realtime, Gemini Live and xAI, and on the
  ReSono Labs Link phone app.
- **Chat** with history, attachments, streaming replies and display cards.
- **Coordinator.** Chat saves reminders, follow-ups and routines, keeps a list of
  open work, and wakes itself in the same chat to report results. Voice hands
  longer requests to it.
- **Background Agent.** Durable, resumable work with admission limits, visible
  progress and user-created specialists.
- **One-step approvals.** A direct request gets one approval card in the
  browser or on the Link phone. There is no second spoken confirmation.

### Memory

- **Live memory and live tool routing.** Proposals appear while you speak or
  type, backed by local EmbeddingGemma vectors and a pgvector HNSW index.
- **Memory review** after each conversation extracts facts, preferences,
  decisions and corrections with evidence. Forgotten facts are not relearned.
- **Learned procedures.** Only qualified, read-only rules are activated.

### Data and tools

- **Personal data:** Mail (IMAP plus an assistant mailbox), Calendar (CalDAV,
  ICS), Contacts, Tasks, workspace files, and host folders shared per user.
- **Built-in plugins:** weather, markets, news, local events, and web search with
  required citations.
- **Command-line tools** for agents, confined to the user's folder with Landlock
  and approved per run.

### Extensions and integrations

- **Extensions.** Import Agent Skills, Agent Plugins, hosted MCP packages and
  remote MCP connections. Every import is reviewed in quarantine, and grants are
  explicit and per workspace.
- **Agent2Agent 1.0** in both directions.
- **Shared memory** for Hermes and OpenClaw through pairing adapters.
- **Developer kits:** the Plugin Kit and the MCP Package Kit.
- **Vault Help** answers from the guides, the developer docs and the source.

### Accounts, security and packaging

- **Accounts.** Local accounts and workspaces with a permanent master account.
  Data is private by default.
- **Security.** Encrypted credentials, CSRF protection, loopback-first listeners,
  and TLS for any network listener.
- **Packaging.**
  - Docker package (Linux, macOS, Windows) with LAN mode.
  - Backup, verified restore, factory reset and uninstall.
  - Native Linux systemd package.
- **Schema.** Numbered, checksummed migrations starting from one baseline.

### Known limits

- Hosted MCP packages are not yet confined by an OS-level sandbox.
- Live transcription and the Decisions API need an OpenAI API key.
- See [known gaps](docs/development/ARCHITECTURE.md#known-gaps).
