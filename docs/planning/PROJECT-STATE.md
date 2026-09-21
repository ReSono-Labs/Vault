# Project state (index)

Date: 2026-09-17  
Role: index and current-state file. It does not replace existing frozen authorities.

## Controlling sources

| Concern | Authority | Path |
|---|---|---|
| Product grounding | Frozen baseline | `GROUNDING.md` |
| Scope and requirements | Frozen candidate v1 | `docs/planning/01-SCOPE-AND-REQUIREMENTS.md` |
| Architecture | Existing | `docs/planning/02-ARCHITECTURE-AND-DATA-BOUNDARIES.md` |
| UX / visual lock | Frozen candidate v1 | `docs/planning/04-UX-AND-ONBOARDING-CONTRACT.md` |
| Decisions | Existing register | `docs/planning/08-DECISION-AND-BLOCKER-REGISTER.md` |
| Progress / evidence summary | Existing | `docs/planning/PROGRESS.md` |
| Vault A2A + Link-native (this change) | Phase 00 grounding; Phase 01 plan r2; C01 VERIFIED; C02 VERIFIED; C03 VERIFIED | this file |
| First-class Link Companion / C04 | Link+Vault grounding **r4**; plan r2; O4 next (not READY) | `/home/christian/Documents/Projects/ReSono-Labs-Link/docs/planning/2026-09-15-vault-first-class-link-integration.md` |
| Method | Anti-drift constitution | `/home/christian/Documents/Projects/drift-protection/AI-PLANNING-PROTOCOL.md` |

Do not copy constitution or phase prompts into this repository.

---

## Owner request

Original instructions and later corrections:

- 2026-09-21 owner: add OpenAI Luna as a Connections Background text model selection; official API id `gpt-5.6-luna`; keep default Sol; Docker package rebuild and deploy.
- 2026-09-17 owner: set up xAI/Grok OAuth on Vault the same way OpenClaw and Hermes do (device code). Voice may fail; the required outcome is a token the Background Agent can use via the provider selector.
- 2026-09-15 owner: Visual Background progress like R1, but do not submit tasks from the UI. Voice creates the goal, Background works it with most Voice tools plus dynamically granted third-party tools, same provider auth tokens as Voice. Review then finish. Combined with prior inventory.
- 2026-09-15 owner: Voice says there is no Background Agent. Are we not doing “modes” anymore? The whole point of Background Agent is for Voice to delegate tasks to it. Is Background built but not connected? Is it OpenAI Agents SDK? Do a full inventory. Record: `docs/planning/2026-09-15-background-agent-connection-inventory.md` (`BA-INV-2026-09-15-r1`).
- 2026-09-11 owner: this project has a lot of UI component cleanup. Components will be given one by one. The agent must create some type of markdown file for tracking, then perform all listed cleanups at once (not incrementally as each item arrives).
- 2026-09-11 owner (first item): Workspace page heading `Your workspace` / private-files subtitle → `{displayName}'s Workspace`, drop subtitle; keep `local` / swipe-hint row on top; move `Up one folder` to the bottom.

Delegated authority / reserved decisions:

- 2026-09-15 owner: implement Voice Goal Intake + Background progress UI (no UI submit form). Combined review+finish.
- 2026-09-15: inventory-only reservation superseded by the later finish request.
- Owner will name each UI component to track.
- Owner will later authorize the batch cleanup implementation (implicit in “then you will do all cleanups at once”).
- Cleanup meaning is **per named item** (copy, layout, etc.). General visual restyle of Browser Voice remains locked unless an item explicitly reopens D-02.
- Tracker path confirmed by use: `docs/planning/UI-COMPONENT-CLEANUP.md`.

Acceptance owner: repository owner (Christian). Agent does not grant acceptance.

---

## Grounding

Revision: `UI-CLEANUP-G-2026-09-11-r1`

Audience and actual use scenario:

- Maintainers and a later implementation pass need one list of owner-named UI components and the intended cleanup for each, then a single batch implementation.

Observable success (this change, not the whole product):

- A single tracking markdown exists and lists only owner-named components.
- Items stay queued until the owner says to implement the batch.
- Implementation (when authorized) does not violate the locked Browser Voice visual system unless the owner explicitly reopens that lock for a named item.

Current scope:

- Queue owner-named UI cleanups in `docs/planning/UI-COMPONENT-CLEANUP.md`.
- Do not implement until the owner authorizes the batch.

Explicit non-goals:

- Implementing any UI cleanup in this phase.
- Inventing a component backlog from the tree.
- Restyling, modernizing, simplifying, or creating a parallel design system (`GROUNDING.md` locked visual system; D-02).
- Reopening product gaps that `docs/planning/PROGRESS.md` recorded as not reopening UI work (dedicated Background Agent submission page, standalone Contacts page, Mail-account removal), unless the owner names those as cleanup items.

Deferred options:

- Phase 01 plan for tracker schema and batch contract.
- Phase 02 review / Phase 03 implementation of the batch.

Constraints:

- V-002 / D-02: exact Browser Voice visual system.
- Grounding: “No existing feature is reinvented, materially redesigned, or independently reimplemented for convenience, preference, cleanup, or novelty.”
- `docs/planning/PROGRESS.md` (2026-09-02): owner visual QA accepted; remaining product gaps “do not reopen UI work.” This new request is a later change and must not silently treat that as cancelled except where the owner names a component.
- Capacity: one owner, one agent; batch implement after the list is complete.

### Premises

| ID | Statement | Type | Source and applicability | Validation/status | Owner / dependents |
|---|---|---|---|---|---|
| P-01 | Owner wants UI component cleanup, listed one-by-one, then implemented as one batch. | Owner constraint | 2026-09-11 chat | Recorded | Tracker + later batch contract |
| P-02 | A markdown tracking file is required. | Owner constraint | 2026-09-11 chat | Recorded; path not specified | Tracker artifact |
| P-03 | Browser Voice visual system is locked; do not restyle/modernize/simplify without a later explicit owner decision. | Owner constraint | `GROUNDING.md`; `04-UX-AND-ONBOARDING-CONTRACT.md`; D-02 | Frozen | Any UI edit |
| P-04 | “Cleanup” for convenience/novelty is prohibited by product grounding. | Owner constraint | `GROUNDING.md` non-negotiable constraints | Frozen | Batch implementation |
| P-05 | Public-facing UI passed owner visual QA on 2026-09-02. | Observation | `docs/planning/PROGRESS.md` | Recorded as of that date | Regression risk of visual edits |
| P-06 | Frontend UI lives mainly under `frontend/src/browser-voice/` (panels, dialogs, CSS). | Observation | workspace glob 2026-09-11 | Tree snapshot only; not a backlog | Tracker population |
| P-07 | Cleanup meaning is defined per queued item; first item is copy + layout reorder. | Owner constraint | 2026-09-11 workspace-page instruction | Recorded for UIC-Q-001 | Tracker + batch |
| P-08 | `docs/planning/PROJECT-STATE.md` did not exist before this phase; product grounding already lived in `GROUNDING.md`. | Observation | glob 2026-09-11 | This file is the index, not a second product constitution | Planning index |

### Requirements

| ID | Required behavior / invariant | Authority | Positive scenario | Negative or failure scenario | Acceptance owner |
|---|---|---|---|---|---|
| UIC-001 | Track only owner-named UI components in one markdown list until the owner authorizes the batch. | P-01, P-02 | Owner names `SettingsPanel`; it appears as queued, not implemented. | Agent implements on first name, or invents extra components. | Owner |
| UIC-002 | Do not change locked Browser Voice visuals unless the owner explicitly reopens the lock for that item. | P-03, P-04, V-002 | A named hygiene item removes unused CSS with no visual change. | Agent “modernizes” spacing/colors as cleanup. | Owner |
| UIC-003 | Batch implementation happens only after the owner says the list is complete and to proceed. | P-01 | Owner finishes naming, then says implement; one change set follows. | Agent starts editing after the first item. | Owner |

### Material decisions

**MD-UIC-01 — Meaning of “cleanup” vs visual lock**

1. Question: Does owner-requested UI cleanup authorize visual/interaction change, or only non-visual hygiene (dead code, unused CSS, copy errors the owner names)?
2. Authority: `GROUNDING.md` locked visual system and anti-rewrite-for-cleanup; 2026-09-11 request does not define the word.
3. Alternatives: (A) visual restyle blocked unless named reopen; (B) owner intends visual cleanup and is reopening D-02 per item; (C) mixed, per-item.
4. Selected: **per-item owner instruction**. No blanket visual restyle. UIC-Q-001 is copy + moving existing `Up one folder` below the directory title/list. Status `CONTINUE` for queuing; implementation still waits for batch authorization.
5. Counterexample: treating unused-CSS deletion as permission to restyle Settings.
6. Dependents: tracker schema, later batch contract.
7. Result: `CONTINUE` (queue); implementation remains deferred.

