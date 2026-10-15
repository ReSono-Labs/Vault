# Vault Documentation

For live memory, Chat and learned decisions, start ONLY at the
[current source-of-truth document set](planning/2026-10-07-live-memory-document-authority.md).
Original October4–5 grounding controls the goal; that map assigns one owner per
concern and links current allocation/status. No old review or READY manifest is
a build instruction. [PROJECT-STATE](planning/PROJECT-STATE.md) top CURRENT owns
next action; older checkpoints are historical.

Historical evidence, not current status: [split review](reviews/2026-10-07-decisions-split-contract-review.md),
[earlier Phase02 review](reviews/2026-10-07-decisions-plan-and-contract-review.md)
and old candidate manifests. Preserve them for chronology; use the current set
for any restart/review/build decision.

The canonical current-platform user and administrator manual is
`PLATFORM-GUIDE.md`. Start there for installation, accounts, sharing,
connections, agents, memory, extensions, backup, removal, and current limits.
Its **Common issues** section provides dashboard-friendly fixes for Plugin and
Skill imports, MCP address warnings, missing capabilities, local bridge sign-in
confusion, and package startup problems.

The 2026-10-04 modular live-memory, learned-decision and Vault-chat change is
grounded in [planning/2026-10-04-live-memory-decisions-grounding.md](planning/2026-10-04-live-memory-decisions-grounding.md).
Its [code review](research/2026-10-04-live-memory-decisions-code-review.md)
distinguishes existing runtime behavior from missing components and theoretical
Decisions API integration. Phase 00 only; no implementation plan/build readiness.
The [change index](CHANGE-INDEX.md) records this documentation checkpoint.

User-facing setup and connection guides:

- `WINDOWS-INSTALLATION.md` — install and operate Vault on Windows with Docker
  Desktop and WSL 2.
- `RESONO-LABS-LINK.md` — add a ReSono Labs Link Custom HTTP/WebSocket
  service (web interface) that targets the local Vault bridge.
- `LOCAL-CONNECTION-BRIDGE.md` — understand the optional local HTTP/WebSocket
  compatibility bridge and when to use it.
- `HERMES-OPENCLAW-MEMORY.md` — install and pair the Hermes/OpenClaw adapters,
  inject Vault memory into sessions, submit completed turns for Vault review,
  and disconnect safely.
- `VAULT-PLUGIN-KIT.md` — build and validate Agent Plugin packages, including
  `vault.json` migration imported from **Library → Plugin**.
- `VAULT-MCP-PACKAGE-KIT.md` — build and validate hosted MCP packages
  (`mcp.package.json`), supervised processes, companion plugins, and MCP-tab import.

Read documents in this order:

1. `../GROUNDING.md` — controlling product boundary.
2. `../SKILLS.MD` — mandatory working and deployment rules.
3. `../INDEX.MD` — concise repository map.
4. `protocols/ANTI-DRIFT-PROTOCOL.md` — planning/change-control method.
5. `planning/FEATURE-DONOR-MAP.md` — feature provenance and readiness.
6. `planning/DONOR-PORTING-RULE.md` — mandatory direct donor-code rule.
7. `planning/PRIMARY-DONOR-AND-CLOUD-SUBTRACTION.md` — Voice-first authority and cloud-auth removal.
8. `planning/PROJECT-BORROWING-MATRIX.md` — exact ownership by donor project.
9. Applicable research and planning documents.

The master sequence is `planning/07-MASTER-DELIVERY-PLAN.md`; phase contracts
are in `planning/09-PHASE-BUILD-CONTRACTS.md`; live status is
`planning/PROGRESS.md`; reviews are under `reviews/`.

The implementation-ready plan for the public Vault Plugin Kit, SDK helpers,
managed embedded MCP wiring, safe configuration, scoped memory services, and
full Documents guide is `planning/26-VAULT-PLUGIN-KIT-DELIVERY-PLAN.md`.

The current extraction inventory is
`research/VOICE-VAULT-EXTRACTION-INVENTORY.md`.

Local development and the isolated Docker PostgreSQL test database are
documented in `development/LOCAL-TEST-ENVIRONMENT.md`.
The installed production Docker package is documented in
`development/PRODUCTION-PACKAGE.md`; its architecture contract and evidence are
`planning/24-PRODUCTION-PACKAGE-AND-USER-PROVISIONING.md` and
`evidence/2026-08-29-PRODUCTION-PACKAGE.md`.
Authenticated inbound HTTPS and outbound internet testing are documented in
`development/INTERNET-CONNECTIVITY-TESTING.md`; the harness does not alter the
local-only product or expose PostgreSQL.

