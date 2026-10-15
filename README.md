# ReSono Labs Vault

**Your AI, your data, your machine.** Vault is a local-first personal data platform
for every AI you use. It runs on your own hardware and holds your memory, mail,
calendar, contacts, files and tools. It gives voice and text agents fast, private,
permissioned access to them, whichever model provider you choose.

Cloud assistants make you choose between capability and privacy. Vault removes that
choice. Your data lives in a local PostgreSQL database you control. Models are
interchangeable. Every agent, built-in or external, works through the same scoped
grants. No ReSono Labs account or hosted control plane is required.

## What Vault does

### Live memory and tool routing
Vault starts preparing *while you are still speaking or typing*.

- **Live transcription:** speech streams through OpenAI `gpt-live-transcribe` in
  parallel with the conversation.
- **Live memory:** each new phrase searches your memory through local EmbeddingGemma
  vectors and a pgvector HNSW index. Hits come back in about 0.3–0.5 s. Relevant
  memories reach the agent before you finish the sentence.
- **Live tool routing:** the OpenAI Decisions API picks the likely tool from the
  current catalog in about 0.2–0.5 s warm. The choice is handed to the agent as a
  provisional route, so it can act without deliberating. Nothing runs before you
  finish. Every action still goes through normal authorization and confirmations.
- **Validation:** every live result is checked against current memory versions,
  grants, session and the Live Memory switch. Voice and Chat share the same engine
  and the same live panel.

### Memory that learns, with you in control
- **Memory review:** completed conversations are reviewed by your chosen model.
  It extracts typed facts, preferences, decisions and corrections, each with evidence
  and confidence, and reconciles them with what Vault already knows.
- **Procedural learning:** handling is assessed for request resolution, usefulness,
  tool and context selection, and your feedback. Only qualified, read-only
  procedures are activated as learned rules.
- **Corrections and forgetting:** explicit, confirmed, and respected. A forgotten fact
  is not quietly relearned.
- **Long sessions:** resumable, windowed review instead of silent truncation.

### One assistant, many models
- **Voice:** OpenAI Realtime, Gemini Live and xAI realtime voice in the browser over WebRTC.
- **Chat:** the same tools, memory and live preparation as text, with history,
  attachments and streaming responses.
- **Background Agent:** the Voice agent hands off longer goals, which run with
  visible progress and the same grants.
- **Providers:** API keys or OAuth for OpenAI (ChatGPT), Google Gemini and xAI.
  Per-capability routing lets OAuth handle conversation while an API key covers
  features that need it (live transcription, web search, Decisions).

### Your data, integrated
- **Mail:** IMAP accounts plus a separate assistant mailbox.
- **Calendar:** CalDAV and ICS.
- **Contacts:** a local contacts store.
- **Tasks:** a local task list.
- **Files:** private per-account workspaces, plus optional linked computer folders.
- **Built-in plugins:** weather, markets, news, local events, and grounded web
  search with citations.
- **Business integrations:** Business workspace and CRM packages run as supervised
  in-Vault MCP sidecars, with their own data migrations.

### An open extension surface
- **Library:** import Agent Skills, Agent Plugins (`vault.json`), hosted MCP packages
  (`mcp.package.json`) and external MCP connections (`mcp.json`).
- **Import review:** packages are quarantined and reviewed without executing their
  code. Supervised processes run sandboxed (bubblewrap). Capabilities are granted
  explicitly, per workspace.
- **Agent2Agent:** standard A2A 1.0 in both directions. Voice and Background can call
  Hermes, OpenClaw or any A2A agent. Inbound tasks run only on the Background Agent.
- **Shared memory for other agents:** Hermes and OpenClaw get scoped, revocable
  memory access through pairing adapters.
- **Developer kits:** the Plugin Kit and MCP Package Kit include schemas and validators.
- **Vault Help:** answers from the platform's own documentation and source.

### Built for households and teams
- **Accounts:** local accounts with private-by-default data, shared or individual
  provider access, and workspace-scoped authorization.
- **Remote access:** optional through [ReSono Labs Link](docs/RESONO-LABS-LINK.md),
  your VPN or your reverse proxy. Vault never requires it.

## Install with Docker

Requires Docker Engine or Docker Desktop with Compose.

```bash
./vault-package install
./vault-package status
./vault-package setup
```

Open `https://127.0.0.1:8765`. The generated local certificate may need a one-time
browser trust step. Apps that cannot use the local certificate can use the
loopback-only bridge at `http://127.0.0.1:8766`.

See the [Platform Guide](docs/PLATFORM-GUIDE.md),
[Windows installation](docs/WINDOWS-INSTALLATION.md) and
[production package](docs/development/PRODUCTION-PACKAGE.md) documentation.

## Architecture at a glance

| Layer | What it is |
|---|---|
| Runtime | Python 3.12, a local HTTPS API, PostgreSQL 16 with pgvector |
| Embeddings | Local EmbeddingGemma 300M, bundled CPU runtime, offline |
| Agents | OpenAI Agents SDK shared runner; fixed Voice and Background agents |
| Frontend | React and TypeScript, browser WebRTC voice, assistant-ui Chat |
| Packaging | Docker Compose with backup, restore, factory reset and LAN mode |

## Security model

- **Network:** listeners bind to loopback by default. Non-loopback API binding
  requires TLS.
- **Authority:** local sessions, CSRF protection, workspace authorization, encrypted
  credentials, extension safe mode and explicit capability grants are enforced
  regardless of transport.
- **Credentials:** provider keys are encrypted at rest and never returned to the browser.
- **Remote MCP:** endpoints are revalidated before I/O and cannot target private,
  link-local, metadata or reserved networks.
- **Agent boundary:** plugins never create new agents. Vault has exactly one Voice
  Agent and one Background Agent.

Report vulnerabilities according to [SECURITY.md](SECURITY.md).

## Development

Python 3.11+, Node.js/npm, Docker and `uv`. Tests use a separate, allowlisted
PostgreSQL database and must never point at installed Vault data.

```bash
uv sync --dev
npm --prefix frontend ci
./scripts/test_env.py up
./scripts/test_env.py test
```

## Status

Vault is in active development and testing. Live memory, live tool routing,
learned procedures and Chat are working end to end on the Docker package. The
Decisions API is an OpenAI public beta, and live transcription needs an OpenAI API
key. Current limits and verification evidence are tracked under `docs/` and in the
[changelog](CHANGELOG.md).

## License and provenance

Vault is meant to be free for everyone. The vision is a free, easy-to-use, private
AI platform that people and businesses can run, study, modify and build on, on their
own hardware.

Vault is open source under the [Apache License 2.0](LICENSE). You can use, modify,
self-host and share it, for personal or business use. Attribution and third-party
notices are in [NOTICE](NOTICE). The live-input stream is adapted from VoiceMem
(Apache-2.0). Feature provenance is documented under `docs/planning/`.

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
