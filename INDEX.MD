# ReSono Labs Vault Index

Current live-memory/Chat/Decisions entry:
[source-of-truth document set](docs/planning/2026-10-07-live-memory-document-authority.md).
Original October4–5 grounding controls the goal; one current owner per concern.

Current live-memory change: original grounding r11 supplemented by
`docs/planning/2026-10-07-decisions-api-evidence-grounding.md`. PROJECT-STATE owns
current phase; older Phase00-only statements below are historical. No runtime
module locations or ownership changed in this documentation amendment.

Vault is a fully local, standalone voice and agent platform intended for public
open-source release. Optional Hermes/OpenClaw memory and credential access is an
additional use case, not a redefinition of the platform. This file is the short
repository map. Detailed decisions belong under `docs/`.

## Current structure

| Path | Owner |
|---|---|
| `GROUNDING.md` | Controlling product boundary and accepted facts |
| `SKILLS.MD` | Mandatory developer, agent, security, packaging, and no-device-deployment rules |
| `INDEX.MD` | Concise repository structure and ownership map |
| `README.md`, `LICENSE.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md` | Public release orientation, rights, reporting, contribution and release-history boundary |
| `docs/README.md` | Documentation map and document authority |
| `docs/PLATFORM-GUIDE.md` | Canonical grounded user/admin guide and complete current feature index |
| `docs/planning/` | Feature scope, donor provenance, sequencing, and gates |
| `docs/CHANGE-INDEX.md` | Change links and frozen documentation identities; does not duplicate requirement or status authority |
| `docs/research/` | Evidence gathered from donor projects and standards |
| `docs/protocols/` | Copied project-control protocols, including anti-drift |
| `docs/reviews/` | Frozen semantic reviews, findings, and readiness results |
| `docs/evidence/` | Phase commands, donor hashes, test results, and limitations |
| `plugin-kit/` | Public Vault Plugin Kit source: schemas, offline CLI, TypeScript/Python helpers, starters and examples; ordinary developer tooling, never an in-product agent |
| `scripts/research/` | Read-only donor inventory utilities; never writes to donor projects |
| `app/vault_runtime/runtime_paths.py` | Portable owner-local runtime/data paths; Phase 1A Voice donor adaptation |
| `app/vault_runtime/local_api/config.py` | Loopback/token/origin configuration with hosted cloud fields removed |
| `app/vault_runtime/local_api/app.py` | Local health/identity, Voice/Background and owner-controlled Phase 5 extension HTTP contract; strict JSON and CSRF protected |
| `app/vault_runtime/local_api/server.py` | Deterministic loopback HTTP lifecycle extracted from Voice |
| `app/vault_runtime/local_api/stores.py` | Voice PostgreSQL/pgvector health contract only; data methods arrive by phase |
| `app/vault_runtime/local_api/__main__.py` | Standalone Phase 1 runtime entrypoint |
| `app/vault_runtime/composition.py` | Local production composition of identity, memory, Voice provider, tools and extensions; no cloud plane or extra agent registry |
| `app/vault_runtime/email_provider.py`, `email_service.py`, `email_store.py` | Direct Voice multi-account Mail client donor slice: labeled, workspace-scoped IMAP/SMTP accounts, cache/sync, confirmation and persistence |
| `app/vault_runtime/email_schema.py`, `email_runtime.py` | Phase 2-scoped Mail schema and encrypted local credential/composition adaptation; Agent Mail excluded |
| `app/vault_runtime/personal_data.py` | Local PostgreSQL account/workspace authority for only Contacts, Calendar cache and their provider records |
| `app/vault_runtime/session_tools/brokers/contacts.py`, `contacts_tools.py` | Direct Voice Contacts broker plus canonical fixed-Voice-Agent catalog adapter; save/use actions retain confirmation |
| `app/vault_runtime/calendar_provider.py`, `calendar_sync.py` | Direct Voice Calendar provider/sync donor slice; ICS read and CalDAV behavior preserved |
| `app/modules/integrations/calendar_ics_provider.py`, `caldav_calendar_provider.py` | Direct Voice outbound-safe Calendar protocol clients; no unrelated integration family admitted |
| `app/vault_runtime/calendar_runtime.py`, `calendar_tools.py` | Local encrypted/scoped Calendar composition and canonical Voice-only donor-cache/create-confirmation adapters |
| `app/vault_runtime/email_tools.py` | Canonical projection of the copied Voice Mail client tools to the fixed Voice Agent only |
| `app/vault_runtime/session_tools/brokers/provider_cache.py` | Direct Voice provider-cache broker copied only for admitted Calendar reads |
| `pyproject.toml`, `uv.lock` | Minimal donor-pinned Python package and reproducible dependency lock |
| `compose.test.yml`, `.env.test.example` | Project-owned loopback PostgreSQL/pgvector test database with an isolated named volume |
| `scripts/test_env.py` | Cross-platform command surface for `.venv` sync and test database up/status/test/stop/reset |
| `scripts/internet_test_env.py` | Development-only authenticated HTTPS ingress and outbound-connectivity harness; Vault and PostgreSQL remain loopback-only |
| `scripts/factory_reset_test_vault.py` | Explicitly confirmed factory reset limited to the isolated manual Browser Voice test database and ignored runtime state |
| `Dockerfile`, `.dockerignore` | Production multi-stage Vault image: Browser Voice build, locked Python runtime, non-root service user and Bubblewrap package |
| `compose.yml`, `docker/link-bridge/` | Installed production package: Vault runtime, private PostgreSQL/pgvector, and a loopback-only verified-TLS Link compatibility bridge; production-only data volumes remain unchanged |
| `scripts/vault_package.py`, `vault-package` | Supported package lifecycle: install, LAN install, start, status, logs, setup, backup, verified restore, uninstall and confirmed factory reset |
| `app/vault_runtime/package_runtime.py` | Idempotent package initialization, local CA/TLS generation, package secrets, database configuration and health checks |
| `app/vault_runtime/workspace_storage.py` | Private per-user and per-workspace storage/key provisioning, startup reconciliation and deletion cleanup |
| `docs/development/` | Local developer environment and test workflow documentation |
| `app/core/security/passwords.py` | Voice PBKDF2 password format with malformed-hash denial hardening |
| `app/core/security/tokens.py` | Voice-compatible opaque token hashing; no hosted JWT behavior |
| `app/vault_runtime/local_identity/` | NEW local multi-account authority: permanent master plus three secondary users, server-validated first-run setup entry with HttpOnly resume authority, optional onboarding creation, `under_18`/`adult` future-use classification, master-selected setup/temporary/managed password control, revocation, private workspaces and opaque sessions; no MFA |
| `app/vault_runtime/voice/credentials.py` | Encrypted master-configured provider authority shared read/use-only with every active Vault user; onboarding, Connections, Voice, Background and memory learning reuse it; only the master may replace/remove keys |
| `app/vault_runtime/voice/schema.py` provider access | Per-account shared-or-individual provider policy; individual keys remain encrypted in that account's fixed private workspace and are never returned |
| `frontend/src/browser-voice/BrowserVoiceApp.tsx` | Browser Voice Home plus resumable R1-shaped onboarding with one consistent action-group contract; R1 connect greeting delivery, Browser Voice microphone processing constraints, transcript/tool/session lifecycle |
| `frontend/src/browser-voice/AccountPanel.tsx`, `ConnectionsPanel.tsx` | R1-shaped collapsible user management and labeled multi-account Mail/Calendar/provider connection management |
| `frontend/src/browser-voice/styles/browser-voice-r1-console.css` | Final R1 management-console layout/responsive layer; every mobile surface is width-contained and onboarding actions share placement, hierarchy and interaction styling |
| `app/vault_runtime/workspace_paths.py` | Voice key normalization plus local traversal/symlink staging guard |
| `app/vault_runtime/memory/contracts.py` | Exact R1 memory contract v2 labels plus local private/workspace visibility validation |
| `app/vault_runtime/memory/schema.py` | PostgreSQL transcript, summary, lifecycle, evidence, ingestion, pending-action and real pgvector embedding schema, including upgrades from the earlier JSON-only vector relation |
| `app/vault_runtime/memory/repository.py` | Scoped Voice/R1 transcript, ingestion, reconciliation, profile, lexical, pgvector and confirmed-action persistence; canonical forget/replay suppression enforced through `memory/suppression.py` |
| `app/vault_runtime/memory/models.py` | Local immutable memory, transcript and pending-action records |
| `app/vault_runtime/memory/retrieval.py` | One R1 lexical/exact/semantic merge policy; default legacy candidate hooks and optional SQL adapter reuse it |
| `app/vault_runtime/memory_search/` | Scoped PostgreSQL HNSW/GIN retrieval and owned startup index validation/cutover; bounded canonical-vector repair lifecycle, explicit legacy rollback |
| `app/vault_runtime/live_memory/` | Shared Chat/Voice-mounted VoiceMem lifecycle, transient parallel memory/tool preparation, scoped channel source adapters, authenticated revisions and exact-final handoff; current-state guards and one bounded worker budget; no speculative execution |
| `app/vault_runtime/conversation/` | Scoped immutable final text plus mounted bounded text-model execution, canonical response events, source capture, replayable SSE and Stop; idle review through existing segment/worker/checkpoints with independent consumer coverage; no Background goal or third agent |
| `app/vault_runtime/conversation_tools/` | Real conversation/turn adapter into existing interactive ToolCatalog/grants/durable invocation owner; no fake Voice session, independent grant store or duplicated handlers |
| `frontend/src/browser-voice/conversation/` | Separate lazy Chat page, scoped transient controller, existing authenticated API/SSE/history/Stop, pinned assistant-ui headless primitives and existing Voice toggle delegation; no client inference/tool execution or durable drafts |
| `app/vault_runtime/memory/service.py` | Bounded search and confirmed correction/forget capability; not an agent |
| `app/vault_runtime/memory/pipeline.py` | R1 citation-required, fingerprint-idempotent session finalize capability; not an agent |
| `app/vault_runtime/memory/openai_reviewer.py` | Direct R1 structured memory-review capability using the locally configured encrypted workspace provider; never a system agent |
| `app/vault_runtime/memory/openai_embeddings.py` | Direct R1 real OpenAI embedding provider adapted to each Vault user/workspace's shared-or-individual encrypted provider authority; no fake-vector fallback |
| `app/vault_runtime/memory/voice_learning.py` | Voice donor final-event/close composition joined to the R1 reviewer and reconciliation pipeline under local user/workspace authority |
| `app/vault_runtime/memory/chat_learning.py` | Sealed Chat channel adapter into the same factual reviewer/canonical reconciliation and embedding store; exact original-source evidence references, scoped atomic publication checkpoint, no copied Voice transcript or new memory authority |
| `app/vault_runtime/memory/analysis_spans.py` | Pure lossless source-span partition/coverage validation for bounded factual review; not a worker, reviewer, store or mounted full-window coordinator |
| `app/vault_runtime/memory/analysis_windows.py` | Bounded factual Chat model-step continuation/consolidation using exact spans; Chat learning owns scoped durable steps, existing worker and MemoryPipeline own scheduling/publication |
| `app/vault_runtime/decision_learning/analysis_windows.py` | Bounded procedural assessment/output coordinator with full source visibility; reuses shared configured reviewer and existing fenced stage/reconciliation/publication owners, not a worker/source store |
| `app/vault_runtime/memory/evidence.py` | R1 recursive secret redaction and 16 KiB tool-evidence bound |
| `app/vault_runtime/memory/tools.py` | R1 lookup/explain/explicit-remember and confirmation-protected correction/forget tools in the fixed-agent catalog |
| `app/vault_runtime/system_agents/inventory.py` | Immutable two-entry Voice/Background system-agent inventory; no registration API |
| `app/vault_runtime/tools/definitions.py` | Donor-derived local tool context, result, effects and fixed-agent audiences |
| `app/vault_runtime/tools/catalog.py` | Canonical schema/audience/local-authorization dispatch and Phase 5 capability-source hook |
| `app/vault_runtime/web_search.py` | Direct Voice Vault `web_search` port: workspace-scoped provider credential, OpenAI Responses built-in search, mandatory public URL citations and fixed-agent catalog registration |
| `app/vault_runtime/tools/strict_json.py` | Voice donor bounded JSON parser/canonicalizer with duplicate, non-finite, depth, node and size rejection |
| `app/vault_runtime/voice/schema.py` | Local Voice session, provider-event, tool-grant and support-safe invocation schema; no hosted teardown/route grants |
| `app/vault_runtime/voice/repository.py` | Voice donor session lifecycle and idempotent provider events under Phase 2 authority |
| `app/vault_runtime/voice/instructions.py`, `voice/context.py` | Source-traced R1 Voice/tool guidance plus deterministic local profile/style, eight scoped memories, prior completed summary and enabled-Skill disclosure |
| `voice/context.py::previous_summary_context` | Existing bounded untrusted-summary formatting shared by Voice startup and Chat segment handoff; no separate compaction model/store |
| `app/vault_runtime/voice/tools.py` | Built-in grant bootstrap, scoped extension authorization and Voice donor exact-once/effect-unknown invocation recovery |
| `app/vault_runtime/voice/evidence.py` | R1/Voice bounded redacted tool results appended to scoped Phase 3 transcripts |
| `app/vault_runtime/voice/events.py` | Voice provider-event idempotency mapped into bounded scoped Phase 3 transcripts |
| `app/vault_runtime/voice/provider.py` | Voice provider-neutral startup with a single per-session catalog snapshot and R1 audio/VAD defaults; credentials remain outside persisted context |
| `app/vault_runtime/voice/openai_realtime.py` | Owner-key OpenAI Realtime WebRTC adapter with R1 PCM/noise/transcription/VAD/tool-choice payload parity |
| `app/vault_runtime/voice/greeting.py` | Exact local R1 daypart/name connect-greeting event contract; emitted once after the browser Realtime data channel opens |
| `app/vault_runtime/background_agent/contracts.py` | R1 fixed generic Background Agent execution plans, states, bounded requests and legal transitions |
| `app/vault_runtime/background_agent/schema.py` | Phase 2-scoped durable Background Agent runs and event timeline |
| `app/vault_runtime/background_agent/repository.py` | R1 lifecycle persistence adapted from SQLite/global scope to local PostgreSQL authority |
| `app/vault_runtime/background_agent/tool_supply.py` | Immutable per-run tool-name/effect/autonomy/budget intersection |
| `app/vault_runtime/background_agent/service.py` | One fixed Background Agent identity with four bounded concurrent workers; scoped submit/execute/cancel/fail lifecycle and model/tool budgets |
| `app/vault_runtime/sandbox/` | Voice-donor-derived fixed-agent Bubblewrap process boundary: per-run roots, clean environment, hidden host paths, no network and resource/time limits; no Agent Packages |
| `app/vault_runtime/background_agent/output_contract.py` | Direct R1 strict Background result, requirement-outcome and bounded phase-evidence schema |
| `app/vault_runtime/background_agent/sdk_runner.py`, `openai_executor.py` | R1 single-agent SDK runner plus local encrypted-provider/in-process-tool adapter used by production composition |
| `app/vault_runtime/extensions/archives.py` | R1-derived bounded ZIP/TAR quarantine; traversal/link/encryption/collision/bomb controls |
| `app/vault_runtime/extensions/package_review.py` | Non-executing advisory review of quarantined Plugin bytes for embedded secrets, scripts and suspicious instructions; never an agent identity or execution authority |
| `app/vault_runtime/extensions/specification.py`, `standards/` | Pinned Agent Plugins 1.0.0 Plugin/MCP manifest validation |
| `app/vault_runtime/extensions/skills.py` | Public Agent Skills `SKILL.md` parser and confined resource access; `allowed-tools` grants nothing |
| `app/vault_runtime/extensions/preflight.py` | Expiring, one-use, principal/workspace/current-hash/replacement-bound confirmations |
| `app/vault_runtime/extensions/filesystem.py` | Same-filesystem staged replacement, previous-version rollback and startup recovery |
| `app/vault_runtime/extensions/schema.py`, `repository.py` | Scoped Plugin/Skill/MCP ownership, grants, discovery, events and safe-mode persistence |
| `app/vault_runtime/extensions/service.py` | Owner-only direct Skill, Plugin and MCP preflight/confirmation lifecycle; no agent creation |
| `app/vault_runtime/extensions/activation.py` | Metadata-first Skill discovery and load-time lifecycle/scope recheck |
| `app/vault_runtime/extensions/mcp_config.py`, `mcp_client.py` | Credential-free configuration validation and bounded MCP 2025-11-25 initialize/list/call client |
| `app/vault_runtime/extensions/mcp_lifecycle.py` | Discovery-without-grant and exact scoped MCP tool projection/revocation into canonical catalog |
| `app/vault_runtime/extensions/secrets.py` | AES-GCM local MCP credential headers under a private owner-local master key |
| `tests/unit/`, `tests/integration/` | Carried/adapted donor tests plus standalone security, multi-account Mail and scoped Contacts regressions |

