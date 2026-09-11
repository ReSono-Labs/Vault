# Vault Plugin Kit Delivery Plan

Status: approved direction; implementation plan

Audience: Vault maintainers and release builders

User-facing companion to create: `docs/VAULT-PLUGIN-KIT.md`

## 1. Outcome

Vault will ship a complete, downloadable Plugin Kit that lets a developer build,
validate, package, install, configure, enable, disable, update, and remove a
third-party plugin without reading or changing the Vault source code.

The kit will use the standards Vault already supports:

- Agent Plugins for package identity and distribution;
- Skills for agent instructions;
- MCP for callable tools;
- Vault-owned grants for Voice and Background Agent access; and
- Vault-owned memory, confirmation, identity, audit, and configuration services.

Third-party code will run as an external MCP service. It will not execute inside
the Vault web or API process. This keeps Vault stable and makes plugin behavior,
network access, credentials, and agent access visible to the owner.

## 2. What already exists

Vault already has useful parts of a plugin platform:

- Agent Plugin `plugin.json` parsing and package import;
- ZIP and TAR archive import;
- embedded Skill discovery and activation;
- standalone Streamable HTTP MCP connections;
- MCP tool discovery and grants;
- dynamic tool projection to Voice and Background Agent;
- enable, disable, update, safe-mode, and removal lifecycle concepts;
- owner confirmation and capability boundaries; and
- user-facing extension management.

These foundations should be extended, not replaced.

## 3. Gaps that must be closed

### 3.1 Embedded MCP is not fully activated

An imported Agent Plugin may contain `mcp.json`, and Vault records that file as
a component. Today, however, the live MCP discovery and projection path operates
on standalone MCP extension records. The embedded MCP component is therefore not
guaranteed to become a live tool provider.

The fix is to create a managed child MCP connection for each embedded MCP
component and bind its entire lifecycle to the parent plugin.

### 3.2 No public development kit

There is currently no downloadable:

- manifest schema bundle;
- package validator;
- scaffolding command;
- packaging command;
- TypeScript or Python helper library;
- runnable starter plugin; or
- compatibility/version reference.

### 3.3 No plugin-owned settings contract

Plugins need a safe way to request simple settings such as locations, topics,
symbols, feed addresses, and API credentials. Vault must render this UI so every
plugin remains clean, consistent, mobile-friendly, and understandable.

### 3.4 No scoped Vault service SDK

Plugins need narrowly authorized ways to use Vault features without database
access or internal session credentials. Memory access is the first priority.

### 3.5 Current documentation describes format, not the full journey

The platform guide explains the basic Agent Plugin package, but it does not take
a developer from a new folder to an installed, configured, callable plugin.

## 4. Plugin package contract

The recommended package will be:

```text
my-plugin/
├── plugin.json
├── vault.json
├── config.schema.json          # optional
├── mcp.json                    # optional
├── skills/
│   └── my-skill/
│       └── SKILL.md            # optional
├── README.md
└── LICENSE
```

`plugin.json` remains the standard Agent Plugins identity manifest.
`vault.json` adds Vault-specific declarations without changing the standard.

### 4.1 `vault.json`

The first schema version will cover:

```json
{
  "$schema": "https://schemas.resonolabs.com/vault/plugin/v1.json",
  "minimumVaultVersion": "0.1.0",
  "agents": ["voice", "background"],
  "configuration": "config.schema.json",
  "mcp": "mcp.json",
  "services": ["memory.search", "memory.propose", "context.locale"]
}
```

Rules:

- undeclared services are denied;
- requested agent audiences are proposals, not automatic grants;
- Vault shows every requested capability before activation;
- unknown fields fail validation where ambiguity would affect security; and
- schema and minimum-version failures use plain, actionable messages.

## 5. Kit contents

The release artifact will contain:

```text
vault-plugin-kit-<version>/
├── README.md
├── LICENSE
├── schemas/
│   ├── plugin.schema.json
│   ├── vault.schema.json
│   └── config.schema.json
├── cli/
│   └── vault-plugin
├── sdk-typescript/
├── sdk-python/
├── starters/
│   ├── typescript/
│   └── python/
└── examples/
    ├── skill-only/
    ├── tool-and-settings/
    └── memory-aware/
```

### 5.1 CLI

The CLI will provide:

- `vault-plugin new` — create a clean starter project;
- `vault-plugin validate` — validate manifests, paths, schemas, and package size;
- `vault-plugin package` — produce an installable ZIP reproducibly;
- `vault-plugin inspect` — print the permissions and audiences users will see.

