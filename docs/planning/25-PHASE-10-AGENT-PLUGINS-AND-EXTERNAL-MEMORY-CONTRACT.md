# Phase 10 Agent Plugins and External Memory Contract

Date: 2026-08-31  
Status: frozen candidate v1  
Authority: owner activation, `GROUNDING.md`, Phase 10 inventory, Agent Plugins
1.0.0

## Outcome

Vault correctly loads the supported Agent Plugins 1.0.0 subset. A separately
installed Hermes adapter can search and propose memory through Vault's
canonical scoped service. An OpenClaw adapter follows only after its exact
release gate passes.

This phase does not make external agents part of Vault and does not expose most
Vault internals.

## In scope

1. Correct the three verified Agent Plugins conformance gaps in the inventory.
2. Preserve Streamable HTTP as the only executable MCP transport.
3. Add a distinct, revocable integration identity bound to one user/workspace.
4. Add a loopback-only external-memory service for search/get, propose,
   correction, forget, health and revocation.
5. Route proposals through existing Vault review/reconciliation/evidence.
6. Build and test a standalone Hermes `MemoryProvider` against the frozen local
   donor.
7. Freeze an exact OpenClaw donor and then build its native memory Plugin
   without changing OpenClaw core.

## Out of scope

- Phase 9 routing or any cross-device connection;
- credential/keystore brokering;
- other Vault domains;
- stdio/SSE execution or arbitrary Plugin runtime code;
- client-specific extension namespace, marketplace, updater, signatures, event
  framework, webhook system or new UI framework;
- automatic import of existing external memory;
- continuous bidirectional mirroring;
- external direct canonical writes or database credentials; and
- any third system-agent identity.

## Required sequence

### M0 — Freeze and conformance fixtures

Entry: this contract and inventory reviewed.  
Deliverables: official Agent Plugins fixtures; exact expected diagnostics;
Hermes donor integrity check; exact local OpenClaw release/license/source/test
inventory.  
Tests: valid minimal/full manifests, unknown field, empty MCP map, malformed
independent Skill/server, unsupported transport.  
Exit: Vault/Hermes paths remain exact; OpenClaw either passes its donor gate or
its later milestone stays blocked.

### M1 — Correct Agent Plugins 1.0 behavior

Entry: M0 fixtures.  
Deliverables: nonfatal unknown-field diagnostics, valid empty `mcpServers` and
independent component results.  
Tests: positive fixtures plus fatal-manifest, containment, collision,
replacement, rollback, safe-mode and grant regressions.  
Stop: any relaxation grants or executes a component automatically.  
Exit: supported-subset conformance passes without weakening Phase 5 controls.

### M2 — Scoped local external-memory service

Entry: M1 and existing memory service/reconciliation tests green.  
Deliverables: integration identity/grants, one-time local enrollment through
existing Connections management patterns, loopback API, bounded schemas, audit
attribution and immediate revocation.  
Tests: search/propose positive path; malformed/oversized/replay denial;
private/workspace isolation; wrong operation; revoked integration; proposal
reconciliation; granted correction/forget auto-application; no database or
arbitrary scope surface.  
Stop: any client supplies authoritative user/workspace scope or writes canonical
records directly.  
Exit: fake adapter proves the full authenticated runtime chain.

### M3 — Hermes adapter

Entry: M2 and frozen Hermes commit.  
Deliverables: standalone provider package using native initialization,
prefetch, completed-turn synchronization and setup surfaces; no Hermes core
patch.  
Tests: setup, scoped recall, attributable proposal, duplicate/retry behavior,
Vault unavailable, revocation, and no write from non-primary Hermes contexts.
  
Exit: a real Hermes session recalls one authorized Vault memory and contributes
one proposal that Vault reconciles with evidence.

### M4 — OpenClaw adapter

Entry: exact local OpenClaw release/license/source/test inventory accepted.  
Deliverables: native memory Plugin using the pinned release's slot/tool
contract; no OpenClaw core patch.  
Tests: slot activation, search/get/propose/forget-request compatibility,
ownership isolation, Vault unavailable, revocation, and preservation or
explicit documented replacement of required default-memory behavior.  
Stop: exclusive-slot behavior cannot be preserved safely.  
Exit: a real pinned OpenClaw session passes the same authorized recall and
proposal proof as Hermes.

### M5 — Anti-drift exit

Entry: completed milestones and evidence.  
Deliverables: donor integrity, full regression, public capability trace,
limitations, rollback and anti-drift review.  
Exit: Agent Plugins support is truthfully described by component and transport;
Vault remains canonical; exactly two Vault system agents remain.

## Rollback

- disable or revoke integration identities before removing adapter packages;
- retain attributable Vault memory/evidence unless the owner separately
  confirms deletion;
- schema changes must be additive and reversible before migration acceptance;
- M1 conformance corrections must preserve the prior installed Plugin tree and
  rollback behavior; and
- failure of M4 does not invalidate M1–M3.

## Acceptance trace

| Requirement | Proof |
|---|---|
| Agent Plugins supported subset conforms | Official positive/negative fixtures |
| Existing extension security remains | Phase 5 regression plus new denial tests |
| External agents cannot select scope | Cross-user/workspace and forged-ID tests |
| Vault remains canonical | Vault-side classification/reconciliation and attributable granted mutations |
| Revocation is immediate | Post-revocation search/propose denial |
| Hermes works without core changes | Real pinned Hermes runtime trace |
| OpenClaw works without core changes | Real pinned OpenClaw runtime trace after donor gate |
| No scope drift | Source scan, two-agent inventory, anti-drift exit |