## Extracted donor structure

Preserve the primary donor's structure. Do not create an alternative `src/vault`
architecture.

| Planned path | Intended owner |
|---|---|
| `app/vault_runtime/` | Existing Voice Vault runtime copied with its module boundaries intact |
| `app/modules/` | Only direct existing Voice module dependencies required by Vault |
| `app/contracts/` | Existing internal contracts required by Vault runtime |
| `app/system_agents/` | Only if needed: the fixed Voice Agent and Background Agent boundary |
| `frontend/src/browser-voice/` | Exact existing Browser Voice application |
| `frontend/` | Browser Voice entry/build configuration and required shared utilities |
| `packaging/` | Linux-first desktop/local packaging; never device images or flashing |
| `tests/` | Carried donor tests plus cloud-detachment, local-auth and desktop/local packaging tests |

Do not create planned paths merely to make this table true. Create them only
under an accepted build contract, and update this index when their ownership is
proven or changes.

Live-memory/learned-decision/chat change authority is indexed from
`docs/planning/PROJECT-STATE.md` and owned by
`docs/planning/2026-10-04-live-memory-decisions-grounding.md`. It is Phase 00
grounding only; existing runtime owners remain unchanged.

The controlling donor implementation rule is
`docs/planning/DONOR-PORTING-RULE.md`: existing features are copied/extracted
from exact donor files rather than independently rewritten.