**MD-UIC-02 — Tracking file location**

1. Question: Where should the tracking markdown live?
2. Authority: owner asked for “some type of md file”; AGENTS.MD defaults extra planning to `docs/planning/`. Product status remains in this index.
3. Alternatives: (A) `docs/planning/UI-COMPONENT-CLEANUP.md`; (B) a file the owner names; (C) only a section in this `PROJECT-STATE.md`.
4. Selected: `docs/planning/UI-COMPONENT-CLEANUP.md` as a **queue**, not a second visual authority.
5. Counterexample: a tracker that restates UX contract and becomes a competing visual spec.
6. Dependents: queued items and later batch contract.
7. Result: `CONTINUE`.

Unresolved choices and affected work:

- Batch implementation still unauthorized until the owner says the list is complete.
- Possessive title uses signed-in `displayName` + `'s Workspace`; unusual names (already ending in `s`) not specified — labeled assumption: always `'s`.

Failure criteria for the later plan:

- Visual drift from Browser Voice without an explicit per-item reopen.
- Invented backlog.
- Incremental implementation against the batch instruction.
- Tracker becoming a second UX constitution.

Change and revalidation triggers:

- Owner defines cleanup type or names a tracker path.
- Owner names the first component (queue only until batch is authorized).
- Owner visual QA of 2026-09-02 is treated as stale for any component whose look will change.

---

## Vault A2A Link-native — Phase 00 grounding

Revision: `VAULT-A2A-LINK-NATIVE-GROUNDING-2026-09-15-r1`.  
Phase: Phase 00 complete. No design, no contracts, no implementation.

### Owner request

Original instructions (2026-09-15 chat):

- Vault has two agents (voice and background). The product should be native to Link.
- Build in the agent-to-agent framework/protocol so it is ready to be enabled.
- Follow the standard: Hermes A2A user guide (`https://hermes-agent.nousresearch.com/docs/user-guide/messaging/a2a`) plus bearer tokens / two-way communication (server or client) and the collab plugin.
- Built-in for Vault; the user can enable/disable.
- Must work natively with Link.
- Use OpenClaw or Hermes as reference; determine which follows the A2A standard correctly.
- Use anti-drift. Approach only in this phase.

Later correction: continue Phase 00 after aborted fetches; do not stop mid-grounding.
Later correction (2026-09-15): A2A and collab must live in Vault’s **proper built-in options** (same class as existing Capabilities “Built into Vault” on/off plugins), not as an extra install/fork of Hermes/OpenClaw plus a side plugin.
Later correction (2026-09-15): Collab plugins for Hermes and OpenClaw already exist. Do **not** rebuild that logic. Reuse the full plugin code from the platform that matches Vault most closely; only small adjustments.
Later correction (2026-09-15): A2A must be **inbound and outbound**. Inbound work goes to the **Background text-based agent**, not Voice.
Later correction (2026-09-15): Owner will discuss Link-native / ports / C04 **after this feature add is done** (C01–C03: builtin Agent2Agent, inbound+outbound, collab reuse). Do not reopen C04 in this pass.

Delegated authority: record grounding, premises, requirements, and Material Decision Gates in this index. Inspect Vault and Link trees and current A2A primary sources.

Reserved: Phase 01 plan; implementation in Vault or Link; claiming official A2A certification; shipping inbound execution that weakens Vault local identity; requiring Link for local-only A2A; forking Hermes/OpenClaw source; treating collab as the protocol; VPS/production Link security-tree deploys.

Acceptance owner: repository owner (Christian). Agent does not grant acceptance.

### Grounding

Audience and actual use scenario:

- A Vault user turns Agent-to-Agent on or off. Voice and Background talk to other A2A agents (Hermes, OpenClaw, another Vault) on the Linux Foundation A2A 1.0 JSON-RPC path, with bearer credentials, as client and (when enabled) as server. **This pass** uses existing Vault listen/connect **ports** (loopback Card URLs). Link Agent Network is optional later connectivity, not a prerequisite.

Observable success (this change, not whole-product GA):

- Grounding states what already exists, what the protocol requires, how Hermes vs OpenClaw relate to that protocol, and what “Link-native” and “enable/disable” mean without choosing an implementation design.

Current scope:

- Phase 00 inventory and classification for Vault A2A + Link-native enablement.

Explicit non-goals (this phase):

- Designing adapters, schemas, UI, or contracts.
- Implementing inbound A2A, collab, or a Link `vault` platform.
- Changing Hermes/OpenClaw product source.
- Replacing official A2A with a Vault-only RPC.
- Mixing dashboard remote access (Custom HTTP to `:8766`) with Agent Network.

Deferred options:

- Phase 01 bound/plan; Link-side platform adapter; inbound principal choice; whether collab is default-on with A2A.

Constraints:

- `GROUNDING.md`: Link/Tailscale remain optional connectivity; do not reinvent existing Vault features.
- `docs/PLATFORM-GUIDE.md`: A2A is currently outbound-only; inbound external execution of Vault is not implemented; remote routing is operator-supplied HTTPS (Link/Tailscale/proxy).
- `docs/evidence/2026-08-31-AGENT2AGENT-LIVE-TEST-LOG.md`: inbound omitted because Vault has no non-human execution principal; reusing a browser session would weaken local identity.
- Link Agent Network must stay transport/config, not an A2A rewrite (`A2A-MDG-02` in the Link tree).
- Official A2A retrieved 2026-09-15 from `https://a2a-protocol.org/latest/specification/`.
- Hermes user guide retrieved 2026-09-15 from the owner URL.

### Premises

| ID | Statement | Type | Source and applicability | Validation/status | Owner / dependents |
| --- | --- | --- | --- | --- | --- |
| VA2A-P01 | Official A2A v1.0 (Linux Foundation) is the inter-agent protocol: Agent Card, JSON-RPC binding methods including `SendMessage` / `GetTask`, context, bearer/HTTP auth errors. It is not a private network or orchestration runtime. | External documented fact | a2a-protocol.org specification TOC and auth error text, 2026-09-15 | Page retrieved; full method schemas not line-copied | Protocol authority |
| VA2A-P02 | Hermes documents bidirectional A2A: outbound `a2a_agents` + bearer `auth.token`; inbound Agent Card at `/.well-known/agent-card.json`, JSON-RPC `POST /`, canonical methods `SendMessage`/`GetTask` plus pre-1.0 aliases `message/send`; inbound peer credentials `A2A_PEER_TOKENS`; remote needs token + `A2A_HOST`. | External documented fact | Hermes A2A user guide, 2026-09-15 | HTML retrieved | Reference, not a requirement to copy Hermes config keys |
| VA2A-P03 | Hermes states interoperability with official `a2a-sdk` and other A2A peers. | External documented fact | Same Hermes page | Marketing/interop claim; not a lab re-run today | Reference |
| VA2A-P04 | OpenClaw 2026.8.1 exposes an A2A channel with Agent Card and JSON-RPC; Link configures `channels.a2a.peers` where inbound accept is `token` and outbound call is `outboundToken`. | Validated fact | Vault live log 2026-08-31; Link OpenClaw `reconcile.py` | Live outbound from Vault succeeded; inbound auth is OpenClaw product behavior | Reference for config shape, not the spec |
| VA2A-P05 | Neither Hermes nor OpenClaw *is* the A2A standard. Both are product implementations. Hermes’ published A2A guide currently matches the spec’s JSON-RPC method names and the client/server split more explicitly than OpenClaw’s peer-map config. | Validated fact with limit | P01–P04 | Does not prove OpenClaw wire messages are non-compliant | Approach: spec first, Hermes as documented bidirectional reference, OpenClaw as a proven peer |
| VA2A-P06 | Vault already has outbound A2A: shared Voice/Background tools, Agent Card discovery, `Authorization: Bearer`, JSON-RPC `SendMessage`/`GetTask`, `A2A-Version: 1.0`, per-connection `enabled`, encrypted tokens. Live Hermes and OpenClaw outbound proofs exist. | Validated fact | `app/vault_runtime/agent_network/`; live test log | 2026-08-31; not re-run this phase | Reuse, do not reinvent outbound client |
| VA2A-P07 | Vault inbound A2A server is not implemented. Documented reason: no non-human execution principal. | Validated fact | PLATFORM-GUIDE; live test log | Current product limit | Two-way / server requirement |
| VA2A-P08 | Link-native Agent Network for Hermes/OpenClaw is: connector apply + platform `reconcile.py` writing that product’s config + opaque TLS. Link does not implement A2A JSON-RPC. | Validated fact | Link adapters; `LINK-A2A-LAYERS-GROUNDING-2026-09-15-r1` | Link tree 2026-09-15 | What “native to Link” can reuse |
| VA2A-P09 | Vault’s published Link instructions today add a **Custom HTTP/WebSocket** service to `http://127.0.0.1:8766` for the dashboard. That is explicitly separate from Link **Agents**. | Validated fact | `docs/RESONO-LABS-LINK.md` | Current docs | Must not conflate dashboard tunnel with A2A |
| VA2A-P10 | `link-a2a-collab` is a host plugin wrapping `SendMessage`+`GetTask` for blocking turns. It is not required by official A2A. Official A2A already has send, get-task, streaming, `contextId`. | Validated fact | Link collab README; A2L-D03; spec TOC | Collab is optional UX | Enable/disable of collab vs protocol |
| VA2A-P11 | Collab JSON-RPC uses method `SendMessage` and role `user`; Vault outbound uses `ROLE_USER` and `messageId`. Both claim A2A v1.0; payload details may differ. | Observation | `a2a_rpc.py`; Vault `client.py` | Not proven which peers accept both shapes | Interop tests, not design this phase |
| VA2A-P12 | Product `GROUNDING.md` still lists Link as an optional connectivity adapter. Owner now wants A2A ready and Link-native. Local A2A without Link remains possible (loopback Hermes proof). | Owner constraint + fact | GROUNDING.md; owner 2026-09-15; live log | Tension is about optional Link, not about using A2A | Do not make Vault unusable without Link |
| VA2A-P14 | Vault already has workspace-scoped built-in options (`BUILTIN_PLUGINS`, Capabilities “Built into Vault”, default off). Owner requires A2A and collab to be that kind of option, not a separately installed platform plugin. | Owner constraint + validated fact | 2026-09-15 chat; `builtin_plugins.py`; `CapabilitiesPanel.tsx` | Tree 2026-09-15 | Product surface |
| VA2A-P15 | Link already ships collab as Hermes Python plugin + OpenClaw JS extension sharing `TurnCoordinator` / `SendMessage`+`GetTask` behavior (`A2A_network_plugins/link-a2a-collab/`). Owner forbids rebuilding that logic in Vault. | Owner constraint + validated fact | 2026-09-15 chat; Hermes `tools.py`; OpenClaw `turn-coordinator.js`; `coordinator.py` | Read 2026-09-15 | C03 |
| VA2A-P16 | Owner requires both inbound (Vault as A2A server) and outbound (Vault as A2A client). Inbound tasks execute on the Background text-based agent, not Voice. | Owner constraint | 2026-09-15 chat | Recorded | R03, R10, D03, D06, C02 |
| VA2A-P17 | Owner 2026-09-15: Link first-class Agent adapter (`VA2A-C04` / O5) is **not required for this pass**. Vault already has the A2A pathway; setup is **port numbers** (inbound `127.0.0.1:8768` by default; outbound Card URLs). Missing a Link `vault` Agent profile is **not a blocker**. | Owner constraint | 2026-09-15 chat | Recorded | Current program is C01–C03; R05 only if a later pass authorizes Link-repo work |

