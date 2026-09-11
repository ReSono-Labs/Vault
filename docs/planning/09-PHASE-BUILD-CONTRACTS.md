# Phase Build Contracts

Status: frozen candidate v1

## Universal entry and exit control

At every phase entry and exit, read and cite `GROUNDING.md`, `INDEX.MD`,
`SKILLS.MD`, the anti-drift protocol, donor map, porting rule, master plan and
project borrowing matrix, and progress ledger. Confirm donor worktrees were not
changed. Any missed feature
must pass the material-decision gate and enter `INDEX.MD` before implementation.
No developer or AI may invent an ungrounded feature.

## Phase 0 — Controlled foundation

Scenario and owner: owner needs a clean, public-facing project safe to build.  
Entry: owner grounding decisions.  
In: controls, donor evidence, plan, review, repository metadata. Out: product code.  
Deliverables: complete docs, license blocker, phase contracts, progress ledger.  
Tests: links/paths/status consistency; adversarial semantic review.  
Stop/rollback: unresolved contradiction blocks dependent work.  
Exit: Phase 1 has exact donors, bounded files and tests.

## Phase 1 — Existing Voice Vault runtime extraction

Scenario: developer starts the existing Voice Vault runtime without mandatory
ReSono cloud bootstrap or authentication.  
Entry: Phase 0 correction pass and complete Voice Vault runtime inventory.  
In: phase-required `app/vault_runtime` modules, direct contracts/modules/tests,
cloud-edge classification, local startup and portable configuration. Out: new
runtime architecture, datastore replacement, Browser Voice.  
Donors: Voice `app/vault_runtime/` and its exact tests. R1 only for a documented
missing local behavior.  
Tests: carried donor tests, local startup, ReSono endpoints disabled, no
mandatory outbound call, and Linux/Windows/macOS path/config tests.  
Stop/rollback: any donor mutation, non-loopback default or hidden cloud call.  
Exit: deterministic local start/stop and health evidence.

## Phase 2 — Local identity and workspaces

Scenario: up to four authenticated users have isolated private workspaces.  
Entry: Phase 1; accepted schema/security contract.  
In: users, password/session security, memberships, scoped repositories/files.  
Out: remote identity, social login, enterprise roles.  
Donors: Voice identity-access/account/workspace code; replace cloud auth with
local authority while preserving contracts.  
Tests: cross-user denial, CSRF, expiry, traversal, symlink and four-user flow.  
Exit: no operation succeeds without matching principal/workspace.

## Phase 3 — Existing Voice Vault memory plus required R1 domain-memory merge

Scenario: each user receives existing Voice Vault memory plus the complete
updated R1 taxonomy/lifecycle without scope leakage.  
Entry: Phase 2 isolation proof.  
In: Voice Vault memory/session/datastore code; every R1 domain and memory type;
authority/confidence/sensitivity labels; evidence, versions, ingestion
idempotency, reconciliation, embeddings, hybrid retrieval and pending confirmed
correction/forget actions.  
Out: external agents. Donors: Voice memory boundaries plus exact R1 memory
modules/migration/tests. Do not rename or collapse R1 labels.  
Tests: donor parity plus private/shared scope, conflict and provider-offline cases.  
Exit: canonical memory remains usable without embeddings/provider.

## Phase 4 — Agents, providers, voice and tools

Scenario: an authenticated user can hold a Browser Voice-compatible session.  
Entry: Phase 3. In: exactly one fixed Voice Agent and one fixed Background
Agent, their provider/realtime/tool behavior, and no package-agent routing.  
Out: cloud control plane, Agent Foundry, Build Agent, Agent Hub, specialist,
generated, developer, marketplace and installable agents.  
Tests: tool authorization, session evidence, provider disconnect/redaction.  
Exit: local authority controls every model/tool projection and runtime inventory
proves exactly two agent identities.
The inventory test must fail if any installable, generated, specialist,
coordinator, developer, marketplace, Foundry, Hub, or Build Agent is registered.
Build and release tooling is not an agent and must run outside product runtime.

## Phase 4C — Mandatory R1 memory/learning integration correction

Scenario: both fixed system agents use the complete updated R1 memory and
learning chain inside Voice Vault's local multi-user/workspace authority.  
Entry: accepted contract 20 M0 donor freeze and anti-drift entry review.  
In: reviewer capability, actual Voice memory injection, authenticated
transcript capture, finalize-on-close, Background scoped context and
attributable learning evidence. Out: another agent, external shared-memory
clients, new taxonomy, document memory and excluded tools.  
Donors: exact Voice capture/finalize and updated R1 memory/reviewer/routes/tests
listed in contract 20.  
Tests: all M1–M4 positives, failures, replay, isolation, revocation, recovery,
taxonomy, evidence and no-third-agent gates.  
Stop/rollback: any donor ambiguity, scope expansion, authorization leak,
fabricated semantic behavior or unlicensed release dependency.  
Exit: fresh evidence and anti-drift review prove the production chain for both
agents; earlier Phase 3/4 exits cannot substitute.

## Phase 5 — Extensions

Scenario: owner safely imports and scopes Plugins, Skills and MCP tools.  
Entry: Phase 4. In: existing Voice package/signal/integration code; bounded R1
Plugin/Skill/MCP lifecycle controls only where Voice lacks equivalents.  
Tests: donor archive corpus, credential isolation, audience/grant/revocation,
rollback and safe mode. Exit: third-party extensions default disabled.

## Phase 6 — Exact Browser Voice web app

Scenario: owner onboards and manages Vault through the locked visual system.  
Entry: Phases 2–5 APIs stable. In: bounded Browser Voice files/styles/tests;
local API adapters; name/style onboarding. Out: cloud billing/operator UI.  
Tests: donor UI tests, visual screenshots, narrow/desktop behavior, accessibility,
no cloud endpoint. Exit: semantic and screenshot review shows no visual drift.

## Phase 7 — Linux desktop/local release

Scenario: non-developer installs, upgrades, backs up, restores and removes Vault.  
Entry: Phase 6 and license decision. In: bounded R1 Rust installer patterns,
service/launcher/release assembly. Tests: clean VM, offline use, rollback,
uninstall, SBOM/checksum/signing. Exit: reproducible public artifact.

## Phases 8–9 — Explicit deferred revisions

Phase 8 packages the unchanged desktop/local core for Windows/macOS. It does
not deploy to a hardware device. Phase 9 adds optional
Link/Tailscale and later remote management over the same API.

## Phase 10 — Agent Plugins and external memory adapters

Scenario: owner installs standards-compatible capabilities and may explicitly
connect Hermes or OpenClaw to scoped canonical Vault memory.  
Entry: existing internal scoped memory service; detailed Phase 10 inventory and
contract; exact adapter donor gate.  
In: verified Agent Plugins corrections, loopback integration identities and
memory service, native Hermes/OpenClaw adapters.  
Out: Phase 9 routing, broad Vault APIs, keystore brokering, arbitrary Plugin
code and new agent identities.  
Authority: `docs/planning/25-PHASE-10-AGENT-PLUGINS-AND-EXTERNAL-MEMORY-CONTRACT.md`.
