# Phase 3 Voice Vault and R1 Memory Inventory

Date: 2026-08-29  
Method: read-only source and schema inspection

## Architectural result

Voice Vault remains the canonical PostgreSQL datastore, scope, transcript,
summary, memory, embedding, document and hybrid-retrieval authority. The updated
R1 memory system is a required semantic/lifecycle merge into those boundaries;
R1 SQLite and its global-primary-user assumptions are not copied as a second
store.

## Primary Voice donors

Root:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/`

| Donor | SHA-256 | Borrowed responsibility |
|---|---|---|
| `app/vault_runtime/datastore/schema.py` | `9d169640b13bc1681c4f01d2736a417308a256900b16b216b691f61ed34c6db2` | PostgreSQL private schema shapes for transcripts, summaries, memory, embeddings and documents |
| `app/vault_runtime/datastore/postgres.py` | `5eaca93846ba45e9ae440b4c094d3b38c16c47c93afc1bd1e49585141308666c` | parameterized scoped persistence/search patterns |
| `app/vault_runtime/datastore/domains.py` | `1f6e065fe658fd57ebd7d80b49cb27047ad11606a2d7b31bab717d1a3eb30281` | domain-to-table/content projection |
| `app/vault_runtime/datastore/scope.py` | `30800f63a91f7f84a4990fc19c048cd44821f1fcf55cd58c7d18505f645c8a22` | account/workspace scope projection, adapted to Phase 2 local authority |
| `app/vault_runtime/runtime_memory/retrieval.py` | `07a59905f004ab0a8a5c4ab5b8e7b5c4eb5fe6ec8a1874537782bede0566f471` | workspace-scoped text + provider-embedding hybrid search, recent-session priority and offline fallback |
| `app/vault_runtime/runtime_memory/embeddings.py` | `12840dd2ac44457960c9b57f80fb4a836313026d3b59515710157bf7fb41a9cf` | legacy local hash-vector code; explicitly not accepted as semantic embedding |
| `app/vault_runtime/handlers/runtime_memory.py` | `3cc41de5f02863bc288ace24e86afb9019ac70239cee740556b27384bc39b4e3` | bounded runtime-memory ingestion/finalization handler behavior |
| `app/vault_runtime/session_transcript_capture.py` | `6b5f6987080d4db93a3a41ed5d97c38c91b2bda732bb05e976d679dfdba8a7be` | deterministic transcript IDs, bounded private text and safe metadata |

The full Voice schema contains later features and prohibited package-agent
tables, so it cannot be copied whole. Phase 3 extracts only memory/document
statements and methods.

## Required updated R1 donors

Root: `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/`

| Donor | SHA-256 | Required merge |
|---|---|---|
| `runtime/resono_runtime/memory/contracts.py` | `c7db82aae93bf8c4a2f7aea841f58c0dff9afea42447d2e30fa0472a3c15831f` | exact domain/type/intent/authority enums and contract version 2 |
| `runtime/resono_runtime/agents/memory_reviewer.py` | `12f494390e171a28b6016ab2df3ffb5e832424982af4a20a30dc6e48a2708267` | candidate validation, citation requirement, prompt/parse contract; capability only, not another agent identity |
| `runtime/resono_runtime/memory/evidence.py` | `7e0e97720a758d32e1c840252d4f9850a781b9f1c435a80246c533a6baae9438` | bounded/redacted tool evidence capture |
| `runtime/resono_runtime/memory/pipeline.py` | `93840bea2ef14028078de506cc3451a2d8a535f2210f75605becffca11bb37e7` | transcript fingerprint idempotency, review, reconcile, summary, evidence and optional embeddings |
| `runtime/resono_runtime/memory/retrieval.py` | `9355edcfad7c1fefc64e1dcb29cbdedf2c89790f064e540f1340608e5236bcf6` | lexical/exact/semantic merge, score floor, limit and cosine behavior |
| `runtime/resono_runtime/memory/service.py` | `b2dc24c03d312c74f8aa440feb12b2d493d703560eb2d06cbf8faeda5ed67fe0` | canonical operations, search result and offline embedding availability |
| `runtime/resono_runtime/storage/memory.py` | `53af00341c10cb9a53abb7f19d432a1475990c6b58ac9b666292c7c29d076541` | versions, evidence, reconciliation, ingestion, pending action, embeddings and deletion semantics |
| `runtime/resono_runtime/storage/migrations/v042_domain_memory.py` | `682f572a6d0203235764ba9ebcfdac6d1397c785f128111f388035dea27cbba7` | lifecycle columns/tables/indexes and legacy backfill meaning |

## Exact required labels

- domains: `identity`, `personal`, `relationship`, `environment`, `project`,
  `device`, `platform`;
- memory types: `fact`, `preference`, `decision`, `episode`, `constraint`,
  `correction`;
- source authority: `user_asserted`, `tool_verified`, `model_derived`;
- reconciliation: `create`, `confirm`, `correct`, `conflict`;
- confidence: `low`, `medium`, `high`;
- sensitivity: `normal`, `sensitive`.

Names may not be renamed, collapsed, or inferred from older Voice
`memory_class` values once a v2 record exists.

## Scope adaptation required by Phase 2

Voice's hosted projection assumes one account owns a workspace. Standalone
Vault supports shared workspace membership and private user memory. Therefore
every canonical record/query must carry:

- creator/owner `user_id` for attribution;
- `workspace_id` validated against active local membership; and
- visibility `private` or `workspace`.

Private records are visible only to the owning user even inside a shared
workspace. Workspace records are visible to current members and become
immediately inaccessible after membership revocation. This is a required local
scope adaptation, not a new memory feature.

## Agent and embedding boundary

The R1 memory reviewer is classified `CAPABILITY_ONLY`. It runs as a bounded
review job owned by the fixed Background Agent or Voice session-finalization
path; it never registers a third identity, accepts delegation, or appears in
the agent inventory.

Real provider embeddings are optional. If unavailable, memory remains durable,
inspectable and retrievable lexically. Voice local hash vectors must not be
reported as semantic matches and are excluded from the canonical embedding
path. No provider credential enters stored memory/evidence.

## Confirmation and deletion boundary

R1 correction/forget operations are prepared first and consumed only after a
later confirmed utterance/event tied to the same user, workspace, session and
action. Forgetting must preserve attributable audit/version evidence as allowed
by retention while removing the active content and embedding from retrieval.
Direct database deletes or caller-provided confirmation IDs are not authority.