### Requirements

| ID | Required behavior / invariant | Authority | Positive scenario | Negative or failure scenario | Acceptance owner |
| --- | --- | --- | --- | --- | --- |
| VA2A-R01 | On-the-wire agent messaging uses official A2A 1.0 JSON-RPC (Agent Card + `SendMessage`/`GetTask` or documented spec equivalents), not a Vault-only or Link-only RPC. | Owner; P01 | Vault Voice sends to stock Hermes using Agent Card + Bearer + `SendMessage`. | Vault invents `/vault-a2a` that only Vault understands. | Owner |
| VA2A-R02 | Bearer (or the scheme advertised on the Agent Card) authenticates A2A HTTP. Inbound accept tokens and outbound call tokens remain distinct when both directions exist. | Owner; P02; P04; OpenClaw 401 incident on Link | Hermes presents inbound bearer; Vault server accepts that peer token; Vault outbound uses a different peer token. | One shared secret overwritten so reverse 401s. | Owner |
| VA2A-R03 | When Agent2Agent is on, Vault is both A2A **client** (outbound) and A2A **server** (inbound Agent Card + JSON-RPC). When it is off, outbound tools and the inbound listener are both off. | Owner; P16 | Peer `SendMessage`s to Vault and Vault `SendMessage`s to a peer. | Enable only outbound connect UI with no inbound card/listener. | Owner |
| VA2A-R10 | Inbound A2A tasks are executed only by the Background text-based agent. Voice may send outbound; Voice must not be the inbound execution principal. | Owner 2026-09-15; R08 | Hermes SendMessage is handled as a Background run. | Inbound text is injected into the live Voice session. | Owner |
| VA2A-R04 | Voice and Background share the same A2A protocol machinery; they are not two protocols. | Owner; P06 | Background send uses the same client as Voice. | Only Voice gets A2A. | Owner |
| VA2A-R05 | If a **later** pass adds Link-native Vault, that means a Link **Agent** integration (not Custom HTTP dashboard as A2A). **Not a current-pass requirement.** This pass is complete for connectivity when loopback ports and Card URLs work without Link. | Owner 2026-09-15 P17; P08; P09; R07 | Operator points Hermes/OpenClaw at `http://127.0.0.1:8768/.well-known/agent-card.json` plus inbound Bearer. | Treating “no Link Agent profile yet” as blocking Vault A2A. | Owner |
| VA2A-R06 | Collab, if included, remains a plugin/helper on top of A2A, enable/disable-able, without patching Hermes/OpenClaw source. It is not a substitute for R01–R03. | Owner; P10 | User disables collab; A2A send/get-task still works. | Collab hooks become the only way two agents can talk. | Owner |
| VA2A-R07 | Local loopback A2A must work without Link. Link remains optional for remote reachability. | P12; GROUNDING.md | Vault on one host talks to local Hermes on 127.0.0.1 without a Link grant. | A2A enable requires a Link account. | Owner |
| VA2A-R08 | Do not reuse a signed-in browser session as the inbound A2A execution principal. | P07; live test log | Inbound tasks run as an explicit agent principal. | Inbound A2A executes as the user’s web session. | Owner |
| VA2A-R09 | Agent-to-Agent protocol and Collab appear as first-class built-in Vault options (catalog + on/off, not removable sideloads). Connection management stays on the existing Agent2Agent page. | Owner 2026-09-15; P14 | User turns Agent2Agent on under Built into Vault, then connects peers. | User must pip-install or copy OpenClaw/Hermes plugin files to get Vault A2A. | Owner |

### Material decisions

**VA2A-D01 — Who is the A2A standard?**

1. Question: Should Vault copy Hermes, copy OpenClaw, or follow official A2A?
2. Authority/evidence: owner asked which of OC/Hermes follows the standard; P01–P05; Hermes guide; spec TOC.
3. Alternatives: (A) Hermes is the standard; (B) OpenClaw is the standard; (C) official A2A is the standard; products are references.
4. Selected: **(C)**. Hermes is the better **documented bidirectional** reference (client + server, Agent Card, Bearer, canonical `SendMessage` + aliases). OpenClaw is a **valid A2A peer** with a different config model (`token` vs `outboundToken`) that Link already had to get right. Vault should interoperate with both, not become either product.
5. Counterexample: implementing only OpenClaw `channels.a2a.peers` and calling that “the A2A standard.”
6. Dependents: later plan, client/server, Link adapter.
7. Result: `CONTINUE`.

**VA2A-D02 — What “native to Link” means**

1. Question: Dashboard Custom HTTP vs Link Agent Network?
2. Authority: owner “native to Link”; P08–P09; RESONO-LABS-LINK.md.
3. Alternatives: (A) only document dashboard tunnel; (B) first-class Link Agent platform for Vault A2A; (C) both remain, strictly separated.
4. Selected: **(C)**. Dashboard remote access stays Custom HTTP. A2A Link-native is Agent Network. Not designed this phase.
5. Counterexample: exposing `/.well-known/agent-card.json` only through the dashboard hostname without an Agent profile.
6. Dependents: Link repo work is a later, separately grounded change.
7. Result: `CONTINUE` for meaning; Link implementation reserved.

**VA2A-D03 — Two-way / inbound vs prior Vault limit**

1. Question: Does this owner request reopen inbound A2A?
2. Authority: owner “inbound and outbound”; P16; live-test identity warning.
3. Alternatives: (A) outbound-only; (B) inbound and outbound; (C) inbound deferred.
4. Selected: **(B)**. Prior outbound-only product limit is reopened. Inbound is required, not optional later work.
5. Counterexample: shipping only gated outbound tools and calling the feature complete.
6. Dependents: O3, C02, R03, R10.
7. Result: `CONTINUE`.

**VA2A-D04 — Collab vs protocol**

1. Question: Is collab required to “follow the standard”?
2. Authority: owner listed collab; P10; A2L-D03; later “built-in options.”
3. Alternatives: (A) collab is the A2A implementation; (B) collab is a second built-in option; (C) omit collab.
4. Selected: **(B)**. Protocol is R01–R03. Collab is a built-in on/off helper (R09), default off, requires Agent2Agent on. Not an OpenClaw/Hermes file drop.
5. Counterexample: blocking stock `SendMessage` unless collab is installed from Link’s extension tree.
6. Dependents: Phase 01 inclusion in first program.
7. Result: `CONTINUE` — collab is in current scope as a builtin option.

