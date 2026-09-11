# Phase 4 Voice, Background Agent and Tools Contract

Status: FROZEN FOR IMPLEMENTATION  
Date: 2026-08-29

## Outcome

An authenticated local user can start one Voice Agent session in an authorized
workspace, receive Phase 3 memory context, use an explicitly authorized
built-in tool, capture transcript/evidence, and stop the session. The same
local authority may run one fixed generic Background Agent with durable state,
bounded tools and progress. No other runtime agent identity exists.

## Donor authority

- Voice Vault is primary for Voice session, provider, context, transcript and
  tool behavior.
- The exact fixed R1 `background_agent/` behavior is secondary for the single
  Background Agent only.
- Exact files, hashes and cut points are recorded in
  `docs/research/PHASE-04-VOICE-BACKGROUND-TOOLS-INVENTORY.md`.
- Donors remain read-only. Copy/extract only the current frozen slice.

## First implementation slices

1. Port Voice strict JSON and canonical tool definition/catalog primitives.
2. Implement a fixed two-entry system-agent inventory with no mutation API.
3. Add local PostgreSQL Voice session state bound to Phase 2 user/workspace and
   Phase 3 transcript/memory services.
4. Port Voice context projection from local style plus scoped profile memory.
5. Add provider-neutral Voice session request/event boundaries; owner-provided
   provider configuration is optional and secret values never enter responses,
   logs, prompts or stored session records.
6. Port R1 Background Agent run contracts, progress, tool-supply intersection
   and lifecycle into scoped PostgreSQL.
7. Wire only admitted memory/session tools through the canonical catalog.
   Feature tools follow only after their own dependency closures are grounded.

## Authorization and security

- Authenticated Phase 2 principal supplies `user_id`, `workspace_id` and local
  session authority. Request bodies cannot override them.
- Every Voice/background session lookup, transition and tool call repeats
  active membership scope.
- Tool definitions declare effect (`read`, `write`, `delete`), audience
  (`voice`, `background`, or both), JSON schema and handler ID.
- Tool exposure is the intersection of enabled definition, audience, local
  grant, active workspace membership and per-run limits.
- Every invocation receives a unique call ID. Side effects use donor
  exact-once/effect-unknown behavior where applicable.
- Tool evidence is redacted/bounded before Phase 3 transcript storage.
- Provider credentials are read through a secret boundary and are never
  returned to the model/client or stored in ordinary configuration.
- Disconnect/cancel closes the local session and prevents later events or tool
  calls from being accepted.

## System-agent invariant

The only identities are constant `voice` and `background`. The codebase must
contain no runtime registration, installation, generation, publication,
selection, handoff or package route for agent identities. Background work is a
run of the same fixed Background Agent, not a newly named agent.

The negative inventory test must fail on any registered installable,
generated, specialist, coordinator, developer, marketplace, Foundry, Hub,
package, or Build Agent. Build scripts and CI are ordinary tooling outside the
runtime.

## Explicit exclusions

- Plugin/Skill/MCP import and lifecycle (Phase 5);
- Browser Voice UI copy (Phase 6);
- Link, Tailscale, A2A and remote management;
- Mail, Contacts and Calendar implementation until their newly admitted donor
  dependency slice is frozen in a subsequent contract;
- External AI, social posts, recipes, local events, markets, workouts, weather,
  news and all other unadmitted signal/tool families;
- hosted ReSono login, account, subscription, provider broker, service key,
  route grant, presence, usage reporting or control-plane dependency;
- Agent Foundry, Agent Hub, agent packages, delegation to another identity,
  Build Agent and specialist agents.

## Exit proof

- exact two-agent inventory and adversarial negative source/runtime scan;
- Voice session create/context/event/tool/close on real PostgreSQL;
- cross-user/workspace session and tool denial, including after revocation;
- provider absent and provider disconnect behavior;
- credential/log/response redaction tests;
- strict JSON duplicate/non-finite/depth/size rejection;
- tool schema, audience, grant, effect and call-ID enforcement;
- exact-once behavior for admitted side effects;
- Background Agent queued/running/completed/failed/cancelled transitions,
  tool-budget enforcement and scoped run isolation;
- transcript and redacted tool evidence visible to Phase 3 finalization;
- donor hashes/fingerprints unchanged;
- full regression suite and Phase 4 anti-drift exit review.
