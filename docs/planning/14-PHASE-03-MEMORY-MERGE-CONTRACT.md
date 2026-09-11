# Phase 3 Memory Merge Contract

Status: FROZEN FOR IMPLEMENTATION  
Date: 2026-08-29

## Purpose

Port the existing Voice Vault PostgreSQL memory foundation and merge the
updated R1 memory classification, evidence, reconciliation, ingestion and
retrieval behavior. This is a donor port, not a memory-system redesign.

This phase does not add another agent. Memory review and session finalization
are capabilities run by the fixed Background Agent or by the Voice Agent's
bounded session-finalization path.

## Controlling boundaries

- `GROUNDING.md` controls product scope.
- `INDEX.MD` controls repository ownership.
- `docs/protocols/ANTI-DRIFT-PROTOCOL.md` controls admission and review.
- `docs/research/PHASE-03-VOICE-R1-MEMORY-INVENTORY.md` records donor proof.
- Voice is the primary platform and datastore donor.
- R1 contributes only its updated memory taxonomy and lifecycle behaviors.
- Hosted cloud authentication, hosted account identity and cloud control-plane
  calls are prohibited.
- Only Voice Agent and Background Agent are system agents. No Build Agent,
  memory agent, reviewer agent, specialist, package agent or generated agent
  may be introduced.

## Admitted donor files