The validator must run without a live Vault installation.

### 5.2 TypeScript and Python SDKs

Both SDKs will expose the same small concepts:

- typed invocation context;
- reading declared configuration;
- registering MCP tools using standard SDKs;
- requesting a Vault service with a scoped token;
- structured success and user-readable errors;
- confirmation-aware operations; and
- health/readiness helpers.

They are convenience libraries, not mandatory runtimes. A standards-compliant
MCP server can integrate without either SDK.

### 5.3 Starter plugins

Each starter must run, explain every file, and contain no production secret.
Starters will demonstrate:

- a tool with no configuration;
- a tool using a simple saved setting;
- a secret-backed API call;
- a Skill plus MCP tool in one package;
- Voice-only, Background-only, and shared access; and
- scoped memory search and a proposed memory write.

## 6. Managed embedded MCP lifecycle

Installing a plugin containing `mcp.json` will create a managed MCP child owned
by the plugin. The owner should see one plugin, not two unrelated extensions.

Lifecycle behavior:

1. Validate the complete archive before writing state.
2. Create the parent plugin and its managed MCP child atomically.
3. Discover tools and show them in the plugin detail page.
4. Ask the owner which agents may use them.
5. Project only granted tools into Voice and/or Background Agent.
6. Disabling the plugin immediately removes every projected tool.
7. Re-enabling performs a health check and fresh discovery.
8. Updating stages and validates the replacement before switching.
9. Safe mode disables the child connection with the parent.
10. Removing a third-party plugin removes its child, settings, and grants while
    retaining only the minimum audit record required by Vault policy.

Built-in plugins remain non-deletable. Third-party plugins retain on/off and
delete controls.

## 7. User-friendly configuration

Plugins may declare these first-version field types:

- short text;
- long text;
- number;
- checkbox;
- single choice;
- multiple choice;
- URL;
- location;
- list; and
- secret/API key.

Each field may include a plain-language label, one-sentence explanation,
placeholder, default, required flag, validation limits, and a private marker.

Vault—not plugin HTML—renders the configuration page. This prevents visual
overlap and keeps desktop and mobile behavior consistent with the rest of Vault.
Secrets are never returned to the browser after saving. Vault supplies only the
specific declared secret to the MCP request header or credential exchange.

The plugin list remains simple: name, short purpose, status, on/off control, and
delete for third-party plugins. Clicking the row opens configuration, tools,
permissions, health, version, and update information.

## 8. Scoped Vault services

The initial SDK service surface will be deliberately small:

- `memory.search` — retrieve relevant memories the caller is allowed to see;
- `memory.propose` — submit information to Vault's existing ingestion/review path;
- `memory.correct` — propose a correction through confirmation policy;
- `memory.forget` — request deletion through confirmation policy;
- `context.locale` — obtain permitted locale, time zone, and unit preferences;
- `activity.report` — add a user-visible plugin activity record; and
- `confirmation.request` — request owner approval for a consequential action.

Plugins never receive database credentials, provider keys, browser session
cookies, unrestricted filesystem paths, or raw internal account identifiers.

Each invocation uses a short-lived, audience-bound capability token containing
only the plugin identity, allowed service, account scope, invocation identifier,
and expiration. Vault rechecks installed, enabled, and granted state on use.

Memory writes are proposals. Vault remains responsible for ingestion,
deduplication, review, provenance, correction, retention, and deletion.

## 9. Agent tool projection

Voice and Background Agent must share one authoritative tool catalog.

- On install or enable: discover tools, reconcile grants, refresh catalog.
- On configuration change: reconnect only when required, then refresh catalog.
- On disable, failure, or removal: withdraw tools immediately.
- On session start: build the provider tool declaration from current grants.
- During a session: reject calls whose plugin became unavailable or disabled.

OpenAI-specific realtime tool declarations must be refreshed through the
existing provider session update path. Other providers receive their equivalent
current tool declarations. Provider adapters must not invent separate plugin
permission rules.

## 10. Web Documents article

Add **Vault Plugin Kit** to the platform Documents index. It will be written for
someone who understands basic development but does not know Vault internals.

The multi-page article will contain:

1. What a Vault plugin is
2. What plugins can safely do
3. Download the Plugin Kit
4. Choose TypeScript or Python
5. Create your first plugin
6. Understand the package files
7. Add a Skill
8. Add an MCP tool
9. Add simple settings
10. Store API keys safely
11. Make tools available to Voice and Background Agent
12. Search Vault memory
13. Propose information for Vault memory
14. Validate and package
15. Install and test in Vault
16. Update, disable, and remove
17. Troubleshooting and compatibility

