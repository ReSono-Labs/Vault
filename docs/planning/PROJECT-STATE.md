# Project state (index)

Date: 2026-09-11  
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
| Method | Anti-drift constitution | `/home/christian/Documents/Projects/drift-protection/AI-PLANNING-PROTOCOL.md` |

Do not copy constitution or phase prompts into this repository.

---

## Owner request

Original instructions and later corrections:

- 2026-09-11 owner: this project has a lot of UI component cleanup. Components will be given one by one. The agent must create some type of markdown file for tracking, then perform all listed cleanups at once (not incrementally as each item arrives).
- 2026-09-11 owner (first item): Workspace page heading `Your workspace` / private-files subtitle → `{displayName}'s Workspace`, drop subtitle; keep `local` / swipe-hint row on top; move `Up one folder` to the bottom.

Delegated authority / reserved decisions:

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

## Plan / Architecture / Contracts

Unchanged product plan remains in existing `docs/planning/` files. No plan, architecture rewrite, or READY contract for UI cleanup in this revision.

---

## Current state

Phase: **03 Build** for UI cleanup batch UIC-Q-001–004.  
Active contract: owner-authorized batch (queue in `docs/planning/UI-COMPONENT-CLEANUP.md`).  
Modified files: Browser Voice workspace, connections, settings CSS, tracker, this index, CHANGELOG.  
Blocker: none.  
Last verified candidate: frontend tests 18 passed; Docker `./vault-package install` healthy at `https://127.0.0.1:8765` serving `browser-voice-DdraQO94.js`.  
Next action: owner live-check Workspace, Connections AI & Voice, and Settings Linked folders. Agent does not grant acceptance.