Primary Voice root:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/`

- `app/vault_runtime/datastore/schema.py`: PostgreSQL memory-adjacent schema
  forms, adapted to local Phase 2 identities and memberships.
- `app/vault_runtime/datastore/postgres.py`: parameterized persistence and
  scoped query patterns.
- `app/vault_runtime/datastore/domains.py`: domain/content projection.
- `app/vault_runtime/datastore/scope.py`: scope behavior, adapted from hosted
  account ownership to local user membership.
- `app/vault_runtime/runtime_memory/retrieval.py`: scoped text/semantic merge,
  recent-session priority and provider failure fallback.
- `app/vault_runtime/handlers/runtime_memory.py`: bounded ingestion/finalize
  orchestration.
- `app/vault_runtime/session_transcript_capture.py`: deterministic transcript
  identifiers and bounded text/metadata handling.

Required R1 root:
`/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/`

- `runtime/resono_runtime/memory/contracts.py`: contract version 2 and exact
  labels.
- `runtime/resono_runtime/agents/memory_reviewer.py`: review input/output
  validation only; it must not be registered or represented as an agent.
- `runtime/resono_runtime/memory/evidence.py`: bounded, redacted evidence.
- `runtime/resono_runtime/memory/pipeline.py`: fingerprinted idempotent review,
  reconciliation, summary, evidence and optional embedding flow.
- `runtime/resono_runtime/memory/retrieval.py`: lexical, exact and real-semantic
  result merge.
- `runtime/resono_runtime/memory/service.py`: canonical memory operations.
- `runtime/resono_runtime/storage/memory.py`: lifecycle, versions, evidence,
  ingestions, pending actions, embeddings and deletion behavior.
- `runtime/resono_runtime/storage/migrations/v042_domain_memory.py`: schema
  meaning and constraints, translated from SQLite to PostgreSQL.
- `runtime/resono_runtime/memory/tools.py`: prepare/confirm correction and
  forget semantics.

The donor files remain read-only. Copy only bounded code needed by this
contract, preserve provenance, and adapt rather than damage donor projects.

## Canonical schema

Phase 3 may create only these memory-owned PostgreSQL relations:

| Relation | Responsibility |
|---|---|
| `vault_transcript_entries` | ordered bounded user/assistant/tool transcript evidence |
| `vault_session_summaries` | idempotent per-session memory review summary |
| `vault_memory_records` | current canonical memory state and classifications |
| `vault_memory_record_versions` | immutable reconciliation history |
| `vault_memory_evidence` | citations and redacted evidence supporting a version |
| `vault_memory_ingestions` | session/contract/fingerprint idempotency ledger |
| `vault_memory_pending_actions` | same-session two-step correct/forget confirmation |
| `vault_memory_embeddings` | optional real-provider vectors and model metadata |

Document/file storage is not admitted by this phase. Although Voice contains
document tables, file management belongs to a later explicitly grounded UI or
capability phase.

Every scoped relation carries the existing Phase 2 `workspace_id`. Every
user-owned or attributable row carries `user_id`. Canonical memories also carry
`visibility`, limited to `private` or `workspace`.

## Exact classification contract

These values are copied exactly from R1 contract version 2:

- domain: `identity`, `personal`, `relationship`, `environment`, `project`,
  `device`, `platform`;
- type: `fact`, `preference`, `decision`, `episode`, `constraint`, `correction`;
- authority: `user_asserted`, `tool_verified`, `model_derived`;
- reconciliation intent: `create`, `confirm`, `correct`, `conflict`;
- confidence: `low`, `medium`, `high`;
- sensitivity: `normal`, `sensitive`.

Unknown or renamed labels fail validation. Older Voice labels may be migrated
only through an explicit mapping backed by donor evidence; they may not replace
the R1 v2 names.

## Scope and authorization contract

- Every operation derives user and active workspace from the authenticated
  Phase 2 session. Caller-supplied ownership is never authority.
- `private` memory is readable and writable only by its owning user.
- `workspace` memory is readable by current workspace members. Mutation retains
  attributable user ownership and requires current membership.
- Revoked members immediately lose workspace-memory access.
- Canonical key uniqueness includes workspace, visibility and private owner
  where applicable, plus subject, domain, type and memory key. A private record
  can never collide with or overwrite another user's record.
- Session, transcript, pending action, evidence and retrieval queries must all
  repeat the scope predicate. Possessing an object UUID is insufficient.

## Lifecycle contract

1. Store ordered bounded transcript entries using deterministic/idempotent
   donor behavior.
2. Fingerprint the transcript. One session, reviewer-contract version and
   fingerprint may be ingested only once.
3. Validate review candidates against the exact taxonomy and require cited
   transcript/evidence entries.
4. Reconcile by canonical key using R1 `create`, `confirm`, `correct` or
   `conflict` behavior.
5. Store an immutable version and attributable evidence for every accepted
   change.
6. Persist the session summary even when embeddings are unavailable.
7. Store an embedding only when produced by a real configured provider.

Profile retrieval admits active, normal-sensitivity, medium/high-confidence
memory according to donor behavior. Sensitive memory remains stored and
inspectable under its authorization boundary but is excluded from automatic
profile injection.

## Correction and forgetting contract

The exact R1 two-step behavior is required:

- prepare returns the exact current content and, for correction, proposed new
  content;
- confirmation must be a later user utterance in the same authenticated user,
  workspace and voice session;
- a pending action is single-use;
- correction reconciles a high-confidence `user_asserted` correction and
  stores the confirming utterance as evidence;
- forget deletes the canonical memory and its active embedding from retrieval,
  following donor deletion semantics;
- another user's action ID, an expired/consumed action, a different session, or
  the preparing utterance cannot authorize a mutation.

No caller-provided utterance identifier alone proves confirmation. The
confirmation entry must exist as a later user transcript row inside the same
authorized scope.

## Retrieval contract

- lexical retrieval is always available;
- exact substring matches receive the R1 exact-match priority;
- semantic retrieval runs only with compatible vectors from a real configured
  embedding provider;
- provider absence or failure cleanly falls back to lexical/exact results;
- no hash, pseudo-random or fabricated vector may be labeled semantic;
- merge methods are reported as `lexical`, `exact` and/or `semantic`;
- result limit is capped at 25 and defaults to 8;
- R1 cosine floor is 0.20;
- all candidate paths apply the same user/workspace/visibility authorization
  before scoring and returning content.

## Explicit exclusions

- additional agents of any name or role;
- Build Agent, Agent Foundry, Agent Hub or agent package installation;
- shared cross-build memory APIs for Hermes, OpenClaw or other products;
- Link or Tailscale routing;
- hosted cloud authentication or synchronization;
- document/file UI and storage;
- fabricated local semantic embeddings;
- new taxonomy labels, auto-sharing rules, retention policy inventions or
  memory features not present in admitted donors.

Future shared Vault storage remains a deferred architectural option. Phase 3
must keep internal service boundaries clean enough for a future authorized
consumer interface, but it must not implement that interface now.

## Required tests and exit evidence

Phase 3 cannot exit until evidence records:

- clean schema creation on real PostgreSQL;
- exact-label validation and invalid-label rejection;
- create, confirm, correct and conflict version/evidence behavior;
- transcript fingerprint idempotency;
- prepared correction and forget rejection without a real later same-session
  user entry;
- successful correction and forget plus single-use action enforcement;
- private isolation between all local users;
- workspace visibility for active members and immediate denial after revoke;
- UUID/object-ID probing denial across users and workspaces;
- sensitive/profile filtering;
- lexical and exact retrieval;
- real-provider semantic retrieval when a test provider is explicitly supplied,
  otherwise recorded as untested—not simulated;
- provider failure/absence lexical fallback;
- no additional agent registration or agent-like runtime identity;
- donor fingerprints unchanged;
- full regression suite passing.

Exit requires an anti-drift review against `GROUNDING.md`, this contract and
`INDEX.MD`, followed by updates to `INDEX.MD` and `docs/planning/PROGRESS.md`.
