# R1 Voice Session Prompt, Memory and Tool Trace

Status: SOURCE-VERIFIED CORRECTION INPUT  
Date: 2026-08-29  
Scope: Voice session composition only; no new product features

## Governing requirement

Vault keeps Voice/Vault's local identity, workspace, provider, transcript and
storage boundaries. Updated R1 is the behavior donor for the complete
memory/learning flow and the more evolved local capability projection. Only the
fixed Voice Agent and fixed Background Agent are admitted. Excluded Voice/R1
features remain excluded.

## Evidence method

The existing R1 Understand Anything graph was used for navigation. It describes
commit `970176729dc4ca41d309a127b1dc5a79c11eb204`, while the inspected R1 checkout
is at `91d9e70bbe156f03c79399a458416f0bebd20210` with later uncommitted runtime
changes. Therefore every material graph claim below was verified against the
current source. Neither donor was modified.

## Verified R1 session sequence

1. `ProviderController.create_realtime_call()` mints the session ID before
   context selection.
2. `SessionContextBuilder.build()` selects at most eight approved memories and
   the most recent completed prior-session summary, excluding the new session.
3. `SessionContext.render()` produces bounded natural-language recalled context
   with domain, type, key and confidence; it tells Voice to use recall naturally
   and not announce it unless asked.
4. Voice instruction layers are joined with blank-line boundaries.
5. One canonical `ToolCatalog` projects the Voice tool definitions after
   availability and audience filtering.
6. The OpenAI Realtime payload carries the composed instructions, explicit
   tools, `tool_choice=auto`, audio/transcription configuration and tuned VAD.
7. Final user and assistant text plus bounded redacted tool evidence are stored
   under the same session ID.
8. Close posts the transcript and triggers citation-required, fingerprint-
   idempotent summary/memory finalization; the next session can receive both the
   accepted memories and the prior summary.

Exact sources:

- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/providers/controller.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/providers/openai/platform.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/providers/openai/live_transport.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/realtime/modes.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/session_context.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/evidence.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/pipeline.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/storage/sessions.py`

## Verified R1 tool enumeration

R1 does not maintain separate Voice, Background, Plugin or MCP tool registries.
All definitions enter one `ToolCatalog`. Its provider projection preserves a
single authoritative definition per tool and filters by:

- fixed system-agent audience;
- definition-level availability;
- active audience-resource binding; and
- the current Voice mode or immutable Background-run grant at invocation.

Dynamic MCP tools are atomically projected with `replace_source`; disabling,
removing or restoring a connection replaces that source's complete catalog
slice. Background runs freeze an immutable intersection of canonical catalog,
explicit names, audience and autonomy/effect policy.

Exact sources:

- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/tools/catalog.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/tools/definitions.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/agents/audience.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/agents/routing.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/mcp/lifecycle.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/background_agent/tool_supply.py`

## Verified R1 Skill behavior

Enabled, audience-matched Skills use progressive disclosure. Voice receives
only each Skill's name and description. The canonical `load_agent_skill` tool
is exposed only when at least one Skill is enabled, and loads the full
instructions only when relevant. A Skill's `allowed-tools` metadata never
grants a tool.

Current R1 source also supports a separate owner-managed Voice `SKILLS.MD`.
The newer application wiring passes that document to `ProviderController`, but
no longer composes `SkillActivation.voice_instructions()`. This is an observed
current-source regression, not behavior to port. Vault must compose both proven
layers: owner Voice instructions when present and installed-Skill disclosures.

Exact sources:

- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/skills/activation.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/skills/documents.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/application.py`

## Voice/Vault responsibilities retained

The primary Voice donor remains authoritative for account/workspace profile
context, provider-neutral request construction, canonical Realtime tool payload
translation, authenticated transcript capture and workspace storage ownership:

- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/inference_runtime/realtime_session_builder.py`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/inference_runtime/realtime_runtime_source.py`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/voice_realtime/assistant_runtime.py`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/voice_realtime/realtime_proxy_service.py`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/contracts/internal/openai_realtime_session.py`

Cloud account/profile lookups, hosted authentication, signals, Agent Hub,
Agent Foundry, Build Agent, package agents, External AI, social posts, recipes,
local events and other excluded tool families are not admitted by this trace.

## Confirmed Vault gaps at trace time

The current standalone Vault runtime:

- injects eight memory rows but not the prior completed session summary;
- omits the complete R1 primary Voice and applicable tool-use guidance;
- does not wire installed Skill disclosure or `load_agent_skill` into production;
- does not restore persisted MCP projections on runtime startup;
- lacks R1 `memory_explain` and explicit `memory_remember_intent` behavior;
- emits only the reduced VAD fields and omits R1's complete audio/VAD defaults
  and explicit `tool_choice=auto`;
- supplies the provider a catalog without a recorded per-session capability
  snapshot; and
- has no Voice-to-fixed-Background-Agent goal-intake/tool composition despite
  retaining the fixed Background Agent runtime.

Transcript capture and close-triggered R1 review are present and remain the
base to preserve. The correction must extend that chain, not replace it.

## 2026-08-29 correction status

Implemented from the traced donors, without changing donor code:

- deterministic primary/profile/style/tool/memory/prior-summary/Skill prompt composition;
- one canonical per-session Voice definition snapshot and built-in grant bootstrap;
- Browser Voice handling for `response.function_call_arguments.done`, serialized
  local execution, scoped invocation evidence, provider tool output and response continuation;
- progressive `load_agent_skill` registration and scoped load-time recheck;
- durable MCP projection restoration before a Voice session and invocation-time grant recheck;
- R1 `memory_explain` and `memory_remember_intent` tools;
- R1 PCM 24 kHz, near-field reduction, transcription, tuned server VAD,
  non-interrupting response and `tool_choice=auto` settings; and
- the existing full transcript close/finalize learning chain remains intact.

Still separate work: Voice goal-intake handoff to the already-existing fixed
Background Agent. It must not be represented as complete by this correction.

## Port boundary

Port the traced R1 behavior with the smallest local multi-user adaptations:

1. compose primary Voice, local profile/style, prior summary, scoped memory,
   installed Skill disclosures and owner Voice instructions in a deterministic
   order;
2. project the canonical audience/scoped tool catalog once for session start;
3. restore active scoped MCP projections and recheck grants at call time;
4. add only the missing R1 memory and Skill tools;
5. connect Voice only to the one existing fixed Background Agent; and
6. preserve the current authenticated transcript/finalization path.

No excluded tool family or additional agent identity may enter through this
correction.