**VA2A-D06 — Inbound execution principal (resolved in Phase 01)**

See plan decision VA2A-D06. Grounding VA2A-D03 remains CONDITIONAL only for implementation detail that Phase 01 now selects Background Agent.

**VA2A-D05 — Fork platforms?**

1. Question: Patch Hermes/OpenClaw plus a plugin?
2. Authority: owner prior Link discussion; this request “follow the standard.”
3. Alternatives: (A) fork agent products; (B) Vault implements A2A + optional collab + Link adapter writes Vault config.
4. Selected: **(B)**. Same rule as Link collab: no platform source forks.
5. Counterexample: vendoring a modified OpenClaw gateway.
6. Dependents: all implementation.
7. Result: `CONTINUE`.

Unresolved after Phase 01 (Link and payload details only):

- Whether Link grows a `vault` Agent profile in the same program or a follow-on (O5).
- Exact JSON-RPC payload fields (`ROLE_USER` vs `user`, `messageId`) against current spec text (C02/C03 interop tests).

Inbound principal is Background (VA2A-D06). Collab is a second builtin with C03, not bundled on with Agent2Agent.

Failure criteria for the later plan:

- Plan that treats Hermes or OpenClaw config as the spec.
- Plan that uses Custom HTTP dashboard as A2A.
- Plan that makes Link mandatory for local A2A.
- Plan that implements inbound as the browser session.
- Plan that replaces A2A with collab-only tools.
- Plan that forks Hermes/OpenClaw.
- Plan that redesigns unrelated UI cleanup or ships Link dirty security trees.

Change and revalidation triggers:

- Official A2A spec method names or Agent Card paths change.
- Hermes/OpenClaw inbound auth model changes.
- Owner picks inbound principal or excludes inbound.
- Owner excludes collab from first enablement.
- Owner authorizes or forbids Link-repo adapter work.

---

## Plan

Revision / candidate identity: `VAULT-A2A-LINK-NATIVE-PLAN-2026-09-15-r2` (corrected after Phase 02; not owner-accepted).  
Grounding and decision input versions: `VAULT-A2A-LINK-NATIVE-GROUNDING-2026-09-15-r1` plus owner 2026-09-15 built-in-options correction (P14, R09).  
Current scope: Built-in Agent2Agent option; **outbound and inbound** A2A (inbound → Background text agent); Collab reuses Hermes/Python donor in C03.  
Deferred: **C04 / O5 Link Agent adapter** (owner 2026-09-15: not necessary for this pass); dashboard Custom HTTP changes; UI cleanup; forking Hermes/OpenClaw; official A2A certification claims; streaming/push-notification completeness beyond send + get-task needed for two-way text.

| Outcome ID | Requirement IDs | Deliverable | Dependencies and readiness | Verification / evidence | Owner and capacity | Recovery |
| --- | --- | --- | --- | --- | --- | --- |
| VA2A-O1 | R04, R07, R09 | Built-in option `agent2agent` in `BUILTIN_PLUGINS` and Capabilities “Built into Vault”, default off, not deletable. Agent2Agent page remains peer connections and refuses new connects while the option is off. | Builtin catalog and panel exist | Toggle off: tools refuse and Connect is disabled; toggle on: option persists per workspace | One agent | Revert catalog key; option stays off |
| VA2A-O1b | R06, R09 | Built-in option `agent2agent_collab` plus collab tools (C03). Do not ship the Collab switch in C01 without tools. | O1; C03 | See O4 | One agent | — |
| VA2A-O2 | R01, R02, R04, R07, R09 | Existing outbound `agent2agent_list` / `agent2agent_send` run only when `agent2agent` is on; per-connection `enabled` still applies | O1; existing client | Send while builtin off fails closed; send while on to live Hermes still works | One agent | Keep client; restore ungated tools only if owner rolls back |
| VA2A-O3 | R01–R04, R07, R08, R10, P16 | Inbound A2A server required in this program: Agent Card + JSON-RPC on a loopback listener separate from dashboard auth; inbound bearer ≠ outbound token; **every inbound task runs as the Background text agent** | O1 | Unauthenticated 401; Bearer accepted; cookie rejected; work is a Background run not Voice | One agent | Stop listener; outbound remains |
| VA2A-O4 | R01, R06, R09, P15 | Built-in Collab option that **reuses** Link `link_a2a_collab` + Hermes plugin code (full coordinator/RPC/store/tools). Small Vault bindings only (peer list from Vault connections, builtin on/off, Voice/Background catalog). Not a new collab engine. OpenClaw JS plugin stays on OpenClaw hosts. | O1; existing Link collab tree | Collab off: protocol send still works; collab on: donor `a2a_collab_turn` wait path works | One agent | Disable builtin; keep donor files unused |
| VA2A-O5 | R05 (later pass only), R07 | Optional later Link **Agent** adapter. **Not this pass.** Local A2A uses listen/connect ports without it. | Owner P17 | N/A this pass | Follow-on | Leave Vault listener |

Sequence and rationale: builtin option first so both directions can be switched off; outbound gate on the existing client; inbound server to Background (C02); collab donor (C03). **Link Agent adapter is not in the sequence for this pass** (P17): ports and Card URLs are the pathway.

Near-term contract allocation (outcomes only, not READY):

- `VA2A-C01` — O1+O2 builtin Agent2Agent option and outbound gate (not Collab catalog yet).
- `VA2A-C02` — O3 inbound server; inbound execution **must** be Background text agent (owner-locked).
- `VA2A-C03` — O4 reuse Hermes/Python collab donor; do not rewrite coordinator.
- `VA2A-C04` — O5 Link adapter. **Deferred this pass** (owner 2026-09-15). Not READY. Do not implement.

Known assumptions, blockers, and dependent outcomes:

- Assumption: default off matches other builtins (Hermes also ships outbound A2A tools off by default).
- O5 / C04 deferred this pass by owner; not a current-program blocker.
- UI cleanup remains unrelated.

### Plan material decisions

**VA2A-D06 — Inbound principal**

1. Question: Who executes inbound A2A tasks?
2. Authority: owner 2026-09-15 “inbound goes to the background text based agent”; R08; R10.
3. Alternatives: Voice session; Background text agent; new third agent.
4. Selected: **Background text-based agent**. Voice remains outbound client only for inbound work.
5. Counterexample: inbound handler uses the signed-in local API cookie or the Voice session.
6. Dependents: C02.
7. Result: `CONTINUE`. Supercedes planner-only selection; this is now an owner constraint.

**VA2A-D07 — Where the A2A server listens**

1. Question: Same port as dashboard/local API or a dedicated A2A listener?
2. Authority: R08; Hermes dedicated A2A port; RESONO-LABS-LINK dashboard vs Agents.
3. Alternatives: (A) JSON-RPC on `/agent2agent` of the browser API; (B) dedicated loopback A2A listener; (C) only via Link relay.
4. Selected: **(B)**. Management UI stays on existing local API. A2A wire protocol does not share the browser session listener.
5. Counterexample: `SendMessage` accepted because the user is logged into Vault in a browser.
6. Dependents: C02, C04 listen URL.
7. Result: `CONTINUE`.

**VA2A-D08 — Collab implementation home**

1. Question: Rebuild collab in Vault, or reuse the existing Hermes/OpenClaw plugin code?
2. Authority: owner 2026-09-15 “THERE IS NO NEED TO REBUILD THOSE PLUGINS. WE JUST REUSE THE FULL CODE… small adjustments.” P15. Vault is a Python tool catalog (`ToolDefinition`), not OpenClaw’s JS `definePluginEntry`.
3. Alternatives: (A) rewrite send+poll in `A2AService`; (B) copy OpenClaw JS into Vault; (C) reuse `link_a2a_collab` + Hermes Python plugin as donor, swap only host bindings.
4. Selected: **(C)**. Donor is the Hermes-side plugin because Vault is Python tools like Hermes, not an OpenClaw gateway. Reuse `TurnCoordinator`, `a2a_rpc.py`, `store.py`, tool names `a2a_collab_turn` / `a2a_collab_list`, and Hermes `tools.py` formatting. Adjust `_load_peer` to Vault A2A connections and register on Vault’s catalog / builtin option. Do not port OpenClaw `index.js` hooks unless a later contract proves a gap. Do not rethink wait/poll/contextId logic.
5. Counterexample: a new Vault-only collab protocol or a from-scratch poller that ignores `link_a2a_collab`.
6. Dependents: C03; O4; architecture collab row.
7. Result: `CONTINUE`. Supercedes the earlier “implement Vault tools using A2AClient GetTask poller” wording.

Later outcomes still needing detail after C02: remote bind/`A2A_PUBLIC_URL` equivalent; streaming; inbound rate limits; per-peer inbound allowlists (C02 uses one workspace inbound token).

