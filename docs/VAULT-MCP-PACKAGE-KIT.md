# Vault MCP Package Kit

Audience: developers shipping hosted MCP servers into ReSono Labs Vault

## What this is

A **hosted MCP package** is the primary install unit in Vault:

- Vault unpacks server code under `extensions/mcps/{name}/`.
- Vault **supervises** the process (start on **Turn on**, stop on **Turn off** / **Remove**).
- Vault renders **owner settings** from `config.schema.json` in the UI.
- Vault discovers tools and projects them to Voice and Background Agent after explicit grants.

An MCP is **not** part of an Agent Plugin. A zip may optionally include a **companion Agent Plugin** (skills, Vault service declarations). The companion is a **sibling** record linked by manifest — it does not own or spawn the MCP.

**Import and removal are linked when a companion is declared.** One MCP package zip can install both rows at once, but deletion follows the MCP row unless you change the manifest (see [Companion Agent Plugin](#companion-agent-plugin)).

External MCP URLs (`mcp.json` only) remain supported for servers you run outside Vault.

## Package layout

```text
your.package/
├── mcp.package.json       Required — primary manifest
├── config.schema.json     Recommended — settings Vault renders for owners
├── server.py              Your MCP HTTP server (or other entrypoint)
├── requirements.txt       Optional — installed into VAULT_PLUGIN_DATA/.venv on first start
└── plugin/                  Optional companion Agent Plugin
    ├── plugin.json
    ├── vault.json
    └── skills/
└── migration/               Optional — hydrated into VAULT_PLUGIN_DATA on import
    ├── resono.db            # SQLite (or manifest-declared name)
    └── workspace/           # Package-owned files (SKILLS.md, ops/, …)
```

`migration/` is **not** copied into `mcps/{name}/current/`. Vault hydrates declared files into `extensions/data/{name}/` during confirm.

## Install units (choose one primary model)

| Type | Zip root file | Vault supervises process? | Package-owned data |
|------|----------------|---------------------------|---------------------|
| **Hosted MCP package** | `mcp.package.json` | Yes | Yes — `extensions/data/{name}/` via `migration` in manifest |
| **Agent Plugin** | `plugin.json` | No | Yes — same `migration` block in `vault.json` (import on **Plugin** tab) |
| **Connection only** | `mcp.json` (upload) | No | N/A |

Agent Plugins remain **Agent Plugins 1.0.0** manifests (`plugin.json` at package root). Vault adds only sibling files (`vault.json`, `config.schema.json`) beside the standard — never inside or replacing the open standard.

## `mcp.package.json`

```json
{
  "$schema": "https://schemas.resonolabs.com/vault/mcp-package/v1.json",
  "name": "resono.business",
  "version": "1.0.0",
  "description": "Business operations MCP",
  "configuration": "config.schema.json",
  "runtime": {
    "type": "process",
    "command": ["python3", "server.py"],
    "cwd": ".",
    "port": 8791,
    "healthPath": "/health",
    "mcpPath": "/mcp"
  },
  "companionPlugin": {
    "directory": "plugin",
    "removeWithPackage": true
  },
  "migration": {
    "database": {
      "source": "migration/resono.db",
      "target": "resono.db"
    },
    "workspace": {
      "source": "migration/workspace",
      "target": "workspace"
    },
    "onConflict": "ask"
  }
}
```

| Field | Purpose |
|-------|---------|
| `name` | Stable identity (`extensions/mcps/{name}/`, DB row) |
| `configuration` | Points at the MCP package settings schema (`config.schema.json`) rendered in **Library → MCP** setup |
| `runtime.command` | Process Vault runs when the owner turns the MCP on |
| `runtime.port` | Hint only — Vault allocates an internal port and sets `VAULT_MCP_PORT` |
| `runtime.healthPath` | GET path polled after start (default `/health`) |
| `runtime.mcpPath` | Streamable HTTP MCP path (usually `/mcp`) |
| `companionPlugin` | Optional sibling Agent Plugin tree |
| `migration.database` | SQLite file copied from zip → `VAULT_PLUGIN_DATA/{target}` |
| `migration.workspace` | Directory tree copied from zip → `VAULT_PLUGIN_DATA/{target}` |
| `migration.onConflict` | `ask` · `replace` · `skip-if-exists` when data already exists |

Archive must be **ZIP or TAR** with **exactly one root directory** (same safety rules as Agent Plugins). MCP package uploads allow up to **~96 MiB** raw archive (128 MiB JSON body budget after base64).

Only `"type": "process"` is supported in this release. Container and stdio runtimes are deferred.

## Import pipeline

| Phase | Vault action |
|-------|----------------|
| **Preflight** | Quarantine, validate manifest/schema, verify `runtime.command` entry exists, validate migration SQLite/workspace payload |
| **Confirm** | Stage code to `mcps/{name}/current/` (excluding `migration/`), hydrate migration into `data/{name}/`, install disabled MCP row (+ companion plugin if declared) |
| **Settings** | Owner saves `config.schema.json` values and secrets |
| **Turn on** | Allocate port, optional venv/pip, start process, health poll |
| **Check tools** | MCP `tools/list` → `vault_mcp_tools` |
| **Grants** | Owner grants tools to Voice / Background → `vault_extension_grants` |

### MCP + companion plugin on import

A single MCP package zip may install **two Library rows**:

| Row | What it owns |
|-----|----------------|
| **MCP** (`kind='mcp'`) | Supervised server, tool discovery/grants, package data under `extensions/data/{name}/` |
| **Companion plugin** (`kind='plugin'`) | Skills, optional `vault.json` services — separate settings schema if declared under `plugin/` |

Vault links them with `companionPluginId` on the MCP row and `companionMcpId` on the plugin row. **Turn on / Turn off** on the MCP row also applies to the companion plugin.

**Removal is asymmetric and MCP-led by default:**

| Owner action | MCP code (`mcps/{name}/`) | Package data (`data/{name}/`) | Companion plugin (`plugins/{name}/`) |
|--------------|----------------------------|-------------------------------|--------------------------------------|
| **Remove MCP package** | Deleted | Deleted (SQLite, workspace, venv) | **Also removed** when `companionPlugin.removeWithPackage` is `true` (default) |
| **Remove companion plugin only** | Unchanged | Unchanged | Deleted |

So you can install MCP and plugin together in one import, but **removing the MCP removes the linked companion plugin** unless the manifest sets `"removeWithPackage": false`. Removing the plugin alone does not remove the MCP or its data.

Set `"removeWithPackage": false` only when you intentionally want the companion plugin to survive MCP package removal (advanced; owners must remove the plugin separately).

### Migration conflict behavior

| `onConflict` | Existing `data/{name}/` target | Result |
|--------------|----------------------------------|--------|
| `ask` (default) | absent | Import migration |
| `ask` | present | UI asks; confirm sends `replaceMigration: true` to overwrite |
| `skip-if-exists` | present | Keep owner data; skip migration copy |
| `replace` | present | Import only when owner confirms package **replace** |

Package **upgrade** swaps `current/` only. Owner data in `data/{name}/` survives unless migration replace is explicitly confirmed. Re-import on upgrade without owner confirmation remains deferred.

## Owner settings (`config.schema.json`)

Use the **same schema** as Agent Plugins (`https://schemas.resonolabs.com/vault/plugin-config/v1.json`). Vault generates the **Library → MCP** setup form from `fields[]`.

Example:

```json
{
  "$schema": "https://schemas.resonolabs.com/vault/plugin-config/v1.json",
  "fields": [
    {
      "key": "greeting",
      "type": "text",
      "label": "Greeting prefix",
      "default": "Hello",
      "maxLength": 40
    },
    {
      "key": "auth_token",
      "type": "secret",
      "label": "Access token",
      "help": "Bearer token required for /mcp. Vault encrypts this value.",
      "secretHeader": "Authorization",
      "required": true
    }
  ]
}
```

### Field types

| Type | UI control | Notes |
|------|------------|-------|
| `text`, `long_text`, `url`, `location`, `number` | Text input | Boundaries via `minLength`, `maxLength`, `minimum`, `maximum` |
| `checkbox` | On/off | |
| `choice`, `multiple_choice` | Select / checkboxes | Requires `choices[]` |
| `list` | One item per line | |
| `secret` | Password field | Requires `secretHeader`; never stored in plain configuration JSON |

### How settings reach your server

When the MCP starts, Vault injects:

| Variable | Source |
|----------|--------|
| `VAULT_MCP_PORT` | Allocated internal port |
| `VAULT_MCP_BIND` | `127.0.0.1` |
| `VAULT_PLUGIN_ROOT` | Install directory (`…/mcps/{name}/current`) |
| `VAULT_PLUGIN_DATA` | Writable data directory |
| `VAULT_MCP_SETTING_{KEY}` | Non-secret settings (`greeting` → `VAULT_MCP_SETTING_GREETING`) |
| `MCP_AUTH_TOKEN` | Parsed from encrypted `Authorization` secret when present |
| `VAULT_MCP_HEADER_{HEADER}` | Encrypted secret fields (`secretHeader: "X-Resend-Api-Key"` → `VAULT_MCP_HEADER_X_RESEND_API_KEY`; hyphens become underscores) |
| `RESONO_DB` | Set when `{VAULT_PLUGIN_DATA}/resono.db` exists after migration |
| `RESONO_WORKSPACE` | `{VAULT_PLUGIN_DATA}/workspace` (always set; directory may be created at start) |
| `VAULT_MCP_VENV` | Path to `.venv` when `requirements.txt` is installed |
| `VAULT_MCP_PYTHON` | Path to venv `python3` used to run `runtime.command` |

Secrets are **never** placed in the zip. Owners enter them in **Library → MCP → Settings**.

**Process env comes from the MCP package row only.** The companion plugin may declare its own `plugin/config.schema.json` for skills or plugin-only options, but secrets saved on the **plugin** row are **not** injected into the supervised MCP process. Put ingest tokens, API keys, and other runtime secrets on the **hosted package's** `config.schema.json`.

For `Authorization`, Vault sets both `MCP_AUTH_TOKEN` (Bearer value) and `VAULT_MCP_HEADER_AUTHORIZATION`.

### Python dependencies (`requirements.txt`)

When `requirements.txt` exists at the package root (`VAULT_PLUGIN_ROOT`):

1. Vault creates `{VAULT_PLUGIN_DATA}/.venv` on first start (or when requirements change).
2. Runs `{venv}/bin/pip install -r requirements.txt`.
3. Rewrites `runtime.command` when it begins with `python` / `python3` to use the venv interpreter.

Mutable install state stays under **`VAULT_PLUGIN_DATA`**, not under `current/` (which is replaced on package update).

## Vault install layout and persistence

### Data root

Docker packages use:

```text
/var/lib/resono-vault/                 ← RESONO_VAULT_DATA_ROOT
└── extensions/                        ← extension_root (composition.py)
```

Linux standalone installs use the same relative tree under the configured data root.

### On-disk tree (extensions)

```text
{data_root}/extensions/
├── quarantine/                        # temporary import extraction
├── runtime/
│   └── ports.json                     # extension_id → internal port (8788–8899)
├── data/
│   └── {mcp.package.name}/            # VAULT_PLUGIN_DATA (writable)
│       ├── resono.db                  # migration.database.target
│       ├── workspace/                 # migration.workspace.target
│       ├── .venv/                     # created when requirements.txt exists
│       └── .requirements.sha256       # reinstall when requirements change
├── mcps/
│   └── {mcp.package.name}/
│       ├── current/                   # VAULT_PLUGIN_ROOT — live package files
│       └── previous/                  # rollback snapshot on replace
└── plugins/
    └── {companion.plugin.name}/
        └── current/                   # companion Agent Plugin tree only
```

### Rules

| What | Where | Replaced on update? |
|------|--------|---------------------|
| Server code, manifests | `mcps/{name}/current/` | Yes — atomic swap; `previous/` kept briefly |
| SQLite, venv, caches | `data/{name}/` | No — survives package replace |
| Port allocation | `runtime/ports.json` | Persists until MCP **Remove** |
| Tool catalog, grants, secrets | PostgreSQL | See below |

### Environment → paths

| Variable | Typical value |
|----------|----------------|
| `VAULT_PLUGIN_ROOT` | `{data_root}/extensions/mcps/{name}/current` |
| `VAULT_PLUGIN_DATA` | `{data_root}/extensions/data/{name}` |
| `VAULT_MCP_PORT` | Allocated loopback port (8788–8899, ~112 slots per Vault) |

### Docker deployment

Hosted MCP packages run as **subprocesses inside the Vault container**:

- Bind address: `127.0.0.1` (`VAULT_MCP_BIND`)
- Vault discovers tools via `http://127.0.0.1:{port}/mcp`
- Do **not** point supervised packages at `host.docker.internal`

External MCP connections (`mcp.json` only) may still target processes outside the container when the owner configures a reachable URL.

## Vault Workspace paths for file tools

If your MCP exposes `list_workspace`, `read_file`, `write_file`, or similar tools, you must understand **three different “workspace” locations**. They are easy to confuse; mixing them up is the most common file-tool bug in hosted packages.

### What the owner sees (Vault → Workspace UI)

The owner’s visible tree is **not** `RESONO_WORKSPACE`.

| UI path | Meaning |
|---------|---------|
| `shared/` | Virtual root — folders other Vault users shared **to** this owner |
| `local/` | Virtual root — folders linked from this computer (`local/{mountName}/…`) |
| Everything else (`business/`, `Work/`, `*.md`, …) | Real files under the workspace files root on disk |

On disk (Docker data root):

```text
{data_root}/private/workspaces/{workspaceId}/files/
├── business/
├── Work/
└── WORKSPACE.md
```

`shared/` and `local/` do **not** exist as plain directories under `files/`. They are **view paths** resolved by Vault’s workspace file service (`app/vault_runtime/workspace_files/`).

### Three storage layers (do not conflate)

| Layer | How it gets there | Typical path variable | Visible in Workspace UI? |
|-------|-------------------|------------------------|---------------------------|
| **Vault Workspace files** | `workspaceImport` on the **companion plugin**, owner edits in UI | Discover under `private/workspaces/{id}/files/` | **Yes** |
| **Package data workspace** | `migration.workspace` in `mcp.package.json` | `RESONO_WORKSPACE` → `extensions/data/{name}/workspace/` | **No** (MCP sandbox) |
| **Local linked folders** | `localShare` on the **companion plugin** at import | `local/{mountName}/…` (virtual); metadata in Postgres | **Yes** (`local/` root) |

**`migration.workspace`** is for package-owned runtime files (skills copy, ops templates). **`workspaceImport`** (companion `vault.json`) is for owner-visible Workspace files. Use both only when you intend both.

### How to wire a hosted MCP package

1. **Companion plugin** (`plugin/vault.json`) — owner-facing contracts:
   - `workspaceImport` — seed markdown into Vault Workspace (`business/…`, root, etc.).
   - `localShare` — optional prompt to link a host folder as `local/{mountName}/…` (see [VAULT-PLUGIN-KIT.md](./VAULT-PLUGIN-KIT.md#link-a-local-folder-on-import-localshare-in-vaultjson)).
   - `lifecycle.supervised` — HTTP sidecar (CRM, etc.) if needed.

2. **Hosted MCP** (`mcp.package.json` + `server.py`) — agent file tools:
   - Implement tools against **Vault Workspace view paths** (`shared/`, `local/`, vault files), not only `RESONO_WORKSPACE`.
   - At root `.`, list **`shared/`**, **`local/`**, then vault file children — same order as the UI.
   - Resolve `local/{mountName}/…` using the **actual mount name** the owner chose at import (e.g. `ReSono-Labs-Business`, not a hardcoded string from your zip).
   - Accept shorthand `local/file.md` by defaulting to the owner’s primary **write** mount when the first segment is a filename, not a mount name.

3. **MCP `config.schema.json`** — runtime secrets and overrides (on the **MCP row**, not the plugin row):
   - `auth_token`, API keys, `crm_base_url`, etc.
   - Optional `local_share_path` (text) — absolute path when the owner uses a **helper-linked** folder readable from inside Docker (browser-linked folders are not).

4. **Grants** — file tools on the **MCP** row; skills on the **companion plugin** row.

### Dynamic `local/` mounts (read from Vault, do not hardcode)

Browser/helper mounts are stored per owner:

```sql
-- vault_private.host_filesystem_mounts
-- columns: mount_name, source ('browser' | 'helper'), permission, workspace_id, user_id, status
```

Your MCP should load active `mount_name` values for the installed workspace and list them under `local/`. Mount names are **owner-chosen** (folder display name / picker label), so `mountName` in `vault.json` is only a **default suggestion** — the live name may differ.

| `source` | Hosted MCP inside Docker |
|----------|---------------------------|
| `helper` | Readable when `local_share_path` (or future platform injection) points at the helper path on disk |
| `browser` | **Not** readable server-side from the container; list the mount, return a clear error on read/write, or map to imported Vault Workspace files as a pragmatic fallback |

### Dynamic `shared/` mounts

Folder shares are stored in `vault_private.vault_workspace_folder_shares`. View paths:

```text
shared/                          → owners who shared to this user
shared/{ownerUsername}/          → that owner’s share mounts
shared/{ownerUsername}/{mount}/  → files under the shared folder_path
```

When there are no inbound shares, `shared/` is an **empty directory** in the UI — not an error.

### Environment variables today vs package sandbox

Vault’s MCP supervisor (`mcp_runtime._build_env`) currently sets:

| Variable | Value today | Use for file tools? |
|----------|-------------|---------------------|
| `RESONO_WORKSPACE` | `{VAULT_PLUGIN_DATA}/workspace` | Package sandbox only — **not** the Workspace UI root |
| `RESONO_DB` | `{VAULT_PLUGIN_DATA}/resono.db` when present | SQLite |
| `VAULT_PLUGIN_DATA` / `VAULT_PLUGIN_ROOT` | Package data / code | Yes |
| `VAULT_MCP_SETTING_*` | Owner MCP settings | Yes |

**Not injected yet (recommended platform follow-up):**

| Variable | Proposed purpose |
|----------|------------------|
| `VAULT_WORKSPACE_ID` | Workspace UUID |
| `VAULT_WORKSPACE_FILES_ROOT` | `private/workspaces/{id}/files` |
| `VAULT_USER_ID` | Owner user id for mount/share queries |

Until Vault injects these, hosted MCPs may discover them from `private/workspaces/{id}/files` and `identity.json`, or query Postgres through the Vault runtime (see reference below).

### Minimal resolution rules (copy into your server)

```text
normalize:
  "." and ""           → workspace root view
  "/local/foo"         → strip leading slashes → "local/foo"

parse:
  "shared"             → area shared, remainder ""
  "shared/alice/docs"  → area shared, remainder "alice/docs"
  "local"              → area local, remainder ""
  "local/Mount/file"   → area local, remainder "Mount/file"
  "business/x.md"      → area vault files

list root:
  shared/, local/, then children of VAULT_WORKSPACE_FILES_ROOT

local write without mount segment:
  local/report.md → local/{defaultWriteMount}/report.md
```

Return structured `{ "ok": false, "error": "…" }` from tools instead of raising when ChatGPT would surface an opaque `INVALID_ARGUMENT`.

### Reference implementation

The `resono.business` hosted MCP (`ReSono-Labs-Business/resono.business/`) implements this pattern:

| Module | Role |
|--------|------|
| `vault_workspace.py` | View-path parse/normalize (`shared/`, `local/`, vault files) |
| `vault_workspace_catalog.py` | Dynamic mounts/shares (Postgres via Vault’s Python + `host_filesystem_mounts`) |
| `workspace.py` | `list_view_directory`, physical resolve, `physical_to_view_path` |
| `vault_bootstrap.py` | Map settings/secrets; discover workspace files root |

Pair with the companion plugin’s `workspaceImport` + `localShare` in `resono.business.plugin/vault.json`.

### Boot behavior

When Vault starts, enabled hosted MCP packages are started automatically (`restore_on_boot`). Disabled packages stay stopped until the owner turns them on.

## Database and extension records

Hosted MCP packages use the existing extensions schema (`app/vault_runtime/extensions/schema.py`). There is no separate `mcp_packages` table.

| Table | Role |
|-------|------|
| `vault_extensions` | One row per MCP (`kind='mcp'`) and one per companion plugin (`kind='plugin'`) |
| `vault_extension_components` | Companion skills (`component_kind='skill'`) |
| `vault_mcp_tools` | Tools persisted after **Check tools** |
| `vault_extension_grants` | Per-tool grants to Voice / Background |
| `vault_extension_secrets` | Encrypted owner secrets (e.g. bearer token) |
| `vault_extension_events` | Install, enable, settings audit |
| `vault_extension_runtime_settings` | Global third-party safe mode gate |

### Hosted MCP `configuration_json` (illustrative)

```json
{
  "packageType": "hosted",
  "packageBundleId": "sha256…",
  "transport": "streamable-http",
  "executable": true,
  "headers": {},
  "runtime": {
    "type": "process",
    "command": ["python3", "server.py"],
    "cwd": ".",
    "port": 8791,
    "healthPath": "/health",
    "mcpPath": "/mcp"
  },
  "configurationSchema": { "fields": [] },
  "settings": { "greeting": "Hello" },
  "runtimeStatus": {
    "state": "running",
    "port": 8788,
    "endpoint": "http://127.0.0.1:8788/mcp",
    "pid": 12345,
    "lastError": null
  },
  "endpoint": "http://127.0.0.1:8788/mcp",
  "url": "http://127.0.0.1:8788/mcp",
  "companionPluginId": "uuid…",
  "companionRemoveWithPackage": true
}
```

Companion plugin row includes `companionMcpId`, `companionMcpName`, and shared `packageBundleId`.

External connection-only MCP rows omit `packageType: "hosted"` and have a fixed `endpoint` / `url` supplied by the owner.

## Production MCP servers (Business-scale)

The stdlib starter demonstrates the contract only. Production packages should:

- Use the **official MCP Python SDK** with Streamable HTTP transport.
- Implement **`GET /health`** and **`POST /mcp`** with MCP protocol version `2025-11-25`.
- Read **`VAULT_MCP_PORT`**, settings env, and secrets from the environment — never hardcode `/home/…` paths.
- When using the MCP SDK behind Vault or Link, configure **transport security** for your deployment (e.g. allowed hosts / DNS rebinding rules when a public Host header is forwarded).

List dependencies in **`requirements.txt`**; Vault installs them into `VAULT_PLUGIN_DATA/.venv` before start.

## Data ownership (split Business + CRM packages)

Large cutovers may ship **two hosted MCP packages** instead of one monolithic zip. Each package owns its own `extensions/data/{name}/` tree and MCP settings.

| Package | Typical `migration` | MCP settings (examples) | Companion plugin |
|---------|---------------------|-------------------------|------------------|
| `resono.business` | `workspace` only | workspace path, MCP access token, Resend API key | `resono.business.ui` — skills |
| `resono.crm` | `resono.db` only | ingest token | `resono.crm.ui` — CRM skills |

| Data | Location | Notes |
|------|----------|-------|
| Package code | `VAULT_PLUGIN_ROOT` (`mcps/{name}/current/`) | Replaced on package upgrade |
| Package SQLite | `VAULT_PLUGIN_DATA` via `migration.database` | Use target name **`resono.db`** — Vault sets `RESONO_DB` only for that file |
| Package workspace files | `VAULT_PLUGIN_DATA/workspace` via `migration.workspace` | Vault sets `RESONO_WORKSPACE` to `…/workspace` |
| Vault Postgres | Vault metadata only | Extension rows, grants, encrypted secrets — not CRM data |
| Vault memory | Companion plugin + memory service grants | Never direct Postgres access from packages |

**Migration `target` names:** Vault copies files to `data/{name}/{target}`, but `_build_env` only auto-exports `RESONO_DB` when the file is exactly `resono.db` and `RESONO_WORKSPACE` for `workspace`. Other target names require your server to read paths under `VAULT_PLUGIN_DATA` directly.

**CRM is not a standalone Agent Plugin zip** for supervised process + SQLite. Ship `mcp.package.json` (`resono.crm`) for the FastAPI/HTTP sidecar and a companion plugin for agent skills. The CRM row appears under **Library → MCP**, not as a plugin-only install.

Import order between split packages does not matter; each row is independent. Remove the old monolithic package before importing split replacements.

## Alignment with Agent Plugins Open Standard

| Concern | Rule |
|---------|------|
| Plugin identity | `plugin.json` uses `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json` unchanged |
| Skills | `skills/{name}/SKILL.md` with standard frontmatter |
| Vault additions | Sibling `vault.json` and `config.schema.json` only — not merged into `plugin.json` |
| MCP ownership | Hosted MCP is **`mcp.package.json`**, not embedded `mcp.json` in a plugin zip (legacy path only) |
| Tools to agents | Grant **MCP tools** on the MCP row; grant **skills** on the companion plugin row |
| Separate database | Lives in `extensions/data/{name}/`, not Vault Postgres |

## Developer CLI

```bash
python3 mcp-kit/cli/vault_mcp.py new my.package
python3 mcp-kit/cli/vault_mcp.py validate ./my.package
python3 mcp-kit/cli/vault_mcp.py package ./my.package --output my.package.zip
```

Directory name must match `mcp.package.json` → `name`. Archives must contain a single root folder with that name (same as Agent Plugins).

## What your server must implement

### Tool MCP servers

1. **Streamable HTTP MCP** at `{VAULT_MCP_BIND}:{VAULT_MCP_PORT}{mcpPath}` (JSON-RPC: `initialize`, `tools/list`, `tools/call`).
2. **`GET {healthPath}`** returning HTTP 2xx before Vault marks the server running.
3. **No TLS in the zip** — TLS and external publish are Vault-owned (per-MCP external access toggle; not in zip).
4. **Read config from environment**, not hardcoded host paths.
5. **Optional `requirements.txt`** at package root for pip dependencies into `VAULT_PLUGIN_DATA/.venv`.

### Supervised HTTP services (minimal MCP)

Some packages (for example `resono.crm`) run a **FastAPI or HTTP app** that is not primarily a tool server. They still declare `healthPath` and `mcpPath` in `mcp.package.json` so Vault can supervise the process. A minimal `/mcp` stub that satisfies the health contract is valid.

**Check tools** may return **zero tools** for these packages. That is expected. Grant skills on the companion plugin row; use the MCP row for settings, turn on/off, and removal.

See `mcp-kit/starters/starter.example/server.py` for a minimal stdlib reference server.

## Companion Agent Plugin

When `companionPlugin` is present, Vault also installs a **plugin** row linked to the MCP:

| MCP row | Plugin row |
|---------|------------|
| `companionPluginId` | `companionMcpId` |
| Tool discovery, grants, runtime | Skills, optional `vault.json` services |
| Owner settings from package-root `config.schema.json` (MCP process) | Owner settings from `plugin/config.schema.json` when declared (plugin/skills) |

Grant **tools** on the MCP. Grant **skills** on the companion plugin. Voice calls MCP tools the same way as any other connection.

### Linked removal (default)

```json
"companionPlugin": {
  "directory": "plugin",
  "removeWithPackage": true
}
```

| `removeWithPackage` | When owner removes the MCP package |
|---------------------|-------------------------------------|
| `true` (default) | Companion plugin row and `plugins/{companion}/` tree are removed with the MCP |
| `false` | Companion plugin stays installed; owner must remove it from **Library → Plugin** if desired |

MCP **Remove** always deletes supervised code (`mcps/{name}/`) and package-owned data (`data/{name}/`). It does not leave orphaned SQLite or workspace files when removal completes successfully.

Removing only the companion plugin (**Library → Plugin → Remove**) deletes that plugin tree only. It does **not** stop or uninstall the hosted MCP or its data directory.

## Owner workflow in Vault

1. **Import package** — **Library → MCP → Import package** (ZIP or TAR with one root folder).
2. Open the MCP row → complete **Settings** (from the package's `config.schema.json`).
3. **Turn on** — Vault starts the server and health-checks `/health`.
4. **Check tools** — discovery runs; tool servers list tools; HTTP sidecars may show none.
5. Grant tools to Voice and/or Background Agent.
6. If the zip included a companion plugin, it turns on/off with the MCP row; grant **skills** on **Library → Plugin**.
7. **Remove MCP package** deletes MCP code, package data, and the linked companion plugin by default — see [linked removal](#linked-removal-default).
8. Exit third-party safe mode if needed (**Connections → Extensions**).

## External `mcp.json` connections

Uploading `mcp.json` alone (**Library → MCP** or legacy connection import) creates a **connection-only** row with no supervised process and no package data directory. Use that for MCP servers you run on another host.

Hosted packages (`mcp.package.json` zip) are the in-Vault path for Business, CRM, and other supervised sidecars. Do not use connection-only import for those when you need migration, settings, or process supervision.

## Packaging checklist

- [ ] Single root folder in zip/tar
- [ ] Valid `mcp.package.json`
- [ ] `config.schema.json` if owners must configure secrets or options
- [ ] `/health` and `/mcp` implemented
- [ ] Server reads `VAULT_MCP_PORT` and settings env vars
- [ ] `requirements.txt` if not stdlib-only (Business, CRM, MCP SDK)
- [ ] Optional companion `plugin/` validates with Agent Plugin + `vault.json` rules
- [ ] No secrets, TLS certs, or public URLs in the archive

## Schema files

- `mcp-kit/schemas/mcp.package.schema.json`
- `plugin-kit/schemas/config.schema.json` (settings UI, shared with plugins)

## Related documents

- [VAULT-PLUGIN-KIT.md](./VAULT-PLUGIN-KIT.md) — Agent Plugin format, **Library → Plugin** import, and `vault.json` migration for package data without a supervised process
- [PLATFORM-GUIDE.md](./PLATFORM-GUIDE.md) — owner-facing extensions overview
