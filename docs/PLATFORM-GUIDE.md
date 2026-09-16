# ReSono Labs Vault Platform Guide

Status: grounded against the repository and packaged web interface on 2026-09-11.

This is the canonical user, administrator, connection, agent, memory, and
extension guide for the current Vault package. It describes implemented
behavior only. A heading marked **Current limitation** documents a missing
supported operation; it is not an instruction to manipulate the database or
package files directly.

## Platform index

| Area | Summary |
| --- | --- |
| Installation | Installs one local Docker package containing Vault and a private PostgreSQL/pgvector database. |
| First-time setup | Uses a one-time local HTTPS setup link to create the permanent master account. |
| Accounts | Supports one permanent master and up to three secondary local accounts, each with a private workspace. |
| Provider access | The master can use one shared AI provider credential or assign an individual OpenAI API key to a secondary account. |
| Voice | The interactive Voice Agent uses the selected AI provider, scoped memory, and tools allowed for the signed-in account. |
| Background Agent | The fixed non-interactive agent performs bounded work with the selected text model and its allowed tools. |
| AI & Voice connections | Supports OpenAI, Gemini, and xAI provider configuration; OpenAI and Gemini support API or OAuth where configured. |
| Mail | Connects local IMAP/SMTP accounts with encrypted credentials and validated server access. |
| Calendar | Connects read-only ICS feeds or CalDAV accounts; Calendar entries remain scoped to the signed-in account/workspace. |
| Contacts | Built-in Voice tools search and perform confirmation-protected contact actions in the account's local data. |
| Vault Memory | Stores classified, scoped memory and can expose it to Hermes, OpenClaw, or compatible plugins. |
| Agent2Agent | Connects external A2A 1.0 agents by Agent Card URL for Voice or Background delegation and completion tracking. |
| Library | Imports Agent Plugins, Skills, hosted MCP packages (`mcp.package.json`), and external MCP connections. Import can ingest package SQLite/workspace data, copy files into Workspace, and prompt to link a computer folder. |
| Workspace | Opens the signed-in account's private files, including `local/` linked computer folders. |
| Settings | Turns Computer folders on or off for this browser and lists linked folders. |
| Documents and Vault Help | Opens the user-guide collection (this guide plus Windows, Link, local bridge, Hermes/OpenClaw memory, Plugin Kit, and MCP Package Kit) and a support assistant. |
| ReSono Labs Link | Pair Link Companion from External agents (or `sudo resono-link-connector companion setup vault`), then add ReSono Labs Vault in Link. After `agent-network setup` and Connect grants, Link apply fills External agents with those peers. Leftover Custom HTTP to `:8766` remains until cleanup. |
| Safe mode | Blocks all third-party capability projection without deleting installed extension records. |
| Backup and restore | Creates verified local backups of the database and private package data and restores only with an exact confirmation phrase. |
| Uninstall | Removes containers and the network while preserving production data volumes. |
| Factory reset | Permanently removes both production data volumes after an exact confirmation phrase. |

## 1. What Vault is

Vault is a local multi-user voice and agent platform. One installed runtime
serves all local accounts; it does not create a server or database per person.
User identity, workspace membership, memory, transcripts, Voice sessions,
Background runs, connections, extensions, and personal data are enforced by
user/workspace scope inside the shared runtime.

Vault has exactly two built-in system agents:

- **Voice Agent** — interactive browser voice sessions.
- **Background Agent** — non-interactive bounded tasks.

Plugins, Skills, MCP servers, tools, Hermes, OpenClaw, and A2A peers add
capabilities or external peers. They do not become additional Vault system
agents.

### Documents and Vault Help

Open **Documents** to read or download every user-facing Vault guide. The
dashboard collection is:

| Dashboard title | File | Audience |
| --- | --- | --- |
| Vault User Guide | this document | Owners and operators |
| Install Vault on Windows | `WINDOWS-INSTALLATION.md` | Windows Docker Desktop / WSL 2 |
| ReSono Labs Link | `RESONO-LABS-LINK.md` | Remote access via Link |
| Local Connection Bridge | `LOCAL-CONNECTION-BRIDGE.md` | Trusted local HTTP/WebSocket apps |
| Hermes & OpenClaw Memory | `HERMES-OPENCLAW-MEMORY.md` | External agent memory pairing |
| Vault Plugin Kit | `VAULT-PLUGIN-KIT.md` | Agent Plugin packages, `vault.json` ingestion |
| Vault MCP Package Kit | `VAULT-MCP-PACKAGE-KIT.md` | Hosted MCP packages, `mcp.package.json` ingestion |

Select **Ask Vault Help** for help using Vault, troubleshooting a problem, or
drafting a Plugin or MCP package. Vault Help searches this collection first,
including the Plugin Kit and MCP Package Kit.

Vault Help uses the text model configured for the signed-in account's selected
AI provider. It searches the complete dashboard-document index before checking
the packaged source snapshot. The source snapshot is read-only and only small
relevant excerpts are sent to the provider. Select the online-search option
when you want it to look for current Plugins, MCP servers, or other current
information.

Vault Help cannot silently install, enable, delete, or change anything. Plugin
and MCP changes still use the normal Library review and confirmation flow.


## 2. Requirements

The supported package workflow requires:

- a Linux host with Docker and Docker Compose available;
- `uv`, because `vault-package` invokes the Python package script through it;
- this repository checkout; and
- a browser able to reach the package HTTPS address.

The default installation binds Vault to `127.0.0.1:8765`. LAN installation
binds the HTTPS service to all host interfaces. PostgreSQL is never published
to the host by the production Compose file.

## 3. Install Vault

From the repository root:

```bash
./vault-package install
./vault-package setup
```

`install` builds the image, starts the package, waits for health, and preserves
existing production volumes. `setup` prints a one-time local HTTPS URL. Open
that URL in the browser; do not separate or redistribute the credential inside
it.