The primary implementation authority is Voice `app/vault_runtime/` plus
Browser Voice. `docs/planning/PRIMARY-DONOR-AND-CLOUD-SUBTRACTION.md` controls
the removal of ReSono cloud authentication and control-plane dependencies.
`docs/planning/PROJECT-BORROWING-MATRIX.md` controls what each other project may
contribute.

No Agent Foundry, Build Agent, Agent Hub, specialist-agent, agent-template or
installable-agent-package directory is authorized. Any donor code that creates
an agent identity beyond Voice Agent and Background Agent is drift.
Build scripts, installers, CI jobs, and release commands are ordinary tooling;
they must never be represented by an in-product Build Agent.

Phase 5 extension code must preserve this inventory mechanically: importing,
enabling, disabling, updating, revoking or rolling back a Plugin, Skill, MCP
server or tool changes available capabilities only. It must not add an agent
record, agent selector, agent registry, delegation target or build-agent path.

Planning authority is indexed in `docs/planning/07-MASTER-DELIVERY-PLAN.md`,
phase gates in `docs/planning/09-PHASE-BUILD-CONTRACTS.md`, and live status in
`docs/planning/PROGRESS.md`.

The permanent-master account lifecycle boundary is
`docs/planning/21-MASTER-ACCOUNT-CONTROL-CONTRACT.md`; passing implementation
evidence is `docs/evidence/MASTER-ACCOUNT-CONTROLS.md`.

