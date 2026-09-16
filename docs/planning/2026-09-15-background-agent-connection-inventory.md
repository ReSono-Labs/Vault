# Background Agent connection inventory

Date: 2026-09-15  
Revision: `BA-INV-2026-09-15-r1`  
Status: Phase 00 grounding inventory. Not a plan. Not implementation.

Owner questions this record answers:

1. Are we not doing “modes” anymore?
2. Is Voice supposed to delegate to Background Agent?
3. Is Background Agent built but disconnected?
4. Is it built with the OpenAI Agents SDK?

---

## What exists (tree, not intent)

### Identities

Vault still has exactly two system agents: Voice and Background (`GET /system-agents` returns `voice`, `background`). Installing plugins/MCP does not add a third identity.

### Background runtime (built)

| Piece | Path | What it does |
|---|---|---|
| Durable runs | `app/vault_runtime/background_agent/service.py` | Queue, 4 worker threads, submit/execute/cancel/fail, recovery |
| PostgreSQL | `schema.py`, `repository.py` | `vault_background_runs` and events |
| Run contract | `contracts.py` | Objective, limits, autonomy, recipe, requested tools |
| Tool freeze | `tool_supply.py` | Per-run intersection of catalog + grants + autonomy + requested names |
| Production executor | `openai_executor.py` | Provider-selected run |
| SDK adapter | `sdk_runner.py` | OpenAI Agents SDK `Agent` + `Runner` |
| Dependency | `pyproject.toml` | `openai-agents==0.18.3` |
| Composition | `composition.py` | Constructs `BackgroundAgentService` with `OpenAIBackgroundExecutor`, calls `start()` |

Gemini Background runs **do not** use the Agents SDK. They use `generateContent` + function declarations in `openai_executor._execute_gemini`. OpenAI API, ChatGPT OAuth (Codex base URL), and xAI use `sdk_runner.run_agent_turn`.

### Callers that can start a Background run (built)

| Caller | How | Notes |
|---|---|---|
| Local API | `POST /background/runs` | Authenticated session + CSRF. Proven by Phase 4 API tests. |
| Inbound A2A | `agent_network/inbound.py` `_send` | Peer message becomes a Background run. Must not use Voice. |

### Callers that cannot start a Background run (absent)

| Expected product path | Tree result |
|---|---|
| Voice tool / goal intake | No Voice tool name, no catalog entry, no session instruction that submits a run |
| Browser Voice UI | No `/background/runs` client, no Background submit page |
| Link connector as Voice | Outbound A2A is Voice/Background **calling peers**, not Voice calling the local Background Agent |

Frontend grep for `/background` under `frontend/src` is empty.

### Voice session (built, separate)

Voice is OpenAI/Gemini/xAI **realtime**, not Agents SDK. Instructions say use only supplied tools. A2A plugin text mentions Background Agent ownership for external-agent work; that text does not create a submit tool.

### Grants (built, apply after a run exists)

Library Voice/Background switches grant **tools** to an audience. They do not start runs. A Background CRM grant is unused until something calls `submit()`.

---

## “Modes” — do not collapse these into one feature

No current Browser Voice control is labeled “modes” for Voice vs Background.

Things that **are** in the tree and are easy to confuse with “modes”:

| Name | Where | User-facing? | Relation to Background |
|---|---|---|---|
| Experience style | Account / Voice instructions | Yes (strict etc.) | Interaction tone only |
| Provider `connectionMode` | Voice session (`webrtc` / websocket) | Transport | Not Background |
| Extension **safe mode** | Library runtime | Yes | Hides third-party tools for both agents |
| Provider **access_mode** | `shared` / `individual` API keys | Account | Credential isolation |
| Background **autonomy** | `limited` / `expanded` / `custom` | API run field, not Voice UI | Limits which effect classes a run may use |
| Background **recipe** | `direct_v1` / `self_review_v1` / `independent_review_v1` | API run field | How the run reviews itself |
| R1 `conversation_mode` / `voice_mode` in donor realtime payloads | Voice donor / R1 copies | Not a Vault product mode switch | Provider session JSON, not Voice→Background |

Things that were **explicitly not imported** as Voice tools (Phase 4 inventory):

- `delegate_task`
- package selection / handoff / resume / cancel
- Agent Foundry / Hub / package identities

Those were treated as **other-agent delegation**, which Grounding forbids. That subtraction is **not** the same as “Voice must never ask the one fixed Background Agent to run.” The Phase 4 inventory said the user may submit work to Background and Voice **may request that fixed service where grounded**; the later prompt-tool correction recorded that Voice goal-intake was **not** completed.