If the browser does not trust Vault's generated local certificate, the local
CA certificate is served by Vault at:

```text
https://127.0.0.1:8765/vault-local-ca.crt
```

Trust that CA using the operating system or browser's certificate-management
workflow. Do not disable TLS verification.

### LAN installation

```bash
./vault-package install --lan
./vault-package setup
```

The generated certificate includes the detected LAN address. LAN mode exposes
the Vault HTTPS port to the local network; it does not expose PostgreSQL.

## 4. First-time setup

The setup flow asks for:

1. the name Vault should use;
2. an experience style: Strict, Concise, Warm, or Funny;
3. a master-account username;
4. a password of at least 10 characters; and
5. password confirmation.

The first account is the permanent **master account**. It cannot be deleted by
the account-management interface. Vault also displays a generated local
recovery login once during onboarding; save it before continuing because it is
not sent to ReSono Labs and is not shown again.

After the master account is created, onboarding optionally offers secondary
accounts and AI provider configuration. Both can be completed later from
Accounts and Connections.

## 5. Sign in, sign out, and change a password

Sign in with a local username and password. Use the initials menu in the upper
right to open **Account** or **Logout**.

In **Accounts → Password**, user-managed accounts enter the current password
and a new password of at least 10 characters. A successful change revokes that
account's other active sessions. A master-managed secondary account cannot
change its own password.

## 6. Accounts and workspaces

### Account model

Vault supports four active accounts total:

- one permanent master account; and
- up to three secondary accounts.

Every account has its own fixed private workspace, storage roots, key material,
sessions, and data scope. Accounts share the installed Vault runtime, but their
private data is not automatically shared.

### What is private by default

The implemented repositories scope the following to the authenticated user and
workspace: memory, transcripts, session summaries, Voice sessions, Background
runs, Mail, Calendar, Contacts/personal records, A2A connections/tasks, external
memory integrations, and extension grants.

### What can be shared

The master AI provider credential can be used as a shared provider credential
by secondary accounts. This shares provider access, not the master's memory,
Mail, Calendar, Contacts, transcripts, or workspace files.

An account's memory contract supports `private` and `workspace` visibility.
The current product gives each account one fixed private workspace; it does not
provide a web workflow for joining another user's workspace.

### Workspace files and Computer folders

Open **Workspace**. The heading is **`{account name}'s Workspace`**. There is no
private-files subtitle.

The file list keeps the current folder name and **Swipe left for actions** at
the top. **Up one folder** appears at the bottom of the list when you are not at
the workspace root. Opening a file shows a preview or editor with **Close**.

**Settings** has **Computer folders**. When that is on, **Linked folders** is the
heading below the separator. **Add folder** links a host folder so it appears
under **`local/`** in Workspace. Voice can browse those folders while the Vault
tab is open. Linking needs a browser with a folder picker (Chrome or Edge).

A Plugin or companion plugin may also prompt during **Import** to link a folder
(`localShare`) or to copy packaged files into Workspace (`workspaceImport`).
Those are described under Library. Package-owned SQLite and runtime files
(`migration`) go into Vault package storage, not into the Workspace file list.

### How provider sharing actually resolves

Provider sharing is a credential-routing policy, not a data-sharing policy.
For every provider request, Vault first verifies that the account and workspace
membership are active. It then reads that account's access mode for the named
provider:

1. **Shared** — Vault resolves the provider record stored under the permanent
   master's workspace and uses it for the requesting account.
2. **Individual** — Vault resolves the provider record stored under the
   requesting account's own private workspace.

If no access-policy row exists, the implemented default is `shared`. Switching
from individual back to shared changes the routing policy; it does not copy the
master key into the secondary workspace. The model never receives the stored
database record, nonce, ciphertext, or workspace key. Vault decrypts only the
selected credential at the provider boundary.

The following remain separate even when two accounts use the same provider
token:

- selected provider per account workspace;
- Voice and Background sessions;
- memory and embeddings;
- Mail, Calendar, and Contacts;
- transcripts, summaries, and tool evidence;
- A2A and external-memory connections; and
- extension grants.

Shared provider use can therefore combine billing/quota at the provider while
preserving separate Vault data scopes. Provider-side account usage is governed
by that provider; Vault does not create separate provider billing identities
for users sharing one token.

### Shared versus separate authentication limits

The master Connections page stores shared API/OAuth provider configuration.
The current Accounts page can assign a separate **API key** for a secondary
account and currently targets OpenAI. It does not assign a separate ChatGPT or
Gemini OAuth identity to a secondary account. OAuth records are stored beside
the provider record in the effective provider workspace and follow that
provider record's shared/individual resolution.

An individual API key record carries its own realtime model, background model,
and voice settings. Selecting shared access returns to the shared provider's
settings. Vault does not merge shared model settings with an individual key.

### Add a secondary account

Open **Accounts → People and access**, select **Add user**, and enter:

- name;
- username;
- age group (`18 or older` or `Under 18`);
- password control; and
- experience style.

The age group is stored metadata only. It does not currently change agent
permissions or enable parental controls.

Password-control choices are:

- **User chooses from setup link** — Vault generates a one-time setup link,
  shown once. It expires after seven days and the user chooses a password.
- **Temporary password; change at login** — the master supplies a temporary
  password. The user must replace it before using protected platform routes.
- **Master-managed password** — the master supplies and controls the password;
  the user cannot change it.

### Reset a secondary account password

Open **Accounts**, select the account, choose **Reset password**, choose a
password-control mode, and apply the reset. Resetting revokes the account's
existing sessions and invalidates an earlier setup credential.

### Configure a secondary account's provider access

Select the secondary account and choose:

- **Use Vault shared key** — uses the provider credential configured by the
  master in Connections; or