Every page will use short sections, copyable examples, and plain-language error
help. Multi-page navigation will retain the compact same-line Back and Next
buttons already required on mobile.

The download page will link directly to:

- full Plugin Kit ZIP;
- TypeScript starter ZIP;
- Python starter ZIP;
- JSON schemas; and
- checksum file.

## 11. Source layout

```text
plugin-kit/
├── schemas/
├── cli/
├── sdk-typescript/
├── sdk-python/
├── starters/
└── examples/

app/vault_runtime/extensions/
├── vault_manifest.py
├── plugin_configuration.py
├── managed_mcp.py
├── invocation_capabilities.py
└── vault_services.py

frontend/src/browser-voice/
└── PluginConfigurationPanel.tsx

docs/
└── VAULT-PLUGIN-KIT.md
```

The kit source stays separate from release archives. Generated ZIPs go under a
dedicated release directory and are not mixed with Vault application code.

## 12. Delivery sequence

### Milestone 1 — Contract and skeleton

- freeze `vault.json` and configuration schemas;
- add the `plugin-kit/` tree;
- implement `new`, `validate`, `inspect`, and `package`;
- create TypeScript and Python starters; and
- validate existing Agent Plugin packages without breaking compatibility.

Deliverable: a developer can create and package a structurally valid plugin.

### Milestone 2 — Complete embedded MCP wiring

- add managed child MCP persistence;
- connect parent lifecycle to discovery and projection;
- display tools and health inside the parent plugin detail page; and
- ensure enable/disable changes live Voice and Background tool availability.

Deliverable: an installed package exposes its granted MCP tools reliably.

### Milestone 3 — Settings and credentials

- render configuration schemas in the existing clean plugin detail UI;
- encrypt and redact secrets using Vault's established secret handling;
- pass only declared settings to the plugin; and
- add clear validation and connection feedback.

Deliverable: ordinary users can configure a plugin without editing files.

### Milestone 4 — Vault service SDK

- implement short-lived capability issuance and verification;
- expose the bounded memory, context, activity, and confirmation endpoints;
- publish matching TypeScript and Python clients; and
- add the memory-aware example.

Deliverable: plugins can use Vault features without internal access.

### Milestone 5 — Documents and release

- add the full user-facing article to Documents;
- publish downloads and checksums;
- run install, enable, tool invocation, disable, and removal smoke checks;
- verify desktop and mobile layout; and
- include the kit in the normal release assembly process.

Deliverable: the Plugin Kit is discoverable and usable from the product.

## 13. Acceptance criteria

The first Plugin Kit release is complete when:

- a developer can build a plugin from either starter without Vault source access;
- the offline validator catches malformed and unsafe packages clearly;
- Vault installs the package and renders its settings cleanly;
- secrets are saved without later exposure in the UI or logs;
- embedded MCP tools appear only for explicitly granted agents;
- Voice and Background Agent can call enabled tools;
- disabling a plugin withdraws its tools from new and active call paths;
- memory-aware plugins use Vault's ingestion path instead of direct writes;
- third-party plugins can be deleted and built-ins cannot;
- documentation and downloads are available inside Documents; and
- the same workflow works in the Docker and standalone Linux distributions.

## 14. Explicitly deferred

The first release will not include:

- arbitrary third-party Python or JavaScript inside the Vault process;
- plugin-provided HTML, CSS, or dashboard scripts;
- unrestricted filesystem, mail, calendar, contacts, or database access;
- local stdio MCP processes launched inside the production Vault container;
- a hosted marketplace, billing, ratings, or automatic public publishing;
- new agent identity types; or
- a large cross-platform test laboratory.

These omissions keep this version small without weakening the real plugin
contract. Standard MCP services may still run locally, elsewhere on the private
network, or remotely through an owner-approved private connection.

## 15. Immediate first build slice

Implementation should begin with Milestone 1 and the smallest necessary part of
Milestone 2 in one bounded slice:

1. add and validate `vault.json`;
2. scaffold the `plugin-kit/` directory and both starters;
3. create the four CLI commands;
4. turn an embedded `mcp.json` into a managed MCP child;
5. prove its tools enter and leave the shared catalog on enable/disable; and
6. write the first draft of `docs/VAULT-PLUGIN-KIT.md` alongside the code.

This sequence prevents publishing an SDK for a package lifecycle that does not
yet work end to end.