---

## Intended vs built (keep separate)

| Statement | Type | Source |
|---|---|---|
| Exactly one Voice Agent and one Background Agent | Owner constraint | `GROUNDING.md`, V-016 |
| Background uses R1 generic Background Agent + SDK runner as donor | Owner/architecture | `GROUNDING.md`; Phase 4 inventory |
| Voice-to-Background goal-intake remains open | Recorded product gap | `PROGRESS.md` 2026-08-29; research 2026-08-29; PLATFORM-GUIDE §9 no submit page |
| Owner 2026-09-15: “the whole point of the background agent is for voice to delegate tasks to it” | Owner constraint (this change) | this chat |
| Background is “not connected to anything” | False as a total claim | API + inbound A2A + workers exist |
| Background is not connected to **Voice or the web UI** | Verified fact | no Voice tool, no frontend client |

---

## Material Decision Gate

### MDG-BA-01 — What “modes” means

1. Question: Did Vault drop a Voice “modes” product, or was something else never ported?
2. Authority: owner question 2026-09-15; tree; Phase 4 inventory. Evidence does **not** prove a later owner decision to cancel Voice→Background handoff.
3. Alternatives: (A) user-facing Voice/Background mode switch was required and dropped; (B) “modes” meant autonomy/recipe/safe-mode; (C) “modes” meant R1/package `delegate_task` which is forbidden.
4. Selected for this inventory: do not pick A/B/C as a single fact. Record all three as distinct. Function of this choice: prevent a false “we cancelled modes” claim.
5. Counterexample: a locked UX spec named “Voice modes” that this tree implemented and later removed — not found.
6. Dependents: Phase 01 if owner wants a Voice submit path or a UI.
7. Result: **CONDITIONAL** until the owner names which “modes” they mean.

### MDG-BA-02 — Is Background disconnected?

1. Question: Is the Background Agent an unused shell?
2. Evidence: composition starts workers; API submit; inbound A2A submit; Gemini/SDK executors.
3. Alternatives: unused; connected only to API/A2A; connected to Voice (false).
4. Selected: **connected to local API and inbound A2A; not connected to Voice or Browser Voice UI.**
5. Counterexample: a Voice tool that POSTs `/background/runs` — absent.
6. Dependents: any Voice delegation work.
7. Result: **CONTINUE** for inventory; **BLOCKED** for claiming Voice delegation exists.

### MDG-BA-03 — SDK

1. Question: Is Background built on OpenAI Agents SDK?
2. Evidence: `from agents import Agent, Runner`; `openai-agents==0.18.3`; Gemini bypass.
3. Alternatives: SDK-only; mixed; not SDK.
4. Selected: **mixed**. OpenAI-compatible text path uses Agents SDK; Gemini uses native HTTP.
5. Counterexample: Gemini run going through `Runner.run` — code path does not.
6. Dependents: provider work, debugging Voice vs Background confusion.
7. Result: **CONTINUE**.

---

## Requirements (inventory only; not a build contract)

| ID | Required behavior / invariant | Authority | Positive | Negative |
|---|---|---|---|---|
| BA-INV-R1 | Do not describe Voice as able to start Background runs until a Voice tool + API mapping exist | Tree + PROGRESS gap | Voice has no submit tool | Claiming “just ask Voice” as current behavior |
| BA-INV-R2 | Do not treat Library Background grants as run intake | Grant UI + tool_supply | Grant without submit does not create a run | “I toggled Background so Voice can delegate” |
| BA-INV-R3 | Keep two-agent inventory; Voice asking the **fixed** Background service is not a third identity | GROUNDING + Phase 4 inventory | One Background service | Reintroducing `delegate_task` / packages |
| BA-INV-R4 | Preserve recorded gap: goal-intake open until owner-authorized Phase 01+ | PROGRESS | Gap labeled | Closing the gap in chat without a contract |

Acceptance owner: Christian. Agent does not grant acceptance.

---

## Unresolved (ask in Phase 00 / before Phase 01)

- Which “modes” the owner means (MDG-BA-01).
- Whether Voice→Background submit is now in **current** scope (owner 2026-09-15 intent vs frozen “do not reopen UI” / no submit page).
- Whether inbound A2A already counts as “connected enough” for some jobs, or Voice must be the primary intake.

Failure criteria for a later plan: a plan that adds a second agent identity; a plan that treats grants as intake; a plan that copies R1 `delegate_task`.
