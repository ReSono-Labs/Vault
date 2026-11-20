# Changelog

All notable changes to Vault are listed here. The version comes from
`pyproject.toml`.

## Unreleased

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