- **Use an individual key** — stores an encrypted individual OpenAI API key in
  that account's private workspace.

The current account screen manages this policy for the OpenAI provider. It does
not expose per-secondary-account Gemini, xAI, or OAuth assignment.

### Delete a secondary account

Select the account and choose **Delete account**, then confirm. The implemented
repository marks the identity deleted, revokes sessions, deletes memberships
and owned workspaces, and deletes scoped Mail, Calendar, personal records,
memory, transcripts, Background/Voice data, provider access, and extension
grants. The master account cannot be targeted.

## 7. AI providers

Open **Connections**. The page heading is **Connected services**. Open the
**AI & Voice** tab (**Provider settings**). The selected provider runs Voice and
the Background Agent. Configure a realtime model, background text model, and
voice.

Supported provider adapters are:

| Provider | API access | OAuth access | Voice transport | Background text |
| --- | --- | --- | --- | --- |
| OpenAI | Yes | ChatGPT OAuth | WebRTC | OpenAI/Codex-compatible text path |
| Gemini | Yes | Gemini OAuth | Gemini Live WebSocket | Gemini `generateContent` |
| xAI | Yes | No current OAuth button | xAI Realtime WebSocket | OpenAI-compatible xAI API |

### Use an API key

Select the provider, enter its API key and model settings if you are using a
key, then choose **Save settings**. Keys are encrypted locally and never
returned to the browser. **Use provider** appears only when another configured
provider is selected and this one is not yet the active provider.

### Use ChatGPT OAuth

When ChatGPT OAuth is **not** connected, select OpenAI and choose **ChatGPT
OAuth**. Vault starts device authorization, opens the ChatGPT authorization
page, displays the code to enter, polls for completion, stores the resulting
OAuth tokens encrypted, and selects OAuth. After OAuth is connected, that
button is hidden and **Disconnect OAuth** is shown instead.

### Use Gemini OAuth

Gemini OAuth requires these package environment variables before Vault starts:

```text
VAULT_GOOGLE_OAUTH_CLIENT_ID=<Google OAuth web client ID>
VAULT_GOOGLE_OAUTH_CLIENT_SECRET=<Google OAuth web client secret>
```

Register this default redirect URI in the Google OAuth client:

```text
https://127.0.0.1:8765/providers/gemini/oauth/callback
```

For LAN use, the registered URI must exactly match the address used in the
browser. When Gemini OAuth is not connected, select Gemini and choose **Gemini
OAuth**. When it is connected, that button is hidden and **Disconnect OAuth**
is shown instead.

### Switch or disconnect authentication

API and OAuth credentials are encrypted in separate records. Adding one does
not erase the other. Save an API key with **Save settings** (leave the key
blank while OAuth is active to keep OAuth and only change models/voice).
**Disconnect OAuth** deletes only OAuth and falls back to a retained API key
when one exists. There is no **Use API key** or **Disconnect provider**
control on this page.

Embeddings are separate: real OpenAI embeddings use a retained OpenAI API key.
ChatGPT OAuth is not substituted as an embedding credential. Without a usable
embedding key, memory remains available through lexical retrieval.

### Embedding model, storage, repair, and fallback

Embeddings are a memory indexing capability, not a third system agent. There is
no “embedding agent.” The implemented embedding adapter is:

| Setting | Current implementation |
| --- | --- |
| Provider | OpenAI Embeddings API |
| Model | `text-embedding-3-small` |
| Dimensions | 1,536 |
| Input bound | 16,384 characters per item |
| Credential | Retained OpenAI API key resolved through the account's shared/individual policy |
| Storage | Scoped memory embedding row with provider, model, dimensions, vector, and content fingerprint |

The embedding credential is deliberately resolved independently from the
selected Voice/text provider. A user can select Gemini or xAI for Voice and
Background while Vault still uses a retained OpenAI API key for memory vectors.
If OpenAI OAuth is active for text/Voice, Vault still resolves the separately
retained API key for embeddings. If no OpenAI API key exists in the account's
effective provider scope, embeddings are unavailable.

When a memory is accepted, Vault attempts to embed its current content. An
embedding error does not discard the memory and does not mark memory ingestion
failed. The record remains available through lexical/exact retrieval. When
memory content is corrected or conflicted, Vault deletes its old vector so a
stale vector cannot continue matching new content.

Vault repairs missing or wrong-model vectors in two places:

- a package-start background backfill, up to 1,000 records per account scope;
- a bounded pre-search repair, up to 256 records by default.

Each vector is validated for numeric values and exactly 1,536 dimensions. A
provider error, rejected key, unreachable endpoint, invalid response, wrong
dimension, or individual record failure is counted/ignored for vector repair
without manufacturing a vector.

“Fallback” therefore means **retrieval fallback**, not model/provider failover:

1. Vault always performs scoped lexical ranking.
2. Exact query-to-key/content matches receive the highest exact score.
3. If the query embedding and stored vectors are available, Vault merges cosine
   semantic matches at or above the 0.20 similarity floor.
4. If embedding creation or query embedding fails, semantic candidates are
   omitted and lexical/exact results continue.

Vault does not currently select Gemini/xAI embedding models, rotate to a second
OpenAI embedding model, fabricate deterministic/hash vectors, or automatically
change vector dimensions. Changing the embedding model requires an explicit
future migration/reindex design; it is not an existing failover mechanism.

## 8. Voice

Open **Voice** and press **Touch to Start**. The browser requests microphone
permission and establishes the selected provider's realtime transport. Vault
supplies scoped instructions, account experience style, bounded startup memory,
and tools allowed for that account and Voice Agent.

Press the control again to end the session. Vault closes the provider session,
persists bounded transcripts/tool evidence, creates the session summary, and
runs memory review/finalization. Closing the browser or losing connectivity is
not a substitute for the normal close action.