The permanent-master/secondary-account lifecycle correction is controlled by
`planning/21-MASTER-ACCOUNT-CONTROL-CONTRACT.md` and verified in
`evidence/MASTER-ACCOUNT-CONTROLS.md`.

Current simultaneous-user and sandbox correction authority is
`research/PHASE-02D-VOICE-SANDBOX-AND-CONCURRENT-USERS-INVENTORY.md` plus
`planning/23-CURRENT-MULTI-USER-SANDBOX-CONTRACT.md`.
M1 concurrency evidence is `evidence/PHASE-02D-MULTI-USER-CONCURRENCY-M1.md`.
More users, parental controls and hotspot work remain deferred under
`planning/22-DEFERRED-HOUSEHOLD-SCALE-SANDBOX-AND-HOTSPOT.md`.

The original feasibility and security boundary for making Vault an optional
external memory store for Hermes/OpenClaw is
`research/2026-08-29-HERMES-OPENCLAW-EXTERNAL-MEMORY-REVIEW.md`. The activated
loopback-only Phase 10 inventory and bounded build contract are
`research/2026-08-31-PHASE-10-PLUGIN-STANDARD-AND-MEMORY-INVENTORY.md` and
`planning/25-PHASE-10-AGENT-PLUGINS-AND-EXTERNAL-MEMORY-CONTRACT.md`. Work has
completed M2's scoped external-memory and owner-confirmation chain; see
`evidence/PHASE-10-M2-EXTERNAL-MEMORY-BOUNDARY.md`. The standalone Hermes
package is built but not installed or live-activated; see
`evidence/PHASE-10-M3-HERMES-ADAPTER.md`.
Cross-device routing remains deferred.
M0–M1 conformance evidence is
`evidence/PHASE-10-M0-M1-AGENT-PLUGINS-CONFORMANCE.md`.
The complete live installation, failure, repair and bidirectional-test record
is `evidence/2026-08-31-SHARED-MEMORY-LIVE-TEST-LOG.md`; its open-items section
is authoritative for tests that have not yet been closed.

The companion research-only keystore review covers Vault-issued ephemeral
capability tokens, preferred provider brokering, Hermes secret-source plugins,
OpenClaw SecretRefs, raw-key compatibility risks, and cross-device credential
pairing:
`research/2026-08-29-VAULT-PRIMARY-KEYSTORE-AND-CREDENTIAL-BROKER-REVIEW.md`.

The completed mandatory updated-R1 memory/learning correction is controlled by
`planning/20-MANDATORY-R1-MEMORY-LEARNING-INTEGRATION-CONTRACT.md`. Its donor
cut points, entry review, slice evidence, and exit review are:

- `research/PHASE-04C-R1-MEMORY-LEARNING-DONOR-CUTPOINTS.md`;
- `reviews/2026-08-29-PHASE-04C-M0-ANTI-DRIFT-ENTRY.md`;
- `evidence/PHASE-04C-M1-STRUCTURED-MEMORY-REVIEWER.md`;
- `evidence/PHASE-04C-M2-VOICE-MEMORY-LEARNING.md`;
- `evidence/PHASE-04C-M3-BACKGROUND-MEMORY-EVIDENCE.md`; and
- `reviews/2026-08-29-PHASE-04C-ANTI-DRIFT-EXIT.md`.

Current Phase 6 authorities are
`research/PHASE-06-BROWSER-VOICE-DONOR-INVENTORY.md` and
`planning/17-PHASE-06-EXACT-BROWSER-VOICE-CONTRACT.md`. The separately gated
owner-required built-in slice is documented in
`research/PHASE-06B-MAIL-CONTACTS-CALENDAR-DONOR-INVENTORY.md` and
`planning/18-PHASE-06B-BUILTIN-PERSONAL-CAPABILITIES-CONTRACT.md`.
Current evidence is `evidence/PHASE-06-BROWSER-VOICE.md` and
`evidence/2026-09-02-OWNER-VISUAL-QA.md`. Owner visual QA on 2026-09-02
closed the desktop/mobile visual gate. The earlier non-passing exit review
(`reviews/2026-08-29-PHASE-06-ANTI-DRIFT-REVIEW.md`) is historical: it recorded
the missing automated screenshot surface, not the current UI status.

Phase 7 covers Linux desktop/local packaging and explicitly excludes deployment
to a hardware device. Its candidate boundary is recorded in
`research/PHASE-07-LINUX-RELEASE-DONOR-INVENTORY.md` and
`planning/19-PHASE-07-LINUX-RELEASE-CONTRACT.md`.

`research/` records observed evidence. `planning/` turns accepted evidence into
bounded proposed work. Neither authorizes implementation unless the grounding
gate and a build contract explicitly do so.
