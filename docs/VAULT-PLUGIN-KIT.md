# ReSono Labs Vault Plugin Kit

## Start here

The Vault Plugin Kit helps developers add useful capabilities without changing
Vault. A plugin can teach Voice and the Background Agent when to use a Skill,
connect standard MCP tools, ask for simple settings, and request narrowly scoped
Vault services.

Plugin code runs as its own MCP service. Vault stays in charge of accounts,
permissions, credentials, memory, confirmations, and activity history.

[Download the complete Plugin Kit](/downloads/resono-labs-vault-plugin-kit-0.1.0.zip)

[Download the Python starter](/downloads/resono-labs-vault-plugin-python-starter-0.1.0.zip)

[Download the TypeScript starter](/downloads/resono-labs-vault-plugin-typescript-starter-0.1.0.zip)

[Verify download checksums](/downloads/SHA256SUMS)

## What you can build

A Vault plugin can provide:

- instructions through an Agent Skill;
- one or more Streamable HTTP MCP tool services;
- settings such as a location, topic list, stock symbols, or API key;
- tools for Voice, the Background Agent, or both; and
- approved access to services such as memory search or memory proposals.

A plugin cannot create another Vault agent, read Vault's database, see another
person's private workspace, or run arbitrary code inside Vault.

### Package-owned data (plugins vs hosted MCP)

| Goal | Import path | Manifest | Library tab |
|------|-------------|----------|-------------|
| Skills + settings + optional external MCP connection | Agent Plugin zip | `plugin.json` + `vault.json` | **Plugin** |
| Skills + SQLite and/or workspace files (no supervised server in Vault) | Agent Plugin zip | `vault.json` → `migration` | **Plugin** |
| Supervised process + tools + package data + optional companion skills | Hosted MCP zip | `mcp.package.json` | **MCP** (+ **Plugin** if companion) |

**Agent Plugin** zips do not start a supervised process inside Vault. They can still
import package-owned files: put SQLite and/or workspace trees under `migration/` in
the zip and declare a `migration` block in `vault.json`. Vault hydrates
`extensions/data/{plugin.name}/` on confirm — the same rules as hosted MCP packages.

Use **Library → Plugin → Import plugin**. The installed row appears under
**Plugins**, not MCP. **Remove plugin** deletes that package data when migration
was imported.

For a **supervised HTTP/MCP server** (FastAPI sidecar, tool MCP, CRM process), ship
**`mcp.package.json`** instead and import from **Library → MCP**. See
[VAULT-MCP-PACKAGE-KIT.md](VAULT-MCP-PACKAGE-KIT.md).

For a **hosted MCP + companion skills** cutover in one zip:

- ship **`mcp.package.json`** as the primary install unit;
- put SQLite and workspace files in the zip **`migration/`** tree when the MCP package owns them;
- keep **`plugin.json`** on the companion `plugin/` tree only.

One MCP import can create both an MCP row and a linked companion plugin row.
**Removing the MCP package also removes that companion plugin by default**
(`companionPlugin.removeWithPackage: true`). Removing the companion plugin alone
does not remove the MCP or its data directory.

## Install the kit

Download and unzip the kit. Python 3.11 or newer is needed for its offline
helper command. Vault itself is not required while you create and validate a
package.

```bash
unzip resono-labs-vault-plugin-kit-0.1.0.zip
cd resono-labs-vault-plugin-kit-0.1.0
python3 -m pip install jsonschema
```

The kit includes JSON schemas, a command-line helper, TypeScript and Python
helpers, two starters, and examples.

## Create your first plugin

For Python:

```bash
python3 -m cli.vault_plugin new my-company.weather --language python
```

For TypeScript:

```bash
python3 -m cli.vault_plugin new my-company.weather --language typescript
```

Use a stable lowercase name. Dots and dashes are allowed. Open the new folder
and replace the starter description and application logic.

## Understand the package

