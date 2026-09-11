# Phase 4 Voice, Background Agent and Tools Evidence

Date: 2026-08-29  
Status: PASS

## Implemented

- Immutable system-agent inventory containing exactly `voice` and
  `background`, with no registration or mutation surface.
- Voice-shaped local PostgreSQL sessions bound to Phase 2 user, workspace and
  local session authority.
- Voice context from local name/experience style plus Phase 3 scoped profile
  memory.
- Provider-neutral realtime request/startup boundary and a bounded OpenAI
  Realtime WebRTC client-secret adapter using only an owner-supplied key.
- Idempotent provider events mapped into bounded Phase 3 transcripts.
- Canonical tool definitions/catalog with JSON Schema, fixed-agent audience,
  explicit local grants, effect classes and observer hooks.
- Voice exact-once invocation with private local result recovery and
  `effect_unknown` on uncertain write failure.
- R1 redacted/bounded tool evidence in the transcript.
- R1 `memory_lookup`, prepare correction, prepare forget and later-confirm
  action tools wired through the canonical catalog.
- One fixed generic R1-derived Background Agent with durable scoped runs,
  legal states, cancellation, progress, output validation, immutable tool
  supply, model/tool limits, queue worker and interrupted-run recovery.
- Strict bounded Voice JSON parsing in the local API.
- Local HTTP contracts for two-agent inventory, Voice start/close and
  Background run submit/read/cancel.

## Verification

The complete suite ran against a disposable loopback-only PostgreSQL 16
instance:

```text
102 passed in 73.24s
```

Coverage includes:

- exact two-agent inventory and rejection of sampled prohibited identities;
- permanent production-source scan for Foundry, Hub, package, Build,
  specialist, generated, marketplace/delegation and hosted authority markers;
- Voice create/open/close/fail and terminal-event rejection;
- cross-user session denial and immediate membership-revocation denial;
- provider event idempotency/conflicting replay rejection and transcript
  capture;
- scoped profile-memory isolation;
- explicit owner grants, non-owner grant denial and immediate grant revocation;
- exact-once write recovery, no duplicate effect and uncertain-effect state;
- redacted tool evidence;
- real memory lookup and later-confirmed correction through the Voice tool
  runtime;
- opaque owner-provider credential separation and provider disconnect cleanup;
- OpenAI Realtime URL, authorization header and donor session/tool/audio
  payload construction without credential leakage into the payload;
- Background legal/illegal transitions, cross-user denial, revocation,
  cancellation, output-schema failure, worker execution and progress counts;
- strict JSON duplicate-key, non-finite, object, encoding, depth and size
  rejection;
- local API CSRF and authenticated Voice/Background flows.

## Donor integrity

The admitted Voice and R1 source hashes matched
`docs/research/PHASE-04-VOICE-BACKGROUND-TOOLS-INVENTORY.md` at exit.

```text
Voice commit: 0f3b34223f745920e79d1d9db301f3b639d08393
Voice tracked diff: 0d9a4ce77e3707940c4f3becc5ecbfb641eb50f4df975c7e971f52e14e6942da
R1 commit: 91d9e70bbe156f03c79399a458416f0bebd20210
R1 tracked diff: 90f9c55912d93683e5e3dea53688b6190c2685c6437259d418520fc6be7551ff
```

Both donor repositories remained read-only from this project. Their unrelated
pre-existing/external dirty state was not cleaned or modified.

## Explicitly absent

- Build Agent, Agent Foundry, Agent Hub, package/specialist/generated agents;
- agent registration, installation, generation, selection or delegation;
- ReSono login, service key, subscription, route grant or cloud control plane;
- Link/Tailscale/A2A/remote management;
- Plugin/Skill/MCP lifecycle, which remains Phase 5;
- Browser Voice source, which remains Phase 6.

The disposable database was stopped/removed, and generated Python cache
directories were removed from the public-facing tree after verification.