**VA2A-D09 — Inbound accept credential**

1. Question: How do peers authenticate to Vault-as-server without colliding with outbound connection tokens?
2. Authority: R02; OpenClaw `token` vs `outboundToken` 401; encrypted outbound token already on `vault_a2a_connections`.
3. Alternatives: (A) reuse each connection’s outbound token inbound; (B) one workspace inbound Bearer, distinct from every outbound token; (C) per-peer inbound tokens in C02.
4. Selected: **(B)** for C02. Generate and store an encrypted workspace inbound token (not in builtin plugin JSON returned to Library). Outbound `credential_*` columns stay call-out only.
5. Counterexample: putting the inbound Bearer in `BUILTIN_PLUGINS` configuration so `/builtin-plugins` shows it; or accepting a connection’s outbound token as inbound Bearer.
6. Dependents: C02, C04.
7. Result: `CONTINUE`.

**VA2A-D10 — Listener multiplicity**

1. Question: One port per workspace or one process listener?
2. Authority: D07 dedicated listener; R07 loopback; local Vault is one process.
3. Alternatives: (A) one `127.0.0.1` port; Bearer selects workspace; (B) port per workspace; (C) path prefix `/workspaces/{id}`.
4. Selected: **(A)**. Card JSON is scoped by the presenting Bearer.
5. Counterexample: JSON-RPC on dashboard `:8766` with a workspace query string and a browser cookie.
6. Dependents: C02.
7. Result: `CONTINUE`.

**VA2A-D11 — Background run session for inbound**

1. Question: `BackgroundAgentService.submit` requires `local_sessions.session_id`. Which session?
2. Authority: R08, R10; runs FK to `local_sessions`; UI `/background/runs` uses the browser `principal.session_id`.
3. Alternatives: (A) current browser cookie session; (B) dedicated inbound session row whose login token is discarded (FK only); (C) change Background schema to drop session FK.
4. Selected: **(B)**. Create/reuse a workspace inbound session via existing `create_session`; never Set-Cookie that session; never use the A2A Bearer as that session’s login secret.
5. Counterexample: inbound `SendMessage` submits with `principal.session_id` from a dashboard cookie on the A2A port.
6. Dependents: C02.
7. Result: `CONTINUE`.

**VA2A-D12 — Loopback port**

1. Question: Which bind/port?
2. Authority: D07; existing 8765 HTTPS UI, 8766 Link dashboard bridge, 8767 browser media.
3. Alternatives: (A) 8767; (B) 8768 default `RESONO_VAULT_A2A_LISTEN_PORT`; (C) 9900 because Hermes live-test used it.
4. Selected: **(B)** `127.0.0.1:8768` default. Tests may bind port 0.
5. Counterexample: sharing 8766 with Custom HTTP.
6. Dependents: C02; C04 public URL later.
7. Result: `CONTINUE`.

**VA2A-D13 — Agent Card GET auth**

1. Question: Is `/.well-known/agent-card.json` public on loopback?
2. Authority: R02; Vault `A2AClient.discover` already sends Bearer; local process isolation is weak.
3. Alternatives: (A) unauthenticated GET; (B) same inbound Bearer as JSON-RPC.
4. Selected: **(B)** for C02.
5. Counterexample: unauthenticated card on a later non-loopback bind.
6. Dependents: C02.
7. Result: `CONTINUE`.

## Architecture

Revision: `VAULT-A2A-LINK-NATIVE-ARCH-2026-09-15-r2` (r1 plus inbound listener row).  
Existing conventions and inspected files: `02-ARCHITECTURE-AND-DATA-BOUNDARIES.md`; `app/vault_runtime/builtin_plugins.py`; `app/vault_runtime/agent_network/{client,service,tools,repository}.py`; `frontend/src/browser-voice/{CapabilitiesPanel.tsx,BrowserVoiceApp.tsx,localApi.ts}`; `docs/RESONO-LABS-LINK.md`.

| Module or artifact | Owns | Actual paths | Public interface | May depend on | Must not own | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| Built-in options catalog | On/off + settings keys for Agent2Agent and Collab | `app/vault_runtime/builtin_plugins.py`; `/builtin-plugins` | Plugin list/update API | Identity/workspace scope | A2A JSON-RPC; peer credentials | Vault |
| Collab builtin | Host bindings for reused donor | `app/vault_runtime/agent_network/collab/` (donor coordinator/rpc/store/types; Vault `_load_peer` in `tools.py`) | `a2a_collab_turn` / `a2a_collab_list` | Donor coordinator; Vault A2A connections; builtin flag | New collab protocol; OpenClaw JS runtime inside Vault | Vault C03 |
| Agent2Agent UI | Peer connect/remove/activity | `BrowserVoiceApp.tsx` Agent2Agent panel; `localApi.ts` | Existing `/agent2agent/*` | Local API | Builtin catalog layout (Capabilities owns that) | Vault |
| Capabilities UI | Built-into-Vault switches | `CapabilitiesPanel.tsx`; `localApi.ts` builtin types | `/builtin-plugins` | Catalog | New visual system | Vault |
| A2A inbound listener | Loopback Agent Card + JSON-RPC; Bearer workspace inbound token; no dashboard cookie | `app/vault_runtime/agent_network/` (C02 `inbound.py` beside client/service) | `GET /.well-known/agent-card.json`; `POST /` JSON-RPC `SendMessage`/`GetTask` (and documented aliases) | Background submit; A2A repository inbound secrets; builtin enabled | Dashboard session auth; Voice execution; Link nginx | Vault C02 |
| Background Agent | Executes inbound A2A work | existing system_agents / background runtime | Internal invocation from A2A server | A2A task text only | Direct datastore access for external peers | Vault |
| Link Agent adapter | Later: write Vault A2A listen/peers via apply | Link `adapters/platforms/` (future `vault`) | Connector apply | Vault inbound URL | A2A method implementation; dashboard nginx | Link follow-on |
| Dashboard Link service | Remote Vault UI | Custom HTTP `:8766` docs | Unchanged | Connector | Agent Card | Docs/ops |

Global invariants:

- External agents never get canonical datastore or workspace paths (`02-ARCHITECTURE`).
- Inbound accept token ≠ outbound call token for the same peer.
- Builtin Agent2Agent off ⇒ no inbound listener and no outbound A2A tools.
- Collab off ⇒ no collab tools; protocol tools may still run if Agent2Agent is on.
- Link optional for local loopback.

New-file and new-directory policy: extend `agent_network/` and builtin catalog. New directory only if C02 cannot place an inbound HTTP server beside existing files; contract must name it. Do not add `A2A_network_plugins/` into Vault.

Verification commands and what each checks:

- Existing `tests/unit/test_agent2agent_client.py` plus new tests for builtin gate, inbound 401, inbound SendMessage→Background, collab poll.
- Frontend tests that Capabilities lists the two builtins; Agent2Agent page still connects peers.
- Manual: builtins off/on; local Hermes card; no cookie on A2A port.

Enforcement level: local advisory tests until merge; no claim of merge lock.

---

## Review

Review ID: `VAULT-A2A-LINK-NATIVE-REVIEW-2026-09-15-r1`  
Target: plan `VAULT-A2A-LINK-NATIVE-PLAN-2026-09-15-r1` then corrected `r2`; contract `VA2A-C01` r1.  
Reviewer type: **internal self-review** (same model/context). Not owner acceptance. Not a fresh-context review.

Required checks: owner request vs plan; R01–R09 trace; failure criteria; module ownership; C01 minimality; builtin pattern reuse (`availability` on tools); Agent2Agent UI vs Capabilities split.

Independently sourced counterexamples: inert Collab toggle (R09); A2A RPC on dashboard cookie (R08); Custom HTTP as A2A (R05); Link required for local (R07).

| ID | Severity | Exact evidence | Violated source | Dependents | Verification / correction / new design | Resolution |
| --- | --- | --- | --- | --- | --- | --- |
| F-01 | major | Plan O1/C01 listed both `agent2agent` and `agent2agent_collab` while C03 owns collab tools | R09 (option must be a real built-in, not a dead switch) | C01 | Correction | Split O1b/C03; C01 is Agent2Agent only. Plan r2. |
| F-02 | major | Grounding still listed inbound principal as unresolved after D06 | VA2A-D06 | C02 | Correction | Unresolved list updated. |
| F-03 | minor | Premises skip P13 | Record hygiene | None | Correction deferred | No plan effect. |
| F-04 | minor | Phase 00 “current scope” still says inventory-only | Phase text drift | Readers | Correction deferred | Requirements still govern. |
| F-05 | minor | Voice prompt always tells the model to use `agent2agent_send` even if the option is off | R09 / existing plugin `availability` pattern | C01 | Correction in C01 | Guidance only when builtin on. |