```text
my-company.weather/
  plugin.json
  vault.json
  config.schema.json
  mcp.json
  skills/
    weather-help/
      SKILL.md
  migration/                 Optional — not copied into plugins/{name}/current/
    workspace/               Hydrated to extensions/data/{name}/ on import
  README.md
```

`plugin.json` identifies the standard Agent Plugin. `vault.json` says which
Vault agents and services the plugin may ask to use, and may declare **`migration`**
to import SQLite and/or workspace files into `extensions/data/{plugin.name}/`.
`config.schema.json` describes the settings form Vault shows on the **Plugin** row.
`mcp.json` declares an external MCP connection (Vault does not supervise it).
A Skill explains when the agents should use the capability.

Import from **Library → Plugin → Import plugin**. Installed plugins always appear
under the **Plugin** tab, never under MCP.

## Add a Skill

Create `skills/your-skill/SKILL.md`:

```yaml
---
name: your-skill
description: Use this when the user asks for a local weather summary.
---

Use the weather tool for current conditions. Clearly name the saved location.
```

The description helps Vault decide when the Skill is relevant. Skill text does
not grant a tool and no Skill script runs automatically.

## Connect an MCP tool

Add `mcp.json`:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "weather": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8788/mcp"
    }
  }
}
```

Use HTTPS for a remote service. A trusted service on the same computer may use
localhost. When Vault is in Docker and the service is on the host, use the host
address supported by your installation. Never place an API key in this file.

## Add simple settings

`config.schema.json` tells Vault which fields to show. Supported fields include
text, longer text, numbers, on/off choices, selections, URLs, locations, lists,
and secrets.

```json
{
  "$schema": "https://schemas.resonolabs.com/vault/plugin-config/v1.json",
  "fields": [
    {
      "key": "home_location",
      "type": "location",
      "label": "Home location",
      "help": "The city or area to use when you do not name one.",
      "required": true
    }
  ]
}
```

Use friendly labels. Keep help text to one sentence. Vault renders the page, so
plugin settings remain consistent and usable on computers and phones.

## Store an API key safely

Declare a secret and the exact HTTP header your MCP service expects:

```json
{
  "key": "api_key",
  "type": "secret",
  "label": "API key",
  "help": "Create this key in your service account.",
  "required": true,
  "secretHeader": "X-Weather-Api-Key"
}
```

Vault encrypts the value and sends it only to the plugin's managed MCP
connection. The saved value is not shown again. Do not put keys in a manifest,
Skill, README, source file, URL, or package archive.

## Choose Voice and Background access

Declare which fixed Vault agents the plugin supports in `vault.json`:

```json
{
  "$schema": "https://schemas.resonolabs.com/vault/plugin/v1.json",
  "minimumVaultVersion": "0.1.0",
  "agents": ["voice", "background"],
  "configuration": "config.schema.json",
  "mcp": "mcp.json",
  "services": []
}
```

This is a request, not permission. After installation, the Vault owner checks
the plugin's tools, identifies whether each tool reads, changes, or deletes
information, and chooses Voice, Background Agent, or both.

## Import package data (`migration` in `vault.json`)

Optional. Uses the same contract as hosted MCP packages:

```json
{
  "$schema": "https://schemas.resonolabs.com/vault/plugin/v1.json",
  "minimumVaultVersion": "0.1.0",
  "agents": ["voice", "background"],
  "configuration": "config.schema.json",
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

| Field | Meaning |
|-------|---------|
| `migration.database` | SQLite file in the zip → `extensions/data/{plugin.name}/{target}` |
| `migration.workspace` | Directory tree in the zip → `extensions/data/{plugin.name}/{target}` |
| `migration.onConflict` | `ask` · `replace` · `skip-if-exists` when data already exists |

The `migration/` folder is **excluded** from `plugins/{name}/current/`. Vault
copies declared payloads into `extensions/data/{name}/` during **Import plugin**
confirm. Removing the plugin deletes that data directory.

`database` and `workspace` are independent — declare either or both. Prefer target
name **`resono.db`** for SQLite when other Vault integrations expect `RESONO_DB`
on a paired hosted MCP package.

Package **`migration.workspace`** copies into **`extensions/data/{name}/`** for
supervised MCP/runtime use. To land files in **Vault → Workspace** instead, use
**`workspaceImport`** (below).

## Link a local folder on import (`localShare` in `vault.json`)

Optional alternative to copying docs into the zip. During **Import plugin**, Vault
can prompt the owner to link a folder from this computer as **`local/{mountName}/…`**
without copying files into Docker.

```json
{
  "localShare": {
    "mountName": "resono-business",
    "permission": "read",
    "label": "Business workspace docs on this computer",
    "required": false
  }
}
```

| Field | Meaning |
|-------|---------|
| `mountName` | Stable mount segment → agents see `local/{mountName}/…` |
| `permission` | Default suggestion: **`read`** (read-only) or **`write`** (read and write) |
| `label` | Owner-facing text in the import prompt |
| `required` | When `true`, import fails unless the owner links a folder |

On confirm, Vault asks whether to link a folder, then asks **read only** vs **read
and write** (the owner can choose either regardless of the manifest default). The
browser folder picker uses the chosen permission. Computer folders must be enabled
in **Settings**; Vault prompts to turn them on when needed.

The linked mount is stored on the plugin row as **`localShare`** (`mountId`,
`mountName`, `permission`, `pathPrefix`).

Active mounts are also recorded in Postgres (`vault_private.host_filesystem_mounts`)
with the **live** `mount_name` the owner picked (which may differ from the
`mountName` default in `vault.json`).

**Hosted MCP file tools do not receive `localShare` in process env.** The companion
plugin declares the import-time prompt; the **hosted MCP package** must implement
`local/{mountName}/…` resolution itself (query mounts, or use optional
`local_share_path` in the MCP settings schema). See
[VAULT-MCP-PACKAGE-KIT.md — Vault Workspace paths for file tools](./VAULT-MCP-PACKAGE-KIT.md#vault-workspace-paths-for-file-tools).

## Import files into Vault Workspace (`workspaceImport` in `vault.json`)

Use this when markdown or other owner-visible files should land in **Vault →
Workspace**, not in `extensions/data/{name}/`. Package **`migration.workspace`**
remains for supervised MCP/runtime data under `extensions/data/`.

```json
{
  "workspaceImport": {
    "onConflict": "ask",
    "items": [
      {
        "source": "workspace-import/templates/welcome.md",
        "target": "business/welcome.md",
        "kind": "file"
      },
      {
        "source": "workspace-import/playbooks",
        "target": "business/playbooks",
        "kind": "directory"
      }
    ]
  }
}
```

| Field | Meaning |
|-------|---------|
| `onConflict` | `ask` · `replace` · `skip-if-exists` when a target path already exists |
| `items[].source` | Path inside the plugin zip |
| `items[].target` | Vault workspace path (lowercase segments; `""` means workspace root) |
| `items[].kind` | `file` or `directory` |
| `items[].onConflict` | Optional per-item override |

During **Import plugin**, Vault validates sizes, detects conflicts, and prompts
when `onConflict` is `ask`. Confirm stores **`workspaceImportStatus`** on the
plugin row.

Imported paths land under **`private/workspaces/{workspaceId}/files/`** and appear
in the Workspace UI. They are **not** the same tree as `RESONO_WORKSPACE`
(`extensions/data/{name}/workspace/` on the paired hosted MCP). MCP packages that
expose file tools must read the Workspace files root — see
[VAULT-MCP-PACKAGE-KIT.md — Vault Workspace paths for file tools](./VAULT-MCP-PACKAGE-KIT.md#vault-workspace-paths-for-file-tools).

## Supervised plugin process (`lifecycle` in `vault.json`)

Optional HTTP sidecar started and stopped with the plugin row (same supervisor as
hosted MCP packages). Prefer **`mcp.package.json`** when the primary deliverable
is an MCP server; use **`lifecycle`** for plugin-owned HTTP services such as a
CRM UI.

```json
{
  "lifecycle": {
    "supervised": true,
    "runtime": {
      "command": ["bash", "crm/run.sh"],
      "cwd": "crm",
      "port": 8790,
      "healthPath": "/health"
    }
  }
}
```

When **`supervised`** is `true`, enabling the plugin starts the process inside
Vault; disabling or removing it stops the process. Runtime status appears on the
plugin row as **`runtimeStatus`**. Vault assigns an internal port and passes
`VAULT_MCP_PORT` to the process (the manifest `port` is documentation only).

## Use Vault services

The optional TypeScript and Python helpers support scoped Vault service calls.
Declare only what is necessary:

```json
"services": ["memory.search", "memory.propose", "context.locale"]
```

Memory search returns only information allowed in the current user and
workspace. A memory proposal enters Vault's normal ingestion and review process;
it is not a direct database write. Correction and forgetting remain protected
operations. Capability tokens are short-lived and limited to the current plugin
invocation.

## Validate and inspect

Run these commands from the unzipped kit:

```bash
python3 -m cli.vault_plugin validate path/to/my-company.weather
python3 -m cli.vault_plugin inspect path/to/my-company.weather
```

`validate` catches missing files, unsupported fields, duplicate setting names,
embedded credentials, unsafe package paths, and unsupported MCP transports.
`inspect` summarizes what Vault will ask the owner to review.

## Package your plugin

```bash
python3 -m cli.vault_plugin package path/to/my-company.weather
```

The command creates a reproducible ZIP with the required single root folder.
It refuses to overwrite an existing ZIP so a previous release is not lost by
accident.

## Install and activate

1. Open **Library** in Vault and choose **Plugins**.
2. Select **Import plugin** and choose the ZIP.
3. Review the package result and confirm the installation.
4. Select the new plugin row.
5. Complete its simple settings.
6. Start the plugin's MCP service.
7. Select **Check tools**.
8. Choose whether each tool reads, changes, or deletes information.
9. Choose **Use with Voice**, **Use in background**, or both.

Installation alone grants nothing. Turning a plugin off withdraws its connected
tools. Third-party plugins can be removed; plugins built into Vault cannot.

## Update or remove

Import a ZIP with the same plugin name to replace it. Vault requires explicit
replacement confirmation. It validates the complete new package before using
it. Review settings and check tools again after a service or manifest change.

Turn a plugin off to pause it without deleting settings. Select **Remove** to
remove a third-party plugin and its managed connections, grants, and saved
credentials. When the plugin imported **`migration`** data, **Remove** also deletes
`extensions/data/{plugin.name}/`. Safe mode pauses every third-party capability together.

## Troubleshooting

**Vault cannot reach the plugin service:** Start the MCP service and confirm the
address in `mcp.json`. Docker-hosted Vault cannot use its own localhost address
to reach a service running directly on the computer.

**The ZIP is rejected:** Run `validate` locally. Confirm there is one root
folder and that `plugin.json` is directly inside it.

**A tool does not appear:** Turn the plugin on, choose **Check tools**, classify
the tool, and grant it to the agent you are using.

**An API call is unauthorized:** Save the secret in the plugin settings and
confirm `secretHeader` matches the header expected by the MCP service.

**A tool disappeared during a session:** The plugin, connection, grant, or safe
mode may have changed. Vault rejects calls immediately after access is removed.

## Compatibility and safety

The first kit release supports Agent Plugins 1.0.0, Agent Skills, and
Streamable HTTP MCP. It does not launch local stdio servers, run packaged source
inside Vault, provide plugin-controlled web UI, or include a public marketplace.

Plugins should fail clearly when their outside service is unavailable. They
must never assume they can see files, accounts, memory, or credentials unless
the current invocation explicitly provides that access.
