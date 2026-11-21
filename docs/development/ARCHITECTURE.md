# Vault architecture

How Vault is built: what runs, where each piece lives, and the rules that keep
it consistent. Read this before changing code. [CONTRIBUTING.md](../../CONTRIBUTING.md)
covers the workflow, and the other files in this folder cover testing and packaging.

Paths are relative to the repository root.

## The system in one picture

```
Browser (React app)  ── HTTPS :8765 ──►  Vault process (Python 3.12)  ──►  PostgreSQL 16 + pgvector
Link phone app       ── bridge :8766 ─┘     │                                 (private to Compose)
Other agents (A2A)   ── HTTP  :8768 ───────►│
Hermes / OpenClaw    ── HTTPS :8765 ───────►│
                                            ├─► model providers (OpenAI, Google Gemini, xAI)
                                            ├─► local embedding runtime (127.0.0.1:11435)
                                            └─► supervised MCP package processes (127.0.0.1)
```

- **One Python process** serves the API, runs the durable background worker and
  supervises MCP packages. There is no separate worker service.
- **PostgreSQL** holds all structured data, including the job queue and memory
  vectors. Files (workspaces, extensions, keys, TLS) live under the data root.
- **The browser talks to voice providers directly** (WebRTC for OpenAI Realtime,
  WebSocket for Gemini Live and xAI). Vault creates the session and executes the
  tools the model calls.
- **Everything listens on loopback by default.** LAN mode is an explicit install
  option and requires TLS.

## Repository map

| Path | Contents |
|---|---|
| `app/core/` | Shared exceptions and security primitives (PBKDF2 password hashing, opaque tokens, outbound host checks, offline JSON Schema checks) |
| `app/vault_runtime/package_runtime.py` | Process entry point: `initialize`, `serve`, `healthcheck`, `show-setup`, `reconcile-restore` |
| `app/vault_runtime/composition.py` | Builds every service and wires them into the API app (the composition root) |
| `app/vault_runtime/local_api/` | HTTPS server (`server.py`), route table (`app.py`), configuration (`config.py`), browser coordination API (`background.py`) |
| `app/vault_runtime/local_api/routes/` | One route module per API area, plus shared helpers in `common.py` |
| `app/vault_runtime/migrations/` | Numbered schema migrations and the runner |
| `app/vault_runtime/local_identity/` | Local accounts, workspaces, memberships and sessions |
| `app/vault_runtime/system_agents/` | The fixed agent inventory (Voice Agent, Background Agent) |
| `app/vault_runtime/voice/` | Voice sessions, provider adapters (OpenAI Realtime, Gemini Live, xAI), instructions, context, events, credentials, Link phone calls (`companion.py`) |
| `app/vault_runtime/conversation/`, `conversation_tools/` | Chat runtime, history, attachments, the tool adapter and the approval gate |
| `app/vault_runtime/live_memory/` | Live preparation while the user speaks or types (proposes memories and tools, never runs them) |
| `app/vault_runtime/memory/`, `memory_search/` | Canonical memory: schema, repository, review and learning pipelines, embeddings, indexed search |
| `app/vault_runtime/decision_learning/`, `decision_routing/` | Learned procedures and live tool selection |
| `app/vault_runtime/background_agent/` | Durable jobs, executor, coordinator, routines, scratchpad, specialists, approvals, prepared actions |
| `app/vault_runtime/tools/` | The tool catalog and tool definitions |
| `app/vault_runtime/email/`, `calendar/`, `contacts_tools.py`, `personal_data.py`, `session_tools/`, `signals/` | Mail, Calendar, Contacts |
| `app/vault_runtime/tasks/`, `tasks_tools.py`, `notifications/` | Tasks and notifications |
| `app/vault_runtime/folders/`, `workspace_files/`, `workspace_storage.py`, `workspace_paths.py` | Host folders shared with users, workspace files and per-workspace storage |
| `app/vault_runtime/commands/` | Command-line tools for agents, confined with Landlock |
| `app/vault_runtime/extensions/` | Plugin, Skill and MCP import, review, lifecycle, MCP client (`mcp_client` picks the era; `mcp_modern` 2026-07-28 and `mcp_legacy` 2025-11-25 share `mcp_http`), MCP sign-in (`mcp_oauth` protocol, `mcp_accounts` personal and shared credentials), supervisor, secrets |
| `app/vault_runtime/builtin_plugins.py`, `builtin_plugin_tools.py` | Built-in plugins |
| `app/vault_runtime/agent_network/` | Agent2Agent (A2A) client, inbound server and collaboration tools |
| `app/vault_runtime/external_memory/` | Scoped memory API for the Hermes and OpenClaw adapters |
| `app/vault_runtime/link_companion/` | ReSono Labs Link pairing, phone chat, voice and tools |
| `app/vault_runtime/genui/` | Display-only card catalog for Chat |
| `app/vault_runtime/help_assistant.py` | Vault Help |
| `app/vault_runtime/web_search.py` | Web search with required citations |
| `frontend/` | The web app (React, TypeScript, Vite) |
| `plugin-kit/`, `mcp-kit/` | Plugin Kit and MCP Package Kit: schemas, CLIs, starters (and SDKs in the Plugin Kit) |
| `integrations/` | Hermes and OpenClaw memory adapters |
| `packaging/` | Docker distribution package and the native Linux service package |
| `scripts/` | Package lifecycle, test harnesses, release build, embedding staging, public-tree check |
| `tests/` | `unit/`, `integration/` (PostgreSQL) and shared `support/` helpers |
| `Dockerfile`, `compose.yml`, `compose.test.yml` | Image, package from source, isolated test database |

