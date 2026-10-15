# Vault Grounding Baseline

Date: 2026-08-28  
Status: owner-directed grounding baseline; planning complete enough for donor research  
Implementation authority: donor research and bounded planning only

## Product definition

Vault already exists inside the ReSono Labs Voice platform. This repository is
the open-source, fully local distribution of that existing Vault runtime and
its Browser Voice interface. It is an extraction and cloud-detachment project,
not a new Vault design. The extracted platform preserves its existing Vault +
Voice product shape. It must operate without ReSono Labs
accounts, hosted authentication, cloud control-plane authority, hosted memory,
hosted management, or required ReSono infrastructure.

The first supported desktop/local installation may serve up to four local users. Each user has
an account and private workspace. Explicit workspace sharing is supported.
Shared memory is opt-in, scoped, attributable, and revocable.
All supported users may be active concurrently through independent sessions.
Each user's agent/capability execution, workspace, temporary files, memory and
credentials must remain inside the user/workspace sandbox adapted from the
existing Voice/Vault donor sandbox.

Voice/Vault does not donate multi-account identity. The four-account local
identity/session/workspace authority is explicitly `NEW` Vault work. It has no
MFA, email challenge, authenticator enrollment or cloud recovery path; do not
add one unless a later owner decision reopens that scope.

Vault may later serve as the primary canonical memory and credential store for other locally
or remotely connected agent systems, including Hermes, OpenClaw, and similar
owner-approved builds. This is an optional additional use case, not a change to
what the platform is. Vault + Voice remains complete by itself and no external
agent is required. When Hermes or OpenClaw is installed, it may use explicitly
granted Vault memory or credentials while the existing Voice experience remains
unchanged and available.

## Non-negotiable constraints

- Existing capabilities use the proven donor code already present in projects
  on this computer. Planning prose is not a substitute for porting that code.
- The default implementation action is copy/extract/port, preserving tested
  behavior and structure—not rewrite from memory or reimplement from a spec.
- No existing feature is reinvented, materially redesigned, or independently
  reimplemented for convenience, preference, cleanup, or novelty.
- Every ported feature requires an exact absolute donor-code path before work.
- New behavior is limited to needs that donors do not already solve and must be
  labeled `NEW` in the donor map.
- Security and privacy boundaries are enforced below the UI.
- Vault remains useful offline and has no required ReSono Labs touchpoint.
- Optional Hermes/OpenClaw memory or keystore use must not redefine, remove, or
  reorganize the existing Vault + Voice platform.
- The codebase and public documentation must be clean, logical, and auditable.
- Network routing mechanics are not part of the initial product-core design.
- External agents never receive implicit memory access merely because they run
  on the same device or can reach Vault over a network.

Permitted changes to donor code are limited to what Vault grounding requires:
removing ReSono-operated cloud coupling, adding local multi-user/workspace
authorization, creating OS-neutral boundaries, connecting the exact Browser
Voice presentation, and fixing a demonstrated security or portability defect.
Every such change must be recorded beside its donor path. A rewrite is blocked
unless direct inspection proves extraction is technically unsafe, incompatible
with the target platforms, or not authorized for public distribution.

Donor repositories are read-only. Vault work must never modify, reformat,
upgrade, delete, rename, or otherwise disturb donor files. Copy only the files
needed by the active accepted phase. All Vault-specific changes occur only in
this Vault repository after the copy and remain traceable to the untouched
source.

## User experience

Installation should be one simple operation. Onboarding and ongoing management
happen in a local web interface. Required onboarding is intentionally small:

1. local user's name; and
2. preferred interaction experience, such as strict, concise, warm, or funny.

After that required master setup, the master may optionally add secondary
accounts before entering Vault. Each secondary account is explicitly marked
`under_18` or `adult` for future use. This metadata has no current parental
control effect and Vault does not collect birth dates.

Onboarding then offers optional AI configuration for the master workspace using
the same encrypted provider credential boundary as later Connections
management. API-key setup is implemented first. OAuth and additional
MCP-backed model providers remain modular future adapters and may not depend on
ReSono Labs or create parallel credential stores.

Advanced models, voice, memory, integrations, extensions, backups, users, and
workspace settings remain optional management choices.