## 9. Background Agent

The Background Agent is the one fixed non-interactive system agent. It uses the
selected provider's background text model, a frozen per-run tool set, autonomy
and tool-call limits, and a durable run lifecycle. It is not a user-installable
agent and extensions cannot create additional system-agent identities.

The current web UI reviews Background runs on the **Background Agent** page using
the R1 delegated-work layout (run logs and reasoning logs). It does
not submit work. Voice starts a goal after switching into Goal Intake; inbound
Agent2Agent can also enqueue a run. There is no Background submission form.

### Provider and model selection

At execution time, the Background Agent reads the provider selected for the
run's user/workspace. It then resolves that account's shared or individual
credential and the configured background model for that provider. The paths
are:

- OpenAI API through the OpenAI Agents SDK;
- ChatGPT OAuth through the ChatGPT Codex-compatible backend;
- Gemini through native `generateContent` and Gemini function calls; and
- xAI through its OpenAI-compatible API base.

There is no automatic provider failover. A missing credential, rejected token,
provider outage, invalid model, timeout, or invalid final output makes the run
fail with durable failure state. Vault does not silently charge or disclose the
request to a second provider.

### What a Background run contains

A run is not just a prompt. Its request records an objective, original request,
instruction profile, success criteria, expected result, scope, exclusions,
source requirements, verification method, completion conditions, stop
conditions, output schema, requested tool names, autonomy profile, recipe, and
hard limits. The final result must validate as Vault's typed Background output
with status, summary, requirement outcomes, unresolved issues, verification,
artifact references, and phase evidence.

The durable lifecycle supports accepted, queued, running, reviewing, repairing,
completed, failed, and cancelled states with legal transitions. The production
service has four worker threads. Startup recovery deals with interrupted durable
runs rather than inventing a successful result.

Default run bounds are 300 seconds, 24 model turns, 40 tool calls, two review
rounds, and 8 MiB of workspace output. The accepted maximums are 3,600 seconds,
100 model turns, 500 tool calls, 10 review rounds, and 256 MiB. Exceeding a
model-turn or time limit fails the run.

### How Background capabilities are selected

At run start, Vault freezes the intersection of:

1. tools currently visible to the Background Agent for that user/workspace,
   including MCP tools granted to Background (restored from durable grants
   immediately before the freeze);
2. exact tool names listed in the run request, or **all** matching Background
   tools when the request lists none (Voice `goal_start` uses this path);
3. the run's autonomy policy; and
4. the run's tool-call budget.

`limited` permits only read tools. `expanded` permits read and write tools.
`custom` permits requested read/write tools and any requested non-delete tool;
the implementation always excludes delete-effect tools from custom runs.
Invocation rechecks the allowed name and Background identity and records
started/completed/failed activity. A tool-result error still consumes a tool
call because the provider attempted the call.

Built-in tools available to Background by audience include memory lookup,
memory evidence explanation, web search, Mail, Contacts, Calendar, Tasks,
workspace files, enabled built-in plugins, and A2A list/send. Voice-only tools
include Goal Intake (`goal_start` / inspect / cancel), `voice_mode_switch`,
explicit remember, and confirmation-based memory correction/forget. An imported
Skill or MCP tool reaches Background only when its lifecycle, user/workspace
audience, safe-mode state, and grant all permit it; installation alone is
insufficient.

### Background memory context

Before the first model turn, Vault searches scoped memory using the objective,
original request, and context summary. At most eight authorized matches are
frozen into the run context, and their memory IDs are recorded in the activity
timeline. The model receives content and classification fields, not unrestricted
database access. Later memory changes do not mutate the already frozen context
for that run.

## 10. Mail

Open **Connections → Mail → Add mail account**. Enter:

- account name and email address;
- IMAP host, port, username, and password;
- SMTP host, port, username, and password.

Vault uses TLS for both connections, validates the supplied servers before
saving, and encrypts credentials locally. Multiple accounts are supported.
Voice Mail tools can list folders, check/search/read messages and attachments,
compose pending sends, confirm sends, mark read/unread, archive, create/rename
folders, and move messages. Sending remains confirmation-protected.

**Current limitation:** the web interface and local Mail management API do not
currently expose removal of a connected Mail account. Do not delete Mail rows
directly from PostgreSQL.

## 11. Calendar

Open **Connections → Calendar → Add calendar**.

For an ICS feed, provide a name and HTTPS feed address. ICS is read-only. For
CalDAV, provide a name, calendar URL if required, username, and password or app
password. Credentials are encrypted locally and the connection is validated.

Use **Remove** beside a Calendar connection to delete it. Calendar tools expose
scoped calendar reads and the implemented confirmation-protected create path;
provider capabilities still determine what succeeds.

## 12. Contacts

Contacts are a built-in local capability rather than a Connections form. Voice
tools can search local contacts and prepare/confirm save, update, delete, or
field-use actions. Mutating or using contact data follows the pending-action
confirmation flow.

The current web interface has no standalone Contacts management page.

## 13. Memory

Vault classifies accepted memories by domain, type, authority, confidence,
sensitivity, intent, and visibility. Supported domains are identity, personal,
relationship, environment, project, device, and platform. Types are fact,
preference, decision, episode, constraint, and correction.

Memory is derived from cited transcript evidence or explicit tool/user actions.
Sensitive/transient content is bounded by the reviewer rules. Correction and
forget operations use the memory action flow rather than unscoped database
writes.

### Memory review is a capability, not another agent

Vault does not create a separate Memory Agent identity. At Voice finalization
or external proposal ingestion, a structured memory-review capability uses the
account's selected provider and configured background model. It can therefore
run through OpenAI API, ChatGPT OAuth/Codex, Gemini, or xAI just like the fixed
Background model path. The reviewer is named in model execution for tracing,
but it has no agent registration, inbox, independent goals, or tool catalog.

