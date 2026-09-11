# Phase 4C R1 Memory and Learning Donor Cut Points

Date: 2026-08-29  
Method: read-only source, test, dependency, and function inspection  
Status: M0 candidate inventory

## Governing requirement

Vault must preserve the complete updated R1 memory/learning behavior inside
Voice Vault's local PostgreSQL, user, and workspace authority. Voice Agent and
Background Agent are the only system-agent identities.

## Voice capture and close authority

Primary donor:

- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/device_runtime/realtime_proxy_service.py`
  - `close_proxy` line 379 closes provider/session state and invokes
    post-session finalization once;
  - `_capture_transcript_event` line 621 captures final user/assistant event
    variants under account/workspace/session scope;
  - `_finalize_post_session_memory` line 701 invokes memory finalization.

Required adaptation: do not port the callback to Platform Learning or Agent
Hub. Those are excluded platform/non-system-agent features. Join Voice capture
and close behavior to the updated R1 local reviewer/pipeline instead.

SHA-256:

- `realtime_proxy_service.py`:
  `5db51370b4a2437eccc77750d051b7688585203c066ce1578d75ef6923cc1882`
- Voice `app/vault_runtime/session_context_builder.py`:
  `949adbcafd7fc353f60f7a8d75897497bc0a4529837bfa43b61969baf91648`
- Voice `app/vault_runtime/session_transcript_capture.py`:
  `6b5f6987080d4db93a3a41ed5d97c38c91b2bda732bb05e976d679dfdba8a7be`

## Updated R1 learning authority

- `runtime/resono_runtime/agents/memory_reviewer.py`:
  `MemoryReviewRunner` line 108, `_summarizer_instructions` line 213, and
  `_run_review_with_agents_sdk` line 402; SHA-256
  `12f494390e171a28b6016ab2df3ffb5e832424982af4a20a30dc6e48a2708267`.
- `runtime/resono_runtime/memory/pipeline.py`:
  `MemoryPipeline.finalize` line 61; SHA-256
  `93840bea2ef14028078de506cc3451a2d8a535f2210f75605becffca11bb37e7`.
- `memory/service.py`: `b2dc24c03d312c74f8aa440feb12b2d493d703560eb2d06cbf8faeda5ed67fe0`.
- `memory/retrieval.py`: `9355edcfad7c1fefc64e1dcb29cbdedf2c89790f064e540f1340608e5236bcf6`.
- `memory/tools.py`: `e9a34c75d644ad0dc63c912fb10a96841d47604517566bd645f06997f936dfc9`.

Composition reference:

- `runtime/resono_runtime/application.py` lines 312–333 composes one reviewer
  capability, pipeline, and service.
- `runtime/resono_runtime/api/routes.py` contains authenticated Voice transcript
  append/finalize and management retry behavior with truthful failures.

The reviewer is capability-only. Its donor file/class name does not authorize
a third system-agent identity.

## Background Agent boundary

Observed R1 behavior:

- `background_agent/composition.py` serializes `memoryReferences`;
- `background_agent/output_contract.py` bounds phase evidence;
- `background_agent/execution.py` persists `agent_evidence` run events;
- `background_agent/instructions.py` requires concise phase evidence; and
- `application.py` enables canonical memory tools for Voice and Background.

No inspected R1 Background file invokes `MemoryPipeline.finalize` or converts a
completed run into canonical memory. Background automatic memory writeback is
therefore not admitted by donor evidence.

## Test donors

- `tests/runtime/test_memory_sessions.py` SHA-256
  `5ccc9a30c06755afd6d39f9fd9b053473fbba6bd5242391f6f941ede61f593a3`:
  provenance, retrieval, idempotency, deletion, offline embeddings, malformed
  extraction, truthful failures, stale recovery, context, and lookup.
- `tests/runtime/test_runtime_http_finalize.py` SHA-256
  `346f9a66cb4b5b870691c2bf8d78acffe88b2b2f14c1381d8834f35c4e324ae0`:
  authenticated transcript intake and finalize behavior.

## Dependencies and adaptations

- Reuse admitted `openai-agents==0.18.3` and the copied R1 SDK runner.
- Resolve keys/models through Vault's encrypted workspace credential store.
- Preserve PostgreSQL, membership, visibility, and revocation below the UI.
- Remove R1 single-user assumptions and Voice cloud/platform callbacks.
- Retain lexical truthfulness when embeddings/reviewer access fails.

## Material decision gates

### D-M1 — Functional authority: `CONTINUE`

Updated R1 controls memory/learning behavior. Voice controls datastore and
local authorization. Replacing R1 reconciliation/reviewer behavior with the
older Voice summary path is the failure counterexample.

### D-M2 — Reviewer identity: `CONTINUE`

R1 composes the reviewer inside the memory service. It is not installed,
selected, delegated, or exposed as an identity. Port it as capability only.

### D-M3 — Background automatic writeback: `BLOCKED/REOPEN`

R1 proves memory references, tools, and durable run evidence but no canonical
writeback. Preserve that exact behavior. Reopen only if another inspected donor
function proves finalization of Background evidence into memory.

## Donor state

Voice commit: `0f3b34223f745920e79d1d9db301f3b639d08393`  
R1 commit: `91d9e70bbe156f03c79399a458416f0bebd20210`

Inspection was read-only. No donor build, format, migration, dependency update,
or code modification was run.