Decision: **PASS** on plan **r2** for C01 as the first slice only. **Inbound plus outbound is the product** (P16). C02 is required next and is owner-locked to the Background text agent. Collab (C03) follows. **C04 is not in this pass** (P17).

Permitted next action: Phase 03 for `VA2A-C01` r1 READY only.

Unperformed checks: live Hermes re-run; official A2A schema line-by-line; fresh-context review.

## Contract

ID: `VA2A-C01`  
Revision: r1  
Lifecycle: **VERIFIED** (implementer review of actual diff; not owner-accepted; not CLOSED)  
Governing inputs: grounding `VAULT-A2A-LINK-NATIVE-GROUNDING-2026-09-15-r1`; plan/arch `…-PLAN-2026-09-15-r2` / `…-ARCH-2026-09-15-r1`; review `…-REVIEW-2026-09-15-r1`.

Requirement IDs: R04, R07, R09, and outbound half of R01 (existing client unchanged).  
Outcome: User can turn **Agent2Agent** on/off under Built into Vault. While off, Voice/Background cannot list/send A2A and the Agent2Agent page does not add connections. While on, existing outbound client and connection APIs work as today.  
Non-goals: inbound listener **in this slice** (required immediately as C02, not dropped); collab builtin; Link adapter; payload/role changes; visual restyle; GROUNDING.md rewrite.

Owning module: builtin catalog + A2A tools + Agent2Agent panel.  
Inspected: `builtin_plugins.py`, `builtin_plugin_tools.py` (`availability` + enabled check), `agent_network/tools.py`, `composition.py`, `CapabilitiesPanel.tsx`, `localApi.ts` `BuiltinPlugin.key`, `BrowserVoiceApp.tsx` `Agent2AgentPanel`, `voice/context.py`, `test_builtin_plugin_runtime.py`, `test_agent2agent_client.py`.

Allowed existing edits:

- `app/vault_runtime/builtin_plugins.py`
- `app/vault_runtime/agent_network/tools.py`
- `app/vault_runtime/composition.py`
- `app/vault_runtime/voice/context.py`
- `frontend/src/browser-voice/localApi.ts`
- `frontend/src/browser-voice/BrowserVoiceApp.tsx`
- `frontend/src/browser-voice/BrowserVoiceApp.test.tsx` (and other existing frontend tests that list builtin keys)
- `tests/unit/test_tasks_runtime.py`, `tests/unit/test_plugin_voice_guidance.py`, `tests/unit/test_builtin_plugin_runtime.py` as needed
- `CHANGELOG.md`
- `docs/PLATFORM-GUIDE.md` only to state Agent2Agent is a built-in option default off (limitations list)

Phase 03 finding (allowlist gap, not a new module): POST `/agent2agent/connections` is owned by `app/vault_runtime/local_api/app.py`. The contract invariant requires that POST refuse when the option is off; that file was edited. `A2AClient` was not changed.

Allowed new files: `tests/unit/test_agent2agent_builtin_gate.py`  
Allowed new directories: **none**

Forbidden: inbound HTTP server; `agent2agent_collab` key; Link repo; copying `link-a2a-collab`; changing `A2AClient` RPC methods; UI restyle; 0035/security-tree Link deploy.

Invariants:

- `agent2agent` appears in builtin list, `builtIn: true`, `canDelete: false`, default `enabled: false`.
- Tools `agent2agent_list` / `agent2agent_send` use `availability` and refuse when off (`is_error`).
- Connect-agent on Agent2Agent page is disabled with copy that the option is off, when builtin is off.
- `/agent2agent/connections` POST refuses when builtin is off (API must not bypass UI).
- Per-connection `enabled` still applies when builtin is on.
- Voice system text does not instruct `agent2agent_send` when the option is off.
- Existing `A2AClient` SendMessage/GetTask/Bearer unchanged.

Positive: enable builtin; list/send and connect work (unit/API).  
Negative: builtin off; send/list tools error; POST connect 4xx; UI connect disabled. Wrong-but-well-formed: Collab-looking second switch must **not** appear yet.

Checks:

- `python` unit tests for builtin catalog key, tool gate, API POST gate.
- Frontend test: Capabilities shows Agent2Agent; Agent2Agent page connect disabled when off (or equivalent if tests mock plugins).
- Do not claim live Hermes in this contract.

Evidence: test output in the Phase 03 checkpoint.  
Stop: two failed attempts at the same gate; or any inbound/collab/Link edit.  
Rollback: revert C01 files; builtins remain off.  
Checkpoint: tests green; no new dirs.  
Completion: contract VERIFIED by implementer review of actual diff; not owner-accepted.

---

## Review

Review ID: `VAULT-A2A-LINK-NATIVE-REVIEW-2026-09-15-r2`  
Target: plan `VAULT-A2A-LINK-NATIVE-PLAN-2026-09-15-r2` plus D09–D13; architecture r2 inbound row; contract `VA2A-C02` r1.  
Reviewer type: **internal self-review** (same model/context). Not owner acceptance. Not a fresh-context review.

Required checks: O3 vs R01–R04, R07, R08, R10; C01 prerequisite; D07 vs 8766; secret placement; Background vs Voice; cookie counterexample; module owner `agent_network` vs `local_api`.

Independently sourced counterexamples: SendMessage on dashboard cookie (R08); inbound Bearer equal to outbound connection token (R02 / OpenClaw 401); listener on 8766 or 8767; inbound token in `/builtin-plugins`; Voice as inbound principal.

| ID | Severity | Exact evidence | Violated source | Dependents | Verification / correction / new design | Resolution |
| --- | --- | --- | --- | --- | --- | --- |
| F-06 | major | 8767 is `RESONO_VAULT_BROWSER_MEDIA_PORT` | D07 / local API config | C02 bind | Correction | D12 selects 8768 |
| F-07 | major | Builtin plugin `configuration` is returned to Library | R02 secret handling | C02 storage | Correction | D09 forbids inbound token in plugin JSON |
| F-08 | major | Background runs FK `local_sessions`; UI get-run uses browser session | R08; `background_agent/schema.py` | C02 submit | Correction | D11 dedicated inbound session, discarded login secret |
| F-09 | minor | C01 allowlist omitted `local_api/app.py` then had to edit it | C01 Phase 03 finding | C02 management URL | Correction | C02 allowlist includes listen info on local API only |
| F-10 | minor | Remote public URL still unspecified | R07 vs C04 | C04 | Deferred | Loopback only in C02 |

Decision: **PASS** for `VA2A-C02` r1 READY. Plan r2 O3 unchanged. D09–D13 are C02-narrow choices, not collab/Link.

Permitted next action: Phase 03 for `VA2A-C02` r1 only.

Unperformed checks: live Hermes inbound; official A2A schema line-by-line; fresh-context review.

## Contract

ID: `VA2A-C02`  
Revision: r1  
Lifecycle: **VERIFIED** (implementer review of actual diff; not owner-accepted; not CLOSED)  
Governing inputs: grounding `VAULT-A2A-LINK-NATIVE-GROUNDING-2026-09-15-r1`; plan `…-PLAN-2026-09-15-r2` plus D09–D13; arch inbound row (r2); reviews r1 (plan/C01) and r2 (this contract); C01 r1 VERIFIED.

Requirement IDs: R01 (inbound half), R02, R03 inbound listener, R04, R07, R08, R10.  
Outcome: With Agent2Agent on, Vault serves a loopback Agent Card and JSON-RPC so a peer can `SendMessage`; each accepted message becomes a **Background** run (not Voice). With the option off, that listener does not accept work. Peers authenticate with a workspace inbound Bearer that is not the outbound connection token and not a dashboard cookie.  
Non-goals: collab tools; Link adapter; non-loopback bind; streaming/push; per-peer inbound allowlists; changing `A2AClient` outbound RPC; visual restyle; C01 behavior except wiring the listener off when the option is off.

Owning module: A2A inbound listener in `agent_network/` plus Background submit.  
Inspected: `agent_network/{client,service,repository,schema,tools}.py`; `background_agent/{service,contracts,schema,repository}.py`; `local_api/{app,server,config}.py`; `local_identity/repository.py` `create_session`; `composition.py`; `builtin_plugins.py`; C01 gate tests.

Allowed existing edits:

- `app/vault_runtime/agent_network/schema.py`
- `app/vault_runtime/agent_network/repository.py`
- `app/vault_runtime/agent_network/service.py` (start/stop listener with option; do not change outbound SendMessage/GetTask client calls)
- `app/vault_runtime/agent_network/__init__.py`
- `app/vault_runtime/composition.py`
- `app/vault_runtime/local_identity/repository.py` only to call existing `create_session` from inbound code (prefer no edit if callers can use it as-is)
- `app/vault_runtime/local_api/app.py` only GET (and optional rotate POST) `/agent2agent/listen` for card URL + inbound token while option on; CSRF on rotate; never JSON-RPC here
- `app/vault_runtime/builtin_plugins.py` only if enable must trigger inbound credential ensure — **must not** put the Bearer in plugin `configuration` returned to Library
- `frontend/src/browser-voice/localApi.ts`
- `frontend/src/browser-voice/BrowserVoiceApp.tsx` Agent2Agent panel: show this Vault’s card URL + inbound token when option on
- `frontend/src/browser-voice/BrowserVoiceApp.test.tsx`
- `CHANGELOG.md`
- `docs/PLATFORM-GUIDE.md` limitations: inbound is loopback Agent Card + Bearer to Background when option on