There is no provider failover for review. If the selected review provider fails
or returns malformed/unsupported structured output, the review fails explicitly;
Vault does not send that transcript to another provider. Embedding failure is
handled separately and does not invalidate an otherwise accepted review.

### What the reviewer produces

The reviewer receives a completed, indexed transcript capped at 100,000
characters. It must return contract version 2, a session summary, and at most
32 candidates. Every candidate includes:

- domain and memory type;
- stable key and bounded content;
- exact source transcript entry indexes;
- source authority;
- confidence and sensitivity;
- reconciliation intent;
- whether the candidate should be stored; and
- optional comparison/time fields in the provider output.

Candidates marked `shouldStore=false`, missing valid citations, using invalid
labels, lacking a stable key/content, or containing forbidden secret markers
are discarded before persistence. Candidate content is capped at 4,096
characters and stable keys are normalized to lowercase letters, numbers, dots,
underscores, and hyphens, with a 120-character limit.

### Classification fields

**Domain** answers “what part of life/system is this about?”

| Domain | Stored meaning |
| --- | --- |
| `identity` | Explicit stable identity information |
| `personal` | Durable personal facts or preferences |
| `relationship` | Explicit people, organization, or relationship roles |
| `environment` | Stable user environment/setup information |
| `project` | Durable project scope, terminology, decisions, or constraints |
| `device` | Durable device configuration or facts |
| `platform` | Owner-accepted ReSono platform decisions or constraints |

**Memory type** answers “what kind of statement is it?”: `fact`, `preference`,
`decision`, `episode`, `constraint`, or `correction`.

**Source authority** records why Vault may trust it:

- `user_asserted` — stated directly by the user;
- `tool_verified` — supported by a verified tool result;
- `model_derived` — derived by model review and lower authority than explicit
  current user statements or verified tools.

**Confidence** is `low`, `medium`, or `high`. **Sensitivity** is `normal` or
`sensitive`. **Visibility** is `private` or `workspace`; automatic reviewer
candidates currently persist as `private`.

**Reconciliation intent** controls how the stable key is handled:

- `create` — create a new canonical record when none exists;
- `confirm` — reinforce an existing value;
- `correct` — replace the current value and return it to active state;
- `conflict` — preserve that competing evidence exists rather than guessing.

### What Vault deliberately does not remember

Reviewer instructions exclude live tool-owned status, Mail/Calendar records,
source files, temporary plans, greetings, one-time requests, assistant
recommendations, unsupported inference, credentials, payment information, and
other secret material. An empty candidate list is valid when a conversation
contains nothing durable. Explicit “remember this” intent raises priority but
does not override secret or inappropriate-content rejection.

### Evidence, versions, conflicts, and idempotency

Every accepted candidate must cite exact transcript entries. Vault stores the
current memory record, an immutable version row, and evidence rows containing
evidence kind, authority, bounded excerpt, and transcript reference.

The canonical identity of a memory is its workspace, visibility owner, subject,
domain, type, and stable key. Repeating the same content normally reinforces
confidence/authority without creating a competing value. Changed content
creates a new version. A `correct` intent makes the new version active; other
changed content becomes conflicted. Conflicted records are excluded from active
profile/retrieval queries until reconciled.

Finalization fingerprints the transcript. A completed fingerprint is not
ingested twice, and concurrent attempts must claim ingestion before writing.
Invalid citation indexes are skipped. Session summary storage and candidate/
stored counts remain durable even when individual embedding calls fail.

### Startup memory and ordinary retrieval

Startup context is a bounded profile, not a full memory dump. Vault selects up
to eight active, normal-sensitivity, medium/high-confidence records, prioritizing
identity, personal, relationship, environment, platform, project, then other
domains, with recent records first inside that order. Hermes and OpenClaw use
the same profile endpoint when startup memory is enabled.

Ordinary memory search combines lexical, exact, and available semantic matches,
caps results at 25, and always enforces the calling user/workspace scope.
Voice and Background can look up memory and explain the stored evidence.
Background can read/explain but cannot use the Voice-only mutation sequence.

### Correction and forgetting

Voice correction/forgetting is a two-step confirmation flow. The first user
utterance prepares a pending action for one exact memory. A later user
transcript entry in the same Voice session must confirm it. Only then does Vault
apply the correction or delete the memory. A correction is recorded as
high-confidence `user_asserted` evidence and invalidates the old embedding.

External-memory adapters are different by explicit product decision: when a
user connects Vault to Hermes/OpenClaw with `correct` and `forget` grants, those
scoped operations are pre-authorized until revocation. Every request still
requires the integration credential, exact grant, active workspace membership,
and a unique bounded request ID. External proposals go through the same
structured reviewer and reconciliation pipeline rather than writing a raw
memory row directly.

### Connect Hermes or OpenClaw through pairing

Install the appropriate adapter, run its pairing command, sign in to Vault in
the browser page it opens, and choose **Connect**. The adapter receives a scoped
credential without requiring copy/paste. The grants are search, propose,
correct, and forget. External proposals are automatically processed until the
connection is revoked.

Hermes adapter directory:

```text
integrations/hermes-vault-memory/
```

OpenClaw adapter directory:

```text
integrations/openclaw-vault-memory/
```

Both adapters enable bounded startup memory by default. Their README files
contain the agent-specific installation and memory-slot/provider selection
steps.

### Create a credential manually

Open **Memory → Add agent memory**, provide a connection name and adapter name,
then choose **Create agent access**. Copy the credential immediately; Vault
shows it once. Manual credentials are intended for compatible adapter setup
when pairing is not used.

### Revoke and remove memory access

Choose **Revoke** to stop future operations immediately. A revoked row remains
visible for audit/cleanup. Choose **Remove** on the revoked row to delete it
from the list. For a clean Hermes/OpenClaw disconnect, also run that adapter's
disconnect command so its local credential and active memory selection are
removed/restored.