### Locked visual system

The entire user-facing web application must use the existing Browser Voice
visual system exactly. This is a direct visual port, not inspiration for a new
design. Preserve its layout, visual hierarchy, components, typography, spacing,
colors, responsive behavior, motion, and interaction patterns wherever the
corresponding screen exists.

Vault-specific local accounts, workspaces, memory, and settings may require new
data wiring or screens, but those additions must be composed from the same
Browser Voice patterns. Do not restyle, modernize, simplify, rebrand, or create
a parallel design system without a later explicit owner decision.

## Local authority and data boundary

The first onboarded account is the permanent master/device-owner account. It
controls installation, upgrades, secondary-user creation, password resets,
account removal, workspaces, extensions,
credentials, backups, and removal. Canonical state is stored locally. Secrets
must be encrypted at rest where platform facilities permit and must never enter
prompts, logs, extension manifests, or exported public configuration.

Management listens on loopback by default. Remote management is a later,
explicitly enabled revision using the same authenticated local management API;
it does not create a separate remote business-logic path.

Application row scoping is not by itself the required sandbox. On Linux,
executable agent/capability work must use the donor-derived Bubblewrap/process
boundary with clean environment, restricted mounts/network, resource limits
and brokered access. Only Voice Agent and Background Agent identities remain.

## System-agent boundary

Vault retains exactly two system agents: one **Voice Agent** and one
**Background Agent**. A system agent is a fixed owner-controlled runtime role
required for Vault operation. It is not an Agent Package, marketplace agent,
specialist, coordinator, generated agent, user-created agent, or Foundry
artifact. Donor labels such as `first_party` and `built_in` do not by themselves
make a donor agent a retained Vault system agent.

Use this role test before copying any donor agent code:

1. Does it implement the single interactive Voice runtime or the single generic
   Background runtime?
2. Is the identity fixed by Vault rather than created, installed, generated,
   published, selected, or delegated at runtime?
3. Can its capability be expressed as a tool, Skill, Plugin, MCP server, queue
   job, or ordinary service instead of another identity?

Only code that passes questions 1 and 2 is system-agent code. Question 3 is a
mandatory conversion/removal check: retain a required capability without
retaining its donor agent identity. A donor being developed or shipped by
ReSono Labs does not make it a system agent.

Remove every non-system agent. Do not include Agent Hub, specialist/packaged
agents, public or private developer agents, graph templates, or delegation to
installed agents. There is no Build Agent. Agent Foundry, agent-building,
generation, publication and build/validation pipelines are prohibited scope.
The Build Agent is excluded even if a donor describes it as built-in,
first-party, privileged, or system-owned. Vault builds are performed by the
normal repository build and release toolchain, not by an in-product agent.

Plugins, Skills, MCP connections and tools remain capabilities usable by the
two system agents; installing them never creates another agent identity.

The Voice Agent comes from the Voice Vault/Browser Voice session runtime. The
one Background Agent uses the fixed generic R1 Background Agent as its secondary
donor. This does not make R1 the Vault architecture and does not authorize any
R1 or Voice Build Agent, Foundry, coordinator or specialist agent.

## Canonical shared-memory role

Vault owns the canonical memory record, history, evidence, reconciliation,
retention, correction, and deletion state. Hermes, OpenClaw, and other agents
may use authenticated adapters to search or contribute memory, but they do not
become competing memory authorities.

External access must be:

- explicitly enabled by the device/workspace owner;
- bound to a distinct, revocable integration identity;
- scoped by user, workspace, visibility, operation, and—where needed—domain;
- attributable in memory evidence and audit history;
- subject to the same reconciliation and confirmation rules as Vault clients;
- immediately denied after membership or integration revocation; and
- available through a stable local service contract, with MCP as an optional
  adapter rather than the database or authorization boundary.

Shared storage does not mean one undifferentiated memory pool. Private user
memory remains private. Workspace memory is visible only to current authorized
members and integrations. An external agent's submitted memory is proposed
evidence until Vault's normal validation and reconciliation path accepts it.

## Proven capabilities to extract

The primary product donors are the ReSono Labs Voice platform's Vault runtime
and Browser Voice implementation:

- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/frontend/src/browser-voice/`

Vault is a standalone extraction of those systems **minus all ReSono cloud
authentication and required cloud control-plane behavior**. Local users,
password/session authentication, workspaces, management, runtime authority and
canonical data are owned by the installed Vault. Browser Voice retains its
exact visual system while its cloud login/session calls are replaced by local
Vault authentication and APIs.

R1 is a secondary donor only when direct inspection proves that the Voice Vault
runtime lacks a required local-only implementation. It is not the base product
architecture. Link/Tailscale remain optional later connectivity adapters.

One R1 contribution is explicitly required: merge the updated R1 memory system
into the existing Voice Vault memory architecture. Preserve all R1 memory
labeling and domains, memory types, source-authority labels, confidence,
sensitivity, evidence, versions, reconciliation states, retrieval behavior and
confirmation-protected correction/forgetting. This enriches Voice Vault memory;
it does not replace Voice's account/workspace scope or datastore architecture.

For memory and learning behavior specifically, the **updated R1 system is the
functional source of truth** because it is more advanced than the corresponding
Voice/Vault implementation. Voice remains the primary product donor and owns
the Vault storage, local identity, user, and workspace boundaries, but an older
or simpler Voice memory behavior must never replace, narrow, or downgrade an R1
memory capability. Where the two donors differ, retain R1 behavior and adapt it
only as required for Vault's PostgreSQL and multi-user authorization boundary.

### Mandatory memory and learning runtime

The complete memory-and-learning chain is a core Vault requirement. It is not
an optional plugin, a deferred integration, or a management-only feature. Both
fixed system agents participate in the same locally owned chain:

- the Voice Agent receives bounded, authorized memory at session start, can
  search it during the session, records the completed transcript and bounded
  tool evidence, and triggers review/reconciliation when the session closes;
- the Background Agent receives bounded, authorized memory relevant to its
  request, can search it through the same scoped tool, and records attributable
  bounded run evidence according to the updated R1 Background runtime; and
- learning is a runtime pipeline and capability service, **not a third agent**.
  A memory-review model call does not create another system-agent identity.

"Complete" means preserving the R1 domain labels, memory types,
source-authority labels, confidence, sensitivity, visibility, citations,
versions, lifecycle/reconciliation states, idempotent ingestion, retrieval,
and confirmation-protected correction and forgetting. The Voice account and
workspace authority remains the outer authorization boundary. Private memory
must never cross users; workspace memory must never cross workspaces.

The donor-parity execution chain is mandatory:

1. capture final user, assistant, and bounded tool transcript evidence;
2. close/finalize every completed Voice session, including failure/teardown
   paths where usable transcript evidence exists;
3. run the single R1 structured memory-review capability over cited evidence;
4. validate, reconcile, version, and persist accepted candidates;
5. build real embeddings when the configured provider is available while
   retaining truthful lexical retrieval when it is not; and
6. inject only scoped, bounded memories into future Voice and Background work.

R1 currently proves automatic post-session learning for Voice. It proves
memory references, lookup, and durable phase evidence for Background runs, but
not automatic conversion of Background output into canonical memory. Do not
invent that writeback path. It remains `BLOCKED/REOPEN` until an existing donor
implementation is located or the owner explicitly authorizes new behavior.

No phase is complete if it merely defines the schema or tools while leaving
this production chain unwired. No developer may replace it with a new learning
design when the donor implementation is available.

The controlling correction build contract is
`docs/planning/20-MANDATORY-R1-MEMORY-LEARNING-INTEGRATION-CONTRACT.md`.
Previous Phase 3 and Phase 4 exit evidence proves their isolated components but
does not prove this newly clarified end-to-end production requirement.

The authoritative statement of what is borrowed from each project is
`docs/planning/PROJECT-BORROWING-MATRIX.md`. No document may promote a secondary
donor above Voice Vault runtime or Browser Voice.

The controlling front-end donor is:

- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/frontend/src/browser-voice/`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/frontend/browser-voice.html`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/docs/NEW_BROWSER_VOICE_VISUAL_SYSTEM.md`

The detailed evidence and adaptation boundaries are in:

- `docs/research/2026-08-28-extension-imports-and-memory-architecture.md`
- `docs/planning/2026-08-28-extension-and-shared-memory-extraction-addendum.md`
- `docs/planning/FEATURE-DONOR-MAP.md`

## New or revised behavior

- `PORT + LOCAL ADAPTATION`: Voice account/workspace/session contracts, with
  ReSono cloud authentication removed and authority moved into local Vault.
- `REQUIRED MERGE`: updated R1 memory taxonomy and lifecycle into existing
  Voice Vault memory boundaries, retaining every documented label and domain.
- `NEW`: opt-in workspace/shared memory and revocable external memory access.
- `NEW`: integration identities and scoped memory access for Hermes, OpenClaw,
  and other owner-approved agents.
- `ADAPTATION`: remove all ReSono cloud ownership and single-user assumptions.
- `ADAPTATION`: simple local browser onboarding and management.
- `ADAPTATION`: cross-platform desktop/local packaging, Linux first if necessary.
- `OPTIONAL ADAPTER`: Link and Tailscale remote connectivity.
- `LATER REVISION`: remote management over the same local management contract.

Everything else must be traced to an inspected donor before it enters scope.

## Built-in personal capabilities

The only built-in personal application capabilities are **Mail, Contacts and
Calendar**. Mail must retain the Voice Vault's multi-account mail-client
behavior; it is not a single send-mail tool. These capabilities remain modular
services and tool adapters consumed by the two fixed system agents.

Do not include the donor External AI feature, social posting, recipes, local
events, markets, workouts, weather, news or other signal/tool families in the
standalone core. Recipes and local events may be evaluated later as optional
Plugins, but are not current features and must not be copied now. An
owner-selected Voice model provider is runtime infrastructure for the fixed
Voice Agent and is not the excluded External AI application feature.

## Platform and packaging target

Desktop/local packaging and release preparation remain part of the project.
The project is **not deployed to a hardware device**: do not flash images,
install onto an R1 appliance, target Android/device firmware, use fastboot,
create USB/udev device flows, or treat physical-device installation as an
acceptance gate. Linux desktop/local packaging is first; Windows and macOS may
follow without changing runtime behavior.

## Security baseline

- deny cross-user and cross-workspace access by default;
- scope queries in repositories/services, not after fetching;
- bind every session, tool call, memory operation, and integration to a local
  principal and workspace;
- enforce least-privilege memory read, propose, correct, forget, and
  administration grants separately;
- quarantine and validate imported extensions;
- separate MCP configuration from credentials and require explicit tool grants;
- default third-party extensions and remote access to disabled;
- preserve evidence, audit events, migrations, rollback, and recovery;
- expose no listener beyond loopback without explicit owner configuration; and
- support local backup, restore, export, deletion, and clean uninstall.

## Grounding gate

Feature implementation can begin only after the first feature slice has:

1. a defined contract and exclusions;
2. an inspected donor implementation with absolute source paths;
3. license/public-release review;
4. required Vault adaptations;
5. security counterexamples and acceptance tests; and
6. a bounded build contract.

Unresolved material questions stay `OPEN` or `CONDITIONAL`; they are not filled
in by developer preference.

## 2026-10-04 live memory, learned decisions, and chat change

Current change authority: original grounding r11 plus the bounded
[2026-10-07 Decisions/evidence amendment](docs/planning/2026-10-07-decisions-api-evidence-grounding.md),
LMD-DA-G-2026-10-07-r2. Decisions is documented; GPT-Live is excluded now.
Separate Chat/persistent Voice supersedes the old Home replacement interpretation.
The paragraph below is an initial historical checkpoint, not current phase or UX
authority. Current phase/next action is in PROJECT-STATE; no implementation added.

The owner-directed change grounding is
[docs/planning/2026-10-04-live-memory-decisions-grounding.md](docs/planning/2026-10-04-live-memory-decisions-grounding.md),
revision `LMD-G-2026-10-04-r5`. That record alone owns this change's
requirements, narrow Home-screen visual exception, material decisions and
unresolved choices. It does not supersede unrelated product boundaries or
authorize implementation. Source findings and verification limits are linked
there; no Decisions API schema or production readiness is asserted.