## Startup

`python -m app.vault_runtime.package_runtime serve` is the image's command.

1. `initialize` creates the data root (`RESONO_VAULT_DATA_ROOT`, `/var/lib/resono-vault`
   in the image) with mode 0700 folders, and writes each secret once: database
   password and URL, setup credential and its hash, session capability secret. It
   also creates a local CA and a server certificate for `RESONO_VAULT_TLS_HOSTS`.
2. `serve` reads `VaultLocalApiConfig.from_env()`, starts the bundled embedding
   runtime when `RESONO_VAULT_LOCAL_EMBEDDINGS=1`, and calls
   `composition.build_local_app(config)`.
3. `build_local_app` runs the migrations, then builds repositories and services in
   dependency order, registers every tool in the catalog, and starts the background
   threads: the durable worker, memory index maintenance, the A2A inbound listener,
   MCP package restore and conversation review recovery.
4. `local_api/server.py` serves the app on a standard-library `ThreadingHTTPServer`
   with TLS 1.2 or newer. It also serves the built web app from `RESONO_VAULT_WEB_ROOT`
   and the local CA at `/vault-local-ca.crt`.

From source, `python -m app.vault_runtime.local_api` runs the same app without
`initialize` and without the embedding runtime. `scripts/internet_test_env.py`
uses it this way.

The loopback bridge on port 8766 is not Python. It is an nginx container
(`packaging/docker-release/bridge/nginx.conf`) that forwards to `https://vault:8765`
for clients that cannot trust the local certificate.

## Request path

```
server.py ─► VaultLocalApiApp.handle() ─► _ROUTES (first match) ─► route mixin ─► service ─► repository ─► PostgreSQL
```

- **Routing.** `local_api/app.py` defines `VaultLocalApiApp` from one mixin per
  area (`routes/*.py`) and a `_ROUTES` table of `_Route` entries (exact paths or
  prefixes, an optional method and suffix). The first matching entry wins. There is
  no middleware layer: each route authenticates and validates for itself.
- **Sessions.** `routes/common.py` reads the session from `Authorization: Bearer`
  or the `resono_refresh` cookie (HttpOnly, SameSite=Strict) and resolves a
  `LocalPrincipal` (`user_id`, `workspace_id`).
- **CSRF.** Requests that change data must send the `resono_csrf` cookie value in
  the `X-ReSono-CSRF` header. The route checks both and then calls
  `identity.require_csrf`.