## 14. Agent2Agent

Vault implements A2A 1.0 as a Built into Vault option (default off). Voice and
Background share outbound `agent2agent_list` and `agent2agent_send`. When the
option is on, Vault also serves a loopback Agent Card and JSON-RPC so a peer can
`SendMessage` this Vault; inbound work runs as the Background text agent, not
Voice. **Setup for this pass is port numbers:** inbound Card at
`http://127.0.0.1:8768/.well-known/agent-card.json` (port override
`RESONO_VAULT_A2A_LISTEN_PORT`, Docker host override `VAULT_A2A_PORT`) plus the inbound bearer shown on the Agent2Agent
page; outbound is Connect agent with the peer’s Card URL (another loopback port
is enough). The Docker package publishes that host loopback port and binds the
listener on all container interfaces (`RESONO_VAULT_RUNTIME_PUBLISH_PORTS`); the
Agent Card URL stays `127.0.0.1`. Standalone Vault still binds loopback only.
Accepting inbound work still requires the Agent2Agent option on. A Link Agent
profile is optional later and is not required for A2A to work. Dashboard Custom
HTTP on `:8766` is the Vault UI tunnel, not A2A.

### Connect an agent

Open **Agent2Agent → Connect agent** and enter:

- a display name;
- the peer's Agent Card URL; and
- a bearer token if the card endpoint/RPC endpoint requires one.

Vault validates the Agent Card, requires the supported JSON-RPC A2A interface,
stores the card, and encrypts the bearer credential. Local peers and remote
peers use this same connection form and protocol. A local container typically
reaches host agents through `host.docker.internal`; remote routing must already
provide a reachable approved HTTPS address, such as a configured Link,
Tailscale, or reverse proxy.

Select a connected agent row to inspect its Agent Card, protocol, URL, version,
and advertised skills. Choose **Remove connection** to delete the connection,
credential, continuity, and related task records.

### Continuity and completion

Vault preserves the A2A context by external connection, user/workspace, caller
kind, and Voice session or Background run. Asynchronous work continues after a
Voice session disconnects. A background poller stores terminal state, summary,
or issue. The page shows the five latest completed requests; select a row for
the full saved review.

## 15. Library: Plugins, Skills, MCP, and Tools

Open **Library** in the app navigation. The page heading is **Agent
capabilities**. Select Skills, Plugins, MCP, or Tools. Only the master can
mutate extension installation or credentials. Installed capabilities target
only Voice and/or Background; they do not register agents.

### Standards

- **Agent Plugins:** pinned Agent Plugins 1.0.0 manifests using
  `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`.
- **Agent Skills:** `SKILL.md` with public Agent Skills-style YAML frontmatter,
  metadata-first discovery, and just-in-time instruction loading.
- **MCP:** hosted packages use `mcp.package.json` (ZIP/TAR import, supervised process);
  connection-only rows use pinned Agent Plugins 1.0.0 `mcp.json`. Runtime negotiation
  uses MCP protocol revision `2025-11-25`.
- **A2A:** outbound Agent2Agent JSON-RPC protocol version 1.0 with Agent Cards.

### Import a Skill

Create one root directory whose name matches the Skill `name`. Add `SKILL.md`
at that root. It must start with closed YAML frontmatter containing:

```yaml
---
name: example-skill
description: What this skill does.
---
Instructions begin here.
```

Optional supported frontmatter fields are `license`, `compatibility`,
`metadata`, and `allowed-tools`. `allowed-tools` is descriptive and grants
nothing. Package the one root directory as ZIP or TAR, choose **Import skill**,
review replacement confirmation if applicable, then enable the installed row.
No Skill script executes automatically.

### Create and import a Plugin

Use **Library → Plugin → Import plugin** with a ZIP or TAR that contains exactly
one root folder and `plugin.json` at that root. The installed row appears under
**Plugins** only — never under MCP.

A Plugin archive must have exactly one root directory with `plugin.json` at its
root. Minimal manifest:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "example-plugin",
  "version": "1.0.0",
  "description": "Example capability bundle"
}
```

The name must satisfy the pinned schema. A Plugin's recognized embedded
component locations are:

```text
example-plugin/
  plugin.json
  vault.json                 Optional — agents, services, migration, settings schema
  config.schema.json
  skills/
    example-skill/
      SKILL.md
  migration/                 Optional — hydrated to extensions/data/{name}/
  mcp.json                   Optional — external MCP connection only