Allowed new files:

- `app/vault_runtime/agent_network/inbound.py`
- `tests/unit/test_agent2agent_inbound.py`

Allowed new directories: **none**

Forbidden: JSON-RPC or Agent Card on 8765/8766/8767; accepting Cookie as A2A auth; executing inbound as Voice; `agent2agent_collab`; copying `link-a2a-collab`; Link repo; `A2AClient` method/payload changes; 0.0.0.0 bind; inbound token in `/builtin-plugins` payloads; UI restyle; 0035/security-tree Link deploy.

Invariants:

- Listener binds loopback only; default port 8768 or `RESONO_VAULT_A2A_LISTEN_PORT`; tests may use port 0.
- Option off (no workspace with `agent2agent` enabled) ⇒ no accept of SendMessage (connection refused or 401/404 closed); option on ⇒ Card + RPC up.
- Missing/invalid Bearer on card GET or RPC ⇒ 401. Cookie without valid Bearer ⇒ 401. Valid Bearer + extra Cookie still must not treat Cookie as the principal.
- Inbound Bearer ≠ any stored outbound connection token for that workspace.
- `SendMessage` (and `message/send` if accepted as alias) calls `BackgroundAgentService.submit` with AgentKind Background / no Voice session id as execution principal.
- `GetTask` (and `tasks/get` if aliased) returns that run’s A2A task state, not a Voice transcript.
- Card advertises JSON-RPC 1.0 so existing `A2AClient.discover` can load it (same origin RPC URL).
- Library builtin plugin JSON does not contain the inbound secret.

Positive: option on; Bearer card GET; SendMessage → background submit mocked; GetTask maps run state; listen info on Agent2Agent page.  
Negative: option off; no Bearer; Cookie-only; outbound token as Bearer; SendMessage must not call a Voice coordinator. Wrong-but-well-formed: collab RPC methods not implemented (method not found), not treated as protocol success.

Checks:

- `.venv/bin/python -m pytest -q tests/unit/test_agent2agent_inbound.py tests/unit/test_agent2agent_builtin_gate.py tests/unit/test_agent2agent_client.py`
- `npm test -- src/browser-voice/BrowserVoiceApp.test.tsx` (listen copy when on; still disabled connect when off)
- Do not claim live Hermes inbound in this contract.

Evidence: Phase 03 checkpoint table.  
Stop: two failed attempts at the same auth or principal gate; any collab/Link/non-loopback edit.  
Rollback: stop listener; leave outbound C01 gates; unused inbound table rows inert.  
Checkpoint: tests green; no new directories.  
Completion: VERIFIED by implementer review of actual diff; not owner-accepted.

---

## Evidence

Candidate identity (and what the identity excludes): Vault tree working copy for `VA2A-C01` only. Excludes inbound listener, collab tools, Link adapter, `A2AClient` RPC, Link 0035/security-tree deploy.

Contract and requirement IDs: `VA2A-C01` r1; R04, R07, R09; outbound half of R01.

Environment and relevant versions (no secrets): Vault `.venv` CPython 3.13.2; frontend vitest 4.1.9. No live Hermes.

Baseline failures and how established: first POST-off test hit 502 because the handler read `service.repository` before the option check; corrected by gating POST first.

| Check / exact command or manual steps | Expected | Actual / exit | Evidence link | Date |
| --- | --- | --- | --- | --- |
| `/home/christian/Documents/Projects/ReSono-Labs-Vault/.venv/bin/python -m pytest -q tests/unit/test_agent2agent_builtin_gate.py tests/unit/test_plugin_voice_guidance.py tests/unit/test_agent2agent_client.py tests/unit/test_tasks_runtime.py` | catalog key; tools hidden/refused off; send on; POST 400 off; POST 201 on; client unchanged; no `agent2agent_send` in voice text when option not enabled | 13 passed, exit 0 | this table | 2026-09-15 |
| `npm test -- src/browser-voice/BrowserVoiceApp.test.tsx` in `frontend/` | Library Plugin list shows Agent2Agent Built into Vault; Connect agent disabled when off; no Collab switch | 7 passed, exit 0 | this table | 2026-09-15 |

Failed, skipped, or unavailable checks: live Hermes; owner UI acceptance; inbound execution.

Structural review result: **PASS**. Policy stays on builtin `enabled` + `availability` (same pattern as other Built into Vault options). UI disable is not the only gate. `local_api/app.py` is the existing POST owner; allowlist omitted it. GET list/delete while off still work (add-connection is what C01 forbids). No inbound/collab/Link files. Implementer does not grant owner acceptance.

## Evidence

Candidate identity (and what the identity excludes): Vault working copy for `VA2A-C02` inbound listener. Excludes collab tools, Link adapter, `A2AClient` RPC changes, non-loopback bind, live Hermes inbound.

Contract and requirement IDs: `VA2A-C02` r1; R01 inbound, R02, R03 listener, R04, R07, R08, R10.

Environment and relevant versions (no secrets): Vault `.venv` CPython 3.13.2; frontend vitest 4.1.9. No live Hermes inbound.

Baseline failures and how established: inbound HTTP server instance was not retained in composition (risk of GC); retained on `A2AService._inbound_http` and stopped with the poller.

| Check / exact command or manual steps | Expected | Actual / exit | Evidence link | Date |
| --- | --- | --- | --- | --- |
| `.venv/bin/python -m pytest -q tests/unit/test_agent2agent_inbound.py tests/unit/test_agent2agent_builtin_gate.py tests/unit/test_agent2agent_client.py tests/unit/test_security_primitives.py` | prior inbound checks plus Bearer-only (no Basic/malformed); WWW-Authenticate; card `securitySchemes`; connect refuses inbound secret reuse; `token_equals` | 30 passed, exit 0 | this table | 2026-09-15 |
| `npm test -- src/browser-voice/BrowserVoiceApp.test.tsx` in `frontend/` | inbound card hidden when off; shown with card URL + token when on; Connect still disabled when off | 8 passed, exit 0 | this table | 2026-09-15 |

Failed, skipped, or unavailable checks: live Hermes inbound to Background; owner acceptance; remote/public URL.

Structural review result: **PASS**. Wire protocol lives in `agent_network/inbound.py`, not on 8765/8766/8767. Dashboard GET `/agent2agent/listen` is management copy only. Inbound Bearer is not plugin JSON. Submit uses Background run request + dedicated session id, not Voice. Implementer does not grant owner acceptance.

---

## Review

Review ID: `VAULT-A2A-LINK-NATIVE-REVIEW-2026-09-15-r3`  
Target: plan r2 O4 / D08; C01+C02 VERIFIED; owner P15/P17; contract `VA2A-C03` r1.  
Reviewer type: **internal self-review**. Not owner acceptance.

Required checks: reuse donor not rewrite; collab is second builtin not a dead switch; Agent2Agent remains the protocol; OpenClaw JS stays out of Vault; C04 not in this slice.

Independently sourced counterexamples: new Vault-only collab RPC; collab on while Agent2Agent off; copying OpenClaw `index.js` into Vault; treating missing Link Agent profile as blocking collab.

| ID | Severity | Exact evidence | Violated source | Dependents | Verification / correction / new design | Resolution |
| --- | --- | --- | --- | --- | --- | --- |
| F-11 | major | Hermes `_load_peer` reads `~/.hermes/config.yaml` | P15 / D08 Vault bindings only | C03 | Correction | C03 replaces `_load_peer` with Vault A2A connections; keep coordinator/rpc/store/format |
| F-12 | minor | Copying donor needs a named directory | Architecture “contract must name it” | C03 | Correction | Allow `app/vault_runtime/agent_network/collab/` |

Decision: **PASS** for `VA2A-C03` r1 READY. C04 remains parked until this feature add is done.

Permitted next action: Phase 03 for `VA2A-C03` r1 only.

Unperformed checks: live collab turn with Hermes; owner acceptance.

## Contract

ID: `VA2A-C03`  
Revision: r1  
Lifecycle: **VERIFIED** (implementer review of actual diff; not owner-accepted; not CLOSED)  
Governing inputs: grounding r1; plan r2 O4 D08; arch collab row; C01+C02 VERIFIED; P15; R06; R09; owner 2026-09-15 reuse-full-code.