Current concurrent-user and sandbox authority is
`docs/research/PHASE-02D-VOICE-SANDBOX-AND-CONCURRENT-USERS-INVENTORY.md` and
`docs/planning/23-CURRENT-MULTI-USER-SANDBOX-CONTRACT.md`. The sandbox borrows
Voice enforcement primitives but must not restore Agent Packages or additional
agent identities.
The first concurrency slice is recorded in
`docs/evidence/PHASE-02D-MULTI-USER-CONCURRENCY-M1.md`.

More than four users, parental controls and edge-device hotspot support remain
deferred in
`docs/planning/22-DEFERRED-HOUSEHOLD-SCALE-SANDBOX-AND-HOTSPOT.md`.

Phase 7 is desktop/local Linux packaging only. Its contract and donor inventory
do not authorize device images, firmware, flashing, fastboot, USB/udev flows,
or physical-device deployment.

Phase 5 donor and standards authority is
`docs/research/PHASE-05-EXTENSION-IMPORT-INVENTORY.md`; its accepted build
boundary and exit tests are
`docs/planning/16-PHASE-05-EXTENSIONS-CONTRACT.md`.

Owner-activated Phase 10 corrects the supported Agent Plugins 1.0 subset and
adds only the loopback scoped-memory service required by optional Hermes and
OpenClaw adapters. Its inventory, contract and entry review are
`docs/research/2026-08-31-PHASE-10-PLUGIN-STANDARD-AND-MEMORY-INVENTORY.md`,
`docs/planning/25-PHASE-10-AGENT-PLUGINS-AND-EXTERNAL-MEMORY-CONTRACT.md`, and
`docs/reviews/2026-08-31-PHASE-10-ANTI-DRIFT-ENTRY.md`. OpenClaw implementation
remains blocked until an exact local donor release is frozen. Phase 9 routing,
general Vault exposure and arbitrary Plugin code remain excluded.