```

Optional **`migration`** in `vault.json` imports SQLite and/or workspace files
from the zip into `extensions/data/{plugin.name}/` (same rules as hosted MCP
packages). Vault asks before overwriting existing package data. **Remove plugin**
deletes imported package data as well as the plugin code.

Before installing a Plugin, Vault checks its structure and reviews the files
without opening or running them. The review looks for packaged credentials,
scripts, and instructions that may be trying to override normal safety rules.
Plugin files are always treated as untrusted, and installing a Plugin does not
give it permission to run or access your information.

The current Library screen does not yet show the detailed review report. Only
install Plugins from a source you trust, leave them turned off until you have
reviewed what they provide, and use **Connections → Extensions** to turn on
safe mode if anything looks unexpected.

Developers can open **Vault Plugin Kit** for Agent Plugin packages (including
`vault.json` migration, Workspace import, and local folder linking). Open
**Vault MCP Package Kit** for hosted MCP packages (`mcp.package.json`),
supervised sidecars, companion plugins, and the same package-data **migration**
contract.

### Package ingestion on import

Import can move three different kinds of content. They are not interchangeable:

| What the package declares | Where it lands | Who sees it |
| --- | --- | --- |
| **`migration`** (SQLite and/or a `migration/workspace` tree) | `extensions/data/{package name}/` | The hosted MCP/plugin runtime (`RESONO_DB`, `RESONO_WORKSPACE`). Not the Workspace file list. |
| **`workspaceImport`** (on `vault.json`, including a companion plugin) | The account's Vault Workspace files | Owners in **Workspace**. |
| **`localShare`** (on `vault.json`) | No copy into Docker; a **`local/{name}/…`** mount | Owners in **Workspace → local/** after they confirm the folder picker. |

Vault asks before overwriting when the package uses `onConflict: ask`.
**Remove plugin** or **Remove MCP package** deletes **`migration`** package data
for that name. Workspace files copied by **`workspaceImport`** remain in the
account workspace unless the owner deletes them. Linked **`localShare`** mounts
remain until removed in Settings or the related plugin is removed.

Hosted MCP **file tools** do not automatically receive a linked folder path.
The companion plugin can prompt for `localShare`; the MCP server must resolve
`local/…` itself. See **Vault MCP Package Kit**.

### Import a hosted MCP package

Use **Library → MCP → Import package** with a ZIP or TAR that contains exactly
one root folder and `mcp.package.json` at that root. Vault validates the
archive, may copy optional **migration** data (SQLite and/or workspace files)
into package storage, and installs the MCP row **disabled**.

Typical owner flow:

1. Import the package and confirm any migration replacement prompt.
2. Open the MCP row → save **Settings** (from the package `config.schema.json`).
3. **Turn on** — Vault starts the supervised process and checks `/health`.
4. **Check tools** — grant discovered tools to Voice and/or Background Agent.
5. If the zip included a **companion plugin**, it is linked to the MCP row:
   turning the MCP on or off applies to both; grant **skills** on **Library → Plugin**.

A single zip may install both an MCP row (tools, runtime, package data) and a
companion plugin row (skills). **Removing the MCP package also removes the linked
companion plugin by default**, including package code, SQLite, and workspace
files under that package. Removing the plugin alone does not remove the MCP.

Large products may ship **multiple hosted packages** (for example separate
Business workspace and CRM database packages). Import each zip independently.
See **Vault MCP Package Kit** for the developer contract.

Settings that start the supervised process must be saved on the **MCP row**, not
only on the companion plugin row.

### Import an external MCP connection (`mcp.json`)

For an MCP server you run outside Vault (no supervised process, no package
migration), import a UTF-8 `mcp.json` file. Minimal Streamable HTTP example:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "example": {
      "type": "streamable-http",
      "url": "https://example.test/mcp"
    }
  }
}
```

Streamable HTTP is the only MCP connection type that currently runs. Remote
connections must use HTTPS. Vault blocks addresses that point into private
networks or common cloud credential services so that an imported connection
cannot quietly reach other devices or services.

For trusted software running on the same computer, use `localhost` when Vault
runs directly. A Docker-installed Vault can reach trusted software on the host
through `host.docker.internal`. Do not use that address for software you do not
trust. Add credentials through Vault's connection controls rather than placing
passwords or tokens in the URL or `mcp.json` file.

Do not use connection-only import for in-Vault Business or CRM sidecars that
need migration, settings, or a supervised process — use **Import package**
with an `mcp.package.json` archive instead.

### Import safety and lifecycle

Plugin and Skill archives accept ZIP or TAR and must contain exactly one root.
Vault rejects traversal, links, special/encrypted entries, duplicate folded
paths, oversized files, excessive expansion/compression, and multiple roots.
Preflight approval is one-use, expires, is bound to the account/workspace and
candidate/current hashes, and requires explicit replacement confirmation.

Installed rows can be enabled or disabled from Library. Safe mode suppresses
all third-party runtime projection without deleting records. The Tools tab is
read-only and groups available tools into collapsed functional categories.

Select an imported Plugin to complete its settings and safely save any declared
API key. If the plugin declares an external MCP connection, start that service,
choose **Check tools**, identify whether each tool reads, changes, or deletes
information, and choose whether Voice, Background Agent, or both may use it.
Third-party Plugins include **On/Off** and **Remove** controls. **Remove**
deletes imported **`migration`** package data (`extensions/data/{name}/`) when
present, as well as plugin code and grants. Built-in Plugins can be turned on or
off but cannot be deleted.

Developers can open **Vault Plugin Kit** for Agent Plugin packages and
**Vault MCP Package Kit** for hosted MCP packages, supervised sidecars, and
companion plugins.

## 16. Connections safe mode

Open **Connections → Extensions**. When third-party safe mode is on, external
capabilities are blocked. Turning it off permits only explicitly enabled and
granted capabilities; installation or discovery alone grants nothing.

## 17. Package operation

```bash
./vault-package status
./vault-package logs
./vault-package stop
./vault-package start
```

`logs` displays the latest 200 Vault and PostgreSQL log lines. Re-running
`install` rebuilds/upgrades the image without deleting production volumes.

### Backup

```bash
./vault-package backup
```

Vault starts the package if necessary and writes a timestamped directory under
`.runtime/package-backups/`. It contains a PostgreSQL custom dump, encrypted
private/package roots, and a SHA-256 manifest.

### Restore

```bash
./vault-package restore .runtime/package-backups/<timestamp> \
  --confirm "RESTORE VAULT BACKUP"
```

Restore verifies the manifest, stops Vault, replaces backed-up private package
data, restores PostgreSQL, restarts the package, and requires a passing health
check. Current data is replaced by the backup.

### Uninstall while preserving data

```bash
./vault-package uninstall
```

This removes package containers and the Compose network. It preserves both
production data volumes. A later install reuses them.

### Factory reset

```bash
./vault-package factory-reset --confirm "DELETE ALL VAULT DATA"
```

This permanently removes production containers, network, and both production
data volumes. The supported equivalent is:

```bash
./vault-package uninstall --delete-data --confirm "DELETE ALL VAULT DATA"
```

Factory reset is destructive and is not recoverable unless a separate valid
backup exists.

## 18. Security and privacy boundaries

- Provider, Mail, Calendar, A2A, external-memory, and extension credentials are
  encrypted locally and are not returned after storage.
- The production service runs as a non-root container user, drops Linux
  capabilities, and uses `no-new-privileges`.
- Imported process execution fails closed when the required Bubblewrap nested
  namespace is unavailable; Vault does not run it unsandboxed.
- Do not add Docker socket mounts, privileged mode, or broad `SYS_ADMIN` to make
  imported executables run.
- Remote MCP requires HTTPS; Vault's local memory adapters do not disable TLS
  verification.
- Discovery, manifests, Agent Skill `allowed-tools`, and MCP annotations do not
  grant authority.

## 19. Common issues

### A Plugin or Skill will not import

- Make sure the upload is a ZIP or TAR archive with one top-level folder.
- A Plugin needs `plugin.json` inside that folder. A Skill needs `SKILL.md`.
- Remove password files, private keys, API keys, installers, and unrelated
  files from the package.
- Download the package again from a trusted source if the archive may be
  damaged or incomplete.
- If the package still fails, keep it disabled and ask **Vault Help** what the
  expected package layout is.

### An MCP connection says its address is blocked

Vault blocks private-network and cloud-credential addresses by design. For a
remote MCP service, use the service's normal public HTTPS URL. For trusted
software on the same computer, use `localhost` with a direct installation or
`host.docker.internal` with the Docker package. Do not work around the warning
by exposing a private service publicly.

### A newly imported capability does not appear in Voice

Importing does not automatically grant access. Check that the item is enabled,
that safe mode is off, and that the capability is allowed for Voice or the
Background Agent. Start a new Voice session after changing capabilities,
because an existing session keeps the tool list it started with.

### Import asks to link a folder or copy files into Workspace

That is package **ingestion**, not a failed install. **Link a folder** uses
Computer folders (`local/` in Workspace). **Copy into Workspace** writes owner
files you can open under Workspace. Package SQLite still goes into hidden
package data. You can skip an optional folder link unless the package marks it
required.

### Signing in works over HTTPS but not through the local bridge

Use `https://127.0.0.1:8765` in a browser. The HTTP bridge at
`http://127.0.0.1:8766` is intended for trusted local applications that cannot
use Vault's local certificate. If a browser session becomes confused after
switching addresses, sign out, close the Vault tabs, and sign in again at the
HTTPS address.

### Vault does not open after an update

Run `./vault-package status`, followed by `./vault-package logs`. If a service
is stopped, run `./vault-package start`. Re-running `./vault-package install`
rebuilds the package without deleting saved Vault data.

## 20. Current supported limitations

- Four active local accounts maximum.
- No cloud account, email-based recovery, MFA, or security questions.
- Age classification does not yet implement parental controls.
- No general shared-workspace selection between different users.
- No Background Agent submission form in the current web UI; Voice (and inbound
  Agent2Agent) start runs. The Background page tracks progress only.
- No standalone Contacts management page.
- No supported Mail-account removal control.
- Streamable HTTP is the only executable MCP transport.
- Full extension grant/credential/removal administration is not exposed in the
  current Library page.
- Detailed Plugin review findings are not yet displayed by the current Library
  import screen.
- A2A outbound tools, new agent connections, and the inbound loopback Agent Card require the built-in Agent2Agent option (default off). Inbound HTTP requires `Authorization: Bearer` with this Vault's inbound token (not a browser cookie, Basic auth, or an outbound peer token). Inbound tasks execute as the Background text agent. Standalone binds `127.0.0.1:8768`; Docker publishes host `127.0.0.1:8768` (`VAULT_A2A_PORT`) so a host connector can reach the Card. Docker outbound to Link Agent Network uses the packaged connector CONNECT hop; operators do not set peer URLs to `host.docker.internal`.
- Collab runs automatically with Agent2Agent (no separate option). It waits for a connected peer's turn using the Hermes coordinator; it does not replace `agent2agent_send`.
- Remote A2A routing is not created by Vault; the operator supplies the
  reachable HTTPS route.
- ChatGPT OAuth does not replace an OpenAI API key for embeddings.

## 21. Grounding references

This guide was cross-checked against these implementation authorities:

- `scripts/vault_package.py` and `compose.yml`;
- `frontend/src/browser-voice/BrowserVoiceApp.tsx`;
- `frontend/src/browser-voice/AccountPanel.tsx`;
- `frontend/src/browser-voice/ConnectionsPanel.tsx`;
- `frontend/src/browser-voice/MemoryPanel.tsx`;
- `frontend/src/browser-voice/CapabilitiesPanel.tsx`;
- `frontend/src/browser-voice/DocumentsPanel.tsx`;
- `frontend/src/browser-voice/SettingsPanel.tsx`;
- `frontend/src/browser-voice/BrowserWorkspaceFileBrowser.tsx`;
- `docs/VAULT-PLUGIN-KIT.md`;
- `docs/VAULT-MCP-PACKAGE-KIT.md`;
- `app/vault_runtime/extensions/standards/vault.schema.json`;
- `app/vault_runtime/extensions/standards/mcp.package.schema.json`;
- `app/vault_runtime/local_api/app.py`;
- `app/vault_runtime/local_identity/repository.py`;
- `app/vault_runtime/system_agents/inventory.py`;
- `app/vault_runtime/memory/contracts.py`;
- `app/vault_runtime/extensions/specification.py`;
- `app/vault_runtime/extensions/skills.py`;
- `app/vault_runtime/extensions/mcp_config.py`;
- `app/vault_runtime/agent_network/service.py`; and
- the Hermes/OpenClaw adapter README files under `integrations/`.