Requirement IDs: R06, R09, P15.  
Outcome: User can turn **Collab** on under Built into Vault (default off). It requires Agent2Agent on. Voice/Background get donor tools `a2a_collab_turn` and `a2a_collab_list` that wait on `TurnCoordinator.send(..., wait=True)` against **Vault connected peers**. Stock `agent2agent_send` still works with collab off.  
Non-goals: C04 / Link Agent adapter; rewriting coordinator/poll/contextId; OpenClaw JS in Vault; inbound collab RPC methods; UI restyle.

Owning module: collab builtin + Vault peer binding.  
Inspected: Link `A2A_network_plugins/link-a2a-collab/link_a2a_collab/{coordinator,a2a_rpc,store,types}.py`; Hermes `platforms/hermes/plugin/tools.py`; Vault `builtin_plugins.py`, `agent_network/{tools,service,repository}.py`, `composition.py`, `localApi.ts` BuiltinPlugin key.

Allowed existing edits:

- `app/vault_runtime/builtin_plugins.py` (`agent2agent_collab` spec, empty config)
- `app/vault_runtime/composition.py` (register collab tools)
- `app/vault_runtime/agent_network/tools.py` or a sibling register function if collab tools belong next to A2A tools
- `frontend/src/browser-voice/localApi.ts` BuiltinPlugin key union
- `frontend/src/browser-voice/BrowserVoiceApp.test.tsx` (Capabilities shows Collab; still no dead switch without tools)
- `CHANGELOG.md`
- `docs/PLATFORM-GUIDE.md` limitations: collab builtin default off, requires Agent2Agent

Allowed new files (donor copies + Vault `_load_peer` wrapper + tests):

- `app/vault_runtime/agent_network/collab/__init__.py`
- `app/vault_runtime/agent_network/collab/coordinator.py` (copy of donor `TurnCoordinator`; no logic rewrite)
- `app/vault_runtime/agent_network/collab/a2a_rpc.py` (copy)
- `app/vault_runtime/agent_network/collab/store.py` (copy)
- `app/vault_runtime/agent_network/collab/types.py` (copy)
- `app/vault_runtime/agent_network/collab/tools.py` (Hermes `tools.py` formatting + Vault connection `_load_peer`)
- `tests/unit/test_agent2agent_collab.py`

Allowed new directories: **`app/vault_runtime/agent_network/collab/` only**

Forbidden: inventing a new collab protocol; OpenClaw JS; Link `adapters/platforms/vault`; changing `A2AClient`; inbound listener behavior; C04; 0035/security-tree deploy.

Invariants:

- `agent2agent_collab` in `BUILTIN_PLUGINS`, `builtIn: true`, `canDelete: false`, default off.
- Collab tools use `availability`: both `agent2agent` and `agent2agent_collab` enabled.
- `_load_peer` resolves Vault A2A connections (display name or connection id) and outbound Bearer; not `~/.hermes/config.yaml`.
- `a2a_collab_turn` calls donor `TurnCoordinator().send(..., wait=True)`; `a2a_collab_list` lists donor store turns.
- Agent2Agent on + collab off ⇒ `agent2agent_send` still available; collab tools hidden/refused.
- Wrong-but-well-formed: collab on with Agent2Agent off ⇒ collab tools refuse (not a silent protocol replacement).

Positive: both options on; turn waits; list returns a recorded turn (unit, mocked RPC).  
Negative: either option off; unknown peer; collab tools error (`is_error`).

Checks:

- `.venv/bin/python -m pytest -q tests/unit/test_agent2agent_collab.py tests/unit/test_agent2agent_builtin_gate.py tests/unit/test_agent2agent_inbound.py`
- `npm test -- src/browser-voice/BrowserVoiceApp.test.tsx` (Library shows Collab as Built into Vault)
- Do not claim live Hermes collab in this contract.

Evidence: Phase 03 checkpoint.  
Stop: two failed donor-bind attempts; any C04/Link adapter edit; coordinator rewrite.  
Rollback: remove collab catalog key and `collab/` package; A2A C01/C02 remain.  
Checkpoint: tests green; only the named new directory.  
Completion: VERIFIED by implementer review of actual diff; not owner-accepted.

---

## Evidence

Candidate identity (and what the identity excludes): Vault working copy for `VA2A-C03` collab reuse. Excludes C04 / Link Agent adapter, OpenClaw JS, inbound collab RPC methods, `A2AClient` changes, live Hermes collab.

Contract and requirement IDs: `VA2A-C03` r1; R06, R09, P15.

Environment and relevant versions (no secrets): Vault `.venv` CPython 3.13.2; frontend vitest 4.1.9. No live Hermes collab.

Baseline failures and how established: Library `findByText(/Built into Vault/)` broke once two builtins rendered; test uses `findAllByText`.

| Check / exact command or manual steps | Expected | Actual / exit | Evidence link | Date |
| --- | --- | --- | --- | --- |
| `.venv/bin/python -m pytest -q tests/unit/test_agent2agent_collab.py tests/unit/test_agent2agent_builtin_gate.py tests/unit/test_agent2agent_inbound.py` | collab catalog; tools only when both options on; wait+list with mocked RPC; unknown peer `is_error`; C01 send still on with collab off; inbound card still omits collab | 25 passed, exit 0 | this table | 2026-09-15 |
| `npm test -- src/browser-voice/BrowserVoiceApp.test.tsx` in `frontend/` | Library Plugin list shows Collab Built into Vault | 8 passed, exit 0 | this table | 2026-09-15 |
| `diff -q` donor `coordinator.py` `a2a_rpc.py` `store.py` `types.py` vs Vault `agent_network/collab/` copies | identical | identical, exit 0 | this table | 2026-09-15 |

Failed, skipped, or unavailable checks: live Hermes collab turn; owner acceptance.

Structural review result: **PASS**. Donor coordinator/poll/store unchanged. Vault `_load_peer` uses A2A connections, not `~/.hermes/config.yaml`. Collab tools `availability` requires both builtins. `agent2agent_send` remains when collab is off. No C04/Link adapter. Implementer does not grant owner acceptance.

## Vault Docker inbound publish — later change (2026-09-15)

Owner request: Docker package must publish the A2A inbound route; standalone stays loopback. The Agent2Agent built-in remains the on/off switch. Docker must handle Docker networking (host cannot reach container `127.0.0.1:8768`).

Grounding revision: `VA2A-DOCKER-INBOUND-GROUNDING-2026-09-15-r1`.

Premises: C02 bound inbound to container loopback and forbade `0.0.0.0`; compose published 8765/8766/8790–8810, not 8768; Docker already sets `RESONO_VAULT_RUNTIME_PUBLISH_PORTS=1` and dashboard `LOCAL_API_HOST=0.0.0.0`. Owner 2026-09-15 authorized Docker-specific publish while keeping the option switch.

Requirements: Docker host `127.0.0.1:8768` (or `VAULT_A2A_PORT`) reaches the Card when Agent2Agent is on; option off still 401; standalone still loopback-only bind; Card URL stays `http://127.0.0.1:<port>`; not 8765/8766/8767.

MDG: bind `0.0.0.0` in-container only when `runtime_port_publish_enabled()`; advertise `127.0.0.1`; compose maps host loopback A2A port. Alternative of RuntimePortForwarder rejected as extra hop when inbound can bind all interfaces itself. Result CONTINUE.

Contract `VA2A-C05` r1: Docker compose + listen host. Forbidden: C04 Link `vault` adapter; public internet bind of A2A (`VAULT_BIND_ADDRESS` does not apply to A2A); mixing Card onto 8766.

## Current state

2026-09-17: xAI device-code OAuth is implemented on Connections (start/poll `/providers/xai/oauth/*`, `xai_oauth` tokens, refresh against `auth.x.ai`). Background executor already sends the selected xAI credential to `https://api.x.ai/v1`. Owner must approve the device login in a browser to mint a live token. Agent does not grant acceptance.

Phase 03 implementer-complete for Voice Goal Intake (`voice_mode_switch` / `goal_start`) and Background progress page. Empty requested tool names freeze all Background-visible tools; MCP grants restore at run start; executor uses selected-provider `background_access`. Agent does not grant acceptance.

Phase 03 complete for `VA2A-C05` r1 (Docker inbound publish) and earlier C01–C03. Contracts **VERIFIED** by implementer, not owner-accepted, not CLOSED.

Last verified candidate: Docker compose publishes `127.0.0.1:${VAULT_A2A_PORT:-8768}` and sets `RESONO_VAULT_A2A_LISTEN_PORT`; inbound binds `0.0.0.0` only when runtime port publish is on; Card origin remains `127.0.0.1`. Standalone unchanged loopback bind. Agent2Agent option still gates accept.

C04 / Link-native first-class Vault: grounding **r4**. `LV-C04` apply implemented. Docker companion is the Link routing layer through the host connector companion gateway (unsigned `0.2.78`). Agent TLS is unchanged. O5 unmet. Not owner-accepted. Do not ship mixed Link security trees.

Exact next authorized action: install unsigned `0.2.78`, recreate this Vault image. Pairing/Connect stay as already set. Agent does not grant acceptance.