The accepted first runtime extraction slice is
`docs/planning/10-PHASE-01-RUNTIME-FOUNDATION-CONTRACT.md`.
Its verification record is `docs/evidence/PHASE-01A-RUNTIME-FOUNDATION.md`.
The completed server slice and Phase 1 exit are recorded in
`docs/evidence/PHASE-01B-LOCAL-SERVER.md` and
`docs/reviews/2026-08-29-PHASE-01-ANTI-DRIFT-EXIT.md`.

Phase 2 donor findings and its frozen candidate contract are
`docs/research/PHASE-02-IDENTITY-WORKSPACE-DONOR-INVENTORY.md` and
`docs/planning/12-PHASE-02-LOCAL-IDENTITY-CONTRACT.md`. No Phase 2 code may be
copied outside that bounded contract.
The first verified Phase 2 slice is
`docs/evidence/PHASE-02A-SECURITY-PRIMITIVES.md`.
Phase 2 completion evidence and exit review are
`docs/evidence/PHASE-02-LOCAL-IDENTITY-WORKSPACES.md` and
`docs/reviews/2026-08-29-PHASE-02-ANTI-DRIFT-EXIT.md`.

Phase 3 Voice/R1 source authority and merge findings begin at
`docs/research/PHASE-03-VOICE-R1-MEMORY-INVENTORY.md`.
The frozen implementation boundary is
`docs/planning/14-PHASE-03-MEMORY-MERGE-CONTRACT.md`. It admits the Voice
PostgreSQL memory foundation plus the updated R1 v2 taxonomy/lifecycle, owned
only by the Voice Agent and Background Agent capability paths. It explicitly
excludes document storage, shared external memory access and all additional
agent identities from Phase 3.
The first bounded schema/contract proof is
`docs/evidence/PHASE-03A-MEMORY-CONTRACT-SCHEMA.md`; it does not close Phase 3.
Phase 3 completion evidence and its anti-drift exit are
`docs/evidence/PHASE-03-MEMORY-MERGE.md` and
`docs/reviews/2026-08-29-PHASE-03-ANTI-DRIFT-EXIT.md`.