- **Other credentials.** The external memory API, Link companion, A2A inbound and
  plugin services each use their own bearer token or per-call capability header.
  Each is checked in its route module.
- **Scoping.** Every service and repository call takes the principal's `user_id`
  and `workspace_id`. Scoping is enforced at the storage boundary, not in the UI.
- **Errors.** Routes map `ValueError` to 400, `PermissionError` to 403 and session
  errors to 401, and return `{"error": {"code", "message"}}`. Unknown paths return 404.

**Adding a route:**

1. Add a `_route_<area>` method to the area's mixin in `routes/`, or add a new
   mixin to the `VaultLocalApiApp` bases.
2. Add a `_Route` entry to `_ROUTES` in `app.py`, in the right position, because
   the first match wins.
3. Authenticate, check CSRF for writes, and pass the principal's scope to the
   service. Services reach the app through `VaultLocalApiApp.__init__`, wired in
   `composition.py`.
4. Add a client function in `frontend/src/browser-voice/api/` if the web app uses
   the route.
5. Regenerate the route snapshot and review the diff (see
   [LOCAL-TEST-ENVIRONMENT.md](LOCAL-TEST-ENVIRONMENT.md#guard-tests)).

## Agents

`system_agents/inventory.py` defines two agent kinds, `VOICE` and `BACKGROUND`.
Every tool declares which of them may use it. Plugins, Skills and MCP servers add
tools. They never add agents.

| Surface | Runs as | Runtime | Code |
|---|---|---|---|
| Voice (browser) | Voice Agent | Provider realtime session (OpenAI Realtime, Gemini Live, xAI); the browser connects directly, tool calls come back to `POST /voice/sessions/{id}/tools/call` | `voice/provider.py`, `voice/openai_realtime.py`, `gemini_live.py`, `xai_realtime.py`, `voice/tools.py` |
| Voice (Link phone) | Voice Agent | Vault opens an OpenAI Realtime call and controls it over the server-side connection | `voice/companion.py` |
| Chat | Voice Agent kind, in coordinator mode when background coordination is on | OpenAI Agents SDK (`background_agent/sdk_runner.py`); xAI and Gemini through their OpenAI-compatible endpoints | `conversation/runtime.py`, `background_agent/coordinator_prompt.py` |
| Background work | Background Agent | Agents SDK, or a native Gemini path when Gemini is selected | `background_agent/executor.py` |
| Specialists | Background Agent, with their own role, instructions and grants | Same executor; created by the Chat coordinator, owned by one user | `background_agent/worker_repository.py`, `coordinator.py`, `coordinator_tools.py` |

**Chat coordinator.** With background coordination on (the production default),
Chat is the user's coordinator. It can do the work itself, save reminders,
follow-ups and routines, keep a scratchpad of open work, start background work
or specialists, and wake itself in the same chat when a follow-up is due, work
finishes or an approval is answered. Voice hands longer requests to the
coordinator (`voice/coordinator_tools.py`).

Other model calls are capabilities, not agents: memory review
(`memory/openai_reviewer.py`), live tool selection (`decision_routing/`), chat
titles, card presentation hints and Vault Help.

## Tools

All tools live in one `ToolCatalog` (`tools/catalog.py`). Voice, Chat and
Background all read from it, so a tool behaves the same everywhere.

- **Define** a `ToolDefinition` (`tools/definitions.py`): name, description, JSON
  Schema (Draft 2020-12), handler, effect class (`read`, `write`, `delete`),
  audiences, and optional scope (one user and workspace) or `conversation_only`.
- **Register** it in `composition.py` through the domain's `register_*_tools`
  function. Plugins and MCP servers register through
  `replace_capability_source(source_id, definitions)`, which replaces that
  source's tools as a group.
- **Enumerate.** Voice sessions get `catalog.realtime_definitions()`, Chat gets
  them through `ConversationToolRuntime`, Background through
  `background_agent/tool_supply.py`.
- **Invoke** with `catalog.invoke(name, arguments, context=...)`. In order, it
  checks:
  1. the audience and scope;
  2. grants (`LocalToolAuthority`, or the background authority for background work);
  3. that the arguments match the schema (errors name fields, never values).
     Schemas are checked offline (`app/core/security/json_schema.py`): only
     references inside the same schema are allowed, and nothing is fetched;
  4. the approval gate.

  After the checks it runs the handler and records the outcome. `ValueError`
  from a handler becomes a tool error the model can read.

A tool is ready only when it is registered, granted, enumerated into the
intended agent's session or run, shown in the Library, and tested through the
same `invoke` path the agent uses.

## Approvals

- **Chat and Voice** use one gate (`conversation_tools/approval_gate.py`), set on
  the catalog at startup. A tool call that needs approval waits while the user
  allows or denies it in the browser (`/approvals`) or on the Link phone,
  including during a phone call. A timeout, or the end of the turn or call, counts as deny.
  Approvals are rows in `vault_private.vault_background_actions`
  (`background_agent/owner_approvals.py`). At startup, any approval still waiting
  from the previous process is denied.
- **Direct requests need one approval.** When the user asks for an action
  directly, the agent prepares it and shows one approval card. The agent does not
  ask for spoken confirmation as well. When the user asked in the same turn, the
  coordinator's own reminders, follow-ups and routines, and new specialists, are
  saved without a card. Work that Vault started on its own still asks.
- **Background work** uses prepared actions (`background_agent/actions.py`,
  `action_bridge.py`, `action_domains.py`). Sending mail, changing the calendar,
  contacts or tasks becomes a prepared action that the user approves before it runs.

## Background engine

- **Queue.** `background_agent/jobs.py` runs a procrastinate worker (schema
  `vault_background_queue`, tasks `vault.work` and `vault.wake`, concurrency 4) in
  a thread of the main process.
- **Admission.** At most 4 runs are active at once, and at most 2 per user,
  checked under an advisory lock. Work that does not fit is retried.
- **Loop.** Every 15 s it runs due routines, reminders and follow-ups
  (`routines.py`). Every 10 s it reconciles stalled jobs and resumes decided
  approvals. Once an hour it runs the daily check-ins.
- **Execution.** `executor.py` runs with checkpoints, step guards and budgets for
  tool calls, model turns and time, so work can resume after a restart.
- **Wakes.** A wake re-runs the coordinator in the chat that owns the work, as
  the session last active there. If that user is signed out, the result waits in
  the chat.
- **Direct runs.** `direct_runs.py` gives A2A inbound tasks a one-shot run on the
  same engine. `run_events.py` stores the per-run phase and reasoning summaries
  shown on the Background page.
- **Compatibility.** `POST /background/runs` still works for one release and logs
  `background_runs_post_deprecated`. Runs from the old engine stay readable, and
  any left active are marked failed at startup.

## Memory

- **Canonical memory** (`memory/`) stores typed facts, preferences, decisions and
  corrections per user and workspace, with evidence and confidence.
  `memory/service.py` is the entry point, and `memory/suppression.py` makes sure
  forgotten facts are not learned again.
- **Embeddings** come from the bundled local runtime (`memory/local_embeddings.py`,
  EmbeddingGemma 300M, 768 dimensions) over `http://127.0.0.1:11435`. Memories are
  embedded when they are written. Missing vectors are retried later. Vault never
  stores a made-up vector.
- **Search** (`memory_search/`) uses a pgvector HNSW index and a full-text index.
  `memory_search/maintenance.py` builds them at runtime with
  `CREATE INDEX CONCURRENTLY`, and the service switches to indexed search once
  they are ready.
- **Review** runs after a conversation: `memory/pipeline.py` with the selected
  model (`openai_reviewer.py`) extracts and reconciles memories. Voice uses
  `voice_learning.py` and Chat uses `chat_learning.py`. Long chats are reviewed in
  resumable windows.
- **Live preparation** (`live_memory/`) searches memory and proposes a likely tool
  while the user is still speaking or typing. It only proposes. The agent still
  calls the tool through the catalog.
- **Learned procedures** (`decision_learning/`) assess how requests were handled
  and activate only qualified read-only rules. `decision_routing/` uses them for
  live tool selection.

## Data and migrations

- **Schemas.** `vault_private` (application data) and `vault_background_queue`
  (job queue).
- **Migrations** live in `app/vault_runtime/migrations/`. Each is named
  `NNNN_name.py` with `apply(cursor)`, plus an optional `NNNN_name.sql`.
  `runner.py` takes an advisory lock and applies new migrations in order, each in
  its own transaction, then records version and checksum in
  `vault_private.schema_migrations`.
- **Startup refuses to continue** when an applied migration's checksum changed or
  when the database has a version this code does not know. Migrations are
  append-only. To change the schema, add the next number. `0001_baseline` also
  accepts the checksum of its earlier text so existing installs keep starting.
- **Files** live under the data root:
  - `private/`: workspace storage;
  - `extensions/`: imported packages, with a `quarantine/` folder;
  - `keys/`, `config/` and `tls/`;
  - `runtime/commands/`: scratch space for command runs.
- **Credentials** (provider keys, mail, calendar, A2A, extension secrets, MCP
  accounts) are encrypted with AES-GCM. `extensions/secrets.LocalMasterKey` keeps one key file
  per domain in `keys/`. Provider keys are never returned to the browser.

## Extensions

- **Import.** Plugins (Agent Plugins 1.0.0 `plugin.json`), Skills, hosted MCP packages
  (`mcp.package.json`) and external MCP connections (`mcp.json`) are unpacked
  into quarantine and reviewed without running their code
  (`extensions/service.py`, `archives.py`, `package_review.py`, `preflight.py`).
  Capabilities are granted per workspace and per agent. Nothing is granted
  automatically.
- **Hosted MCP packages** run as child processes of Vault on `127.0.0.1`, on
  ports 8788–8899, supervised by `extensions/mcp_runtime.py`. They inherit only a
  short list of harmless environment variables, never Vault's secrets.
- **Storage is per workspace** (`extensions/filesystem.py`): every install's
  files are under `<root>/<category>/.ws/<workspace>/<identity>/{current,previous}`
  and its data under `<root>/data/.ws/<workspace>/<identity>`, so the same name in
  two workspaces is two independent installs. A plugin and its hosted MCP package
  (or companion) in one workspace share that workspace's data folder, which is
  deleted only when no install in the workspace still uses it. Installs from before
  this layout (no `storageScope` in their configuration) are moved at startup
  (`ExtensionFilesystem.adopt_legacy`) when exactly one workspace uses the old
  name-keyed folder. When two workspaces used it, the bytes stay where they are and
  both installs are blocked (`storageConflict`) until the device owner reinstalls one.
- **Safe mode** is one device-wide, persistent setting
  (`vault_extension_runtime_settings`, key `third_party_extensions`). While it
  is on, no third-party capability is projected, the supervisor refuses every
  start (confirm, enable, boot restore, restart), and turning it on stops every
  supervised process group and unpublishes its host port.
- **Remote MCP endpoints** are checked before every connection and cannot target
  private, link-local, metadata or reserved networks (`app/core/security/outbound.py`).
- **Plugin data.** Vault-specific package data lives under the
  `com.resonolabs.vault` key in `plugin.json` `extensions` and a top-level
  `com.resonolabs.vault/` folder. A root `vault.json` is still read for older
  packages; if both exist the namespace wins and `vault.json` is ignored with a
  diagnostic. Other clients' namespaces are ignored.
- **MCP in plugins.** Only Streamable HTTP servers become connections; stdio and
  SSE entries are skipped with a per-server diagnostic, and a connection Vault
  cannot execute never receives a request. Header names and values are checked,
  merged case-insensitively, and Vault's own headers always win.
- **Skills** (`extensions/skills.py`, `activation.py`): new imports must have a
  valid `name` matching their folder (rules of the pinned `skills-ref`
  validator); installs from before that rule load as `legacy`. Agents get a
  catalog (name, description, id, source) in Voice, Chat and Background, load a
  skill by name or id (an ambiguous name is an error, never a guess) and read
  bundled files with a bounded, read-only tool confined to that skill's folder.
  A damaged skill is left out without hiding its siblings.
- **Built-in plugins** (`builtin_plugins.py`): weather, markets, news, local
  events, agent mail, tasks, Agent2Agent and A2A collaboration.

## Integrations

- **A2A** (`agent_network/`): outbound calls from Voice and Background to other
  agents, and an inbound listener on port 8768 that turns accepted tasks into
  direct background runs.
- **External memory** (`external_memory/`): pairing and a bearer-token API under
  `/external-memory/` for the Hermes and OpenClaw adapters in `integrations/`.
  Their writes are proposals that Vault reviews and reconciles.
- **Link companion** (`link_companion/`): pairing, phone chat (answered by the
  coordinator by default, `RESONO_VAULT_LINK_CHAT_RESPONDER`), phone voice and
  approvals.
- **Link Front Door v1** (`link_companion/front_door.py`): the agent contract Link's
  engine uses for owner chat. `GET /link/v1/capabilities`, `POST /v1/responses`
  (background turns with `Idempotency-Key`, images as `data:` URIs only), `GET` and
  `POST .../cancel` on `/v1/responses/{id}`, `POST /link/v1/responses/{id}/approval`
  and `/link/v1/drafts[/status|/clear]`. It authenticates with the paired companion
  bearer and translates to the legacy companion chat handler (`link_companion/chat.py`),
  so turns, live preparation, approvals and activity behave exactly as there. GenUI
  cards are returned as Link Cards v1 (`link_cards`). Steer and streaming are reported
  unsupported, and voice keeps the direct WebRTC companion routes. A Link conversation
  maps to one Vault conversation (`link_conversation`, or the conversation id Link
  sends back as `previous_response_id`). The legacy `/link-companion/chat/*` routes stay
  until every Link install uses the Front Door.
- **Vault Help** (`help_assistant.py`) answers from the help-source tree in the
  image (`/opt/resono-vault/help-source`): the seven user guides, `app/`,
  `docs/README.md` and `docs/development/`.

## Personal data

| Domain | Code | Notes |
|---|---|---|
| Mail | `email/` | IMAP and SMTP accounts plus a separate assistant mailbox; sync feeds the coordinator |
| Calendar | `calendar/` | CalDAV and ICS; sync feeds the coordinator |
| Contacts | `contacts_tools.py`, `personal_data.py` | Local store |
| Tasks | `tasks/`, `tasks_tools.py` | Local list |
| Folders | `folders/` | Host folders shared by the master account; locations come from `RESONO_VAULT_DEVICE_LOCATIONS`, set by the installer |
| Workspace files | `workspace_files/` | Private per-workspace storage |
| Commands | `commands/` | Run inside a user's folder under Landlock; refused when Landlock is unavailable; each run needs approval |

## Web app

- **Build.** `frontend/` is React 18 with TypeScript, built by Vite from
  `browser-voice.html` into `dist/`. The image serves it from
  `/opt/resono-vault/web`.
- **Shell.** `src/browser-voice/BrowserVoiceApp.tsx` is the app shell. It uses no
  router library: pages come from the URL hash and query.
- **API.** `localApi.ts` assembles one client module per area from `api/`. Chat
  has its own `conversation/api.ts`.
- **Voice** is `useVoiceSession.ts`. **Chat** is `conversation/`, built on
  assistant-ui. **Cards** are `genui/`; their layouts mirror `app/vault_runtime/genui/catalog.py`.
- **Themes.** Midnight is the default and Aurora the alternative (`theme.ts`).
  After changing app CSS, run `npm run theme:aurora` to regenerate
  `styles/browser-voice-aurora.generated.css`. Breakpoints are 560 px and 800 px.

## Configuration

`local_api/config.py` reads the environment. These are the settings that matter
when developing:

| Variable | Default | Effect |
|---|---|---|
| `RESONO_VAULT_DATA_ROOT` | per-platform data folder | Data root |
| `RESONO_VAULT_DATABASE_URL` / `_FILE` | `config/database-url` | Database |
| `RESONO_VAULT_LOCAL_API_HOST` / `_PORT` | `127.0.0.1` / `8765` | Listener; any other host requires TLS |
| `RESONO_VAULT_LOCAL_API_TLS_CERTIFICATE_FILE` / `_PRIVATE_KEY_FILE` | unset | TLS for the listener |
| `RESONO_VAULT_WEB_ROOT` | unset | Built web app to serve |
| `RESONO_VAULT_A2A_LISTEN_PORT` | `8768` | A2A inbound listener |
| `RESONO_VAULT_LINK_CHAT_RESPONDER` | `coordinator` | Who answers Link chat |
| `RESONO_VAULT_DEVICE_LOCATIONS` | empty | Host folders Vault can offer; empty hides Folders |
| `RESONO_VAULT_GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | unset | Gemini sign-in |
| `RESONO_VAULT_MCP_OAUTH_CLIENT_METADATA_URL` | unset | HTTPS Client ID Metadata Document for MCP sign-in |

These switches are on in production (`from_env`) and can be turned off in an
emergency: `RESONO_VAULT_DECISION_REVIEW_ENABLED`, `_INDEXED_MEMORY_ENABLED`,
`_BACKGROUND_COORDINATION_ENABLED`, `_OWNER_APPROVALS_ENABLED`, `_GENUI_ENABLED`,
`_GENUI_PRESENTATION_HINTS`. A config built directly in a test leaves
coordination, approvals and presentation hints off. The integration fixture
`mounted` turns them on, so tests run the production composition unless they are
marked `@pytest.mark.flags_off("reason")`.

## Rules that keep Vault consistent

- **Two agent kinds.** Extensions add tools, never agents. Specialists are
  user-owned roles of the Background Agent.
- **One catalog.** Every tool goes through `ToolCatalog.invoke`, so grants,
  schema checks and approvals apply on every path.
- **One implementation per capability.** Adapters may translate formats but must
  not fork business rules.
- **Scope at the storage boundary.** Every read, write, search, vector and
  integration call carries the user and workspace.
- **Secrets stay out of** source, logs, model context, memory and plugin
  processes.
- **Loopback first.** Any non-loopback listener requires TLS, and remote access
  is optional.
- **Append-only migrations.** Never edit a merged one.
- **Tests never touch real data.** pytest refuses any database except the
  isolated test database (see [LOCAL-TEST-ENVIRONMENT.md](LOCAL-TEST-ENVIRONMENT.md)).
- **Machine-independent repository.** No absolute local paths in it:
  `scripts/check_public_tree.py` checks this in CI.

## Known gaps

These are current limits, not designs to build on:

- **Hosted processes are confined, not sandboxed.** Hosted MCP packages and
  supervised plugins start under Linux Landlock (`extensions/confinement.py`, which
  uses the same `commands/landlock.py` as agent commands): their own package read
  only, their own data folder read and write, system files read only. Vault's data,
  keys and other installs are refused by the kernel, and Landlock's ptrace checks keep
  other processes' `/proc` entries out of reach. They still run as Vault's OS user,
  can use the network and share CPU and memory, so the owner approves each package.
  Without Landlock in the kernel they run unconfined and report `confinement: none`.
- **No Origin checks.** CSRF protection relies on the double-submit token, not
  on Origin or `Sec-Fetch-*` headers.
- **Unused settings.** The local API token in `config/local-api-token` is
  required at startup, but no route checks it. The `RESONO_VAULT_BROWSER_STARTUP_*`
  and `RESONO_VAULT_BROWSER_MEDIA_*` settings are parsed but unused.
- **Network model calls.** Memory review, live tool selection, titles, web search
  and Vault Help call the selected model provider. Only embeddings are fully
  local.