Phase 3's schema and isolated pipeline proof do not by themselves satisfy the
product requirement. Production composition must wire the full learning chain
to both fixed system agents. Voice must inject scoped startup memory and
finalize captured transcripts on close. Background must receive scoped memory,
retain memory references, and persist bounded phase evidence exactly as R1
does. Automatic Background-to-canonical-memory writeback is not donor-proven.
This is
tracked by `docs/planning/20-MANDATORY-R1-MEMORY-LEARNING-INTEGRATION-CONTRACT.md`.
Within that chain, updated R1 is the functional authority; Voice Vault remains
the datastore, identity, user, and workspace authority. Simpler legacy Voice
memory behavior may not downgrade the R1 port.

The correction is a reopened integration gate. Earlier Phase 3/4 completion
records remain valid only for the isolated behavior they actually tested; they
are not evidence that production Voice and Background learning is complete.
The Phase 4C donor inventory and entry decision are
`docs/research/PHASE-04C-R1-MEMORY-LEARNING-DONOR-CUTPOINTS.md` and
`docs/reviews/2026-08-29-PHASE-04C-M0-ANTI-DRIFT-ENTRY.md`.

Phase 4 donor findings and the frozen two-system-agent implementation boundary
are `docs/research/PHASE-04-VOICE-BACKGROUND-TOOLS-INVENTORY.md` and
`docs/planning/15-PHASE-04-VOICE-BACKGROUND-TOOLS-CONTRACT.md`.
The first bounded safety proof is
`docs/evidence/PHASE-04A-SYSTEM-AGENT-TOOL-BOUNDARY.md`; it does not close
Phase 4.
Phase 4 completion evidence and anti-drift exit are
`docs/evidence/PHASE-04-VOICE-BACKGROUND-TOOLS.md` and
`docs/reviews/2026-08-29-PHASE-04-ANTI-DRIFT-EXIT.md`.

Phase 5 completion evidence and anti-drift exit are
`docs/evidence/PHASE-05-EXTENSIONS.md` and
`docs/reviews/2026-08-29-PHASE-05-ANTI-DRIFT-EXIT.md`.

Phase 6 donor/visual authority and accepted build boundary are
`docs/research/PHASE-06-BROWSER-VOICE-DONOR-INVENTORY.md` and
`docs/planning/17-PHASE-06-EXACT-BROWSER-VOICE-CONTRACT.md`.
The complete theme/onboarding source audit and its still-open rendered evidence
gate are recorded in
`docs/reviews/2026-08-29-FULL-BROWSER-VOICE-THEME-AND-ONBOARDING-REVIEW.md`.

The owner-admitted built-in Mail/Contacts/Calendar slice is controlled by
`docs/research/PHASE-06B-MAIL-CONTACTS-CALENDAR-DONOR-INVENTORY.md` and
`docs/planning/18-PHASE-06B-BUILTIN-PERSONAL-CAPABILITIES-CONTRACT.md`.
It remains donor-research-only until its transitive code/schema/test closure is
frozen; this does not authorize any other signal/tool family.

The only admitted built-in personal capability domains are Mail (including the
donor multi-account mail client), Contacts and Calendar. External AI, social
posting, recipes, local events and all other donor signal/tool families are
excluded from core. They do not receive repository paths until a later owner
decision and accepted donor phase contract.
