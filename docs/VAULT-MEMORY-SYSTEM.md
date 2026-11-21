# The memory system in ReSono Vault

This is the memory system we implemented in our agentic platform, ReSono Vault. It retrieves relevant context while a user is typing or speaking, then learns durable memories from completed sessions. The two paths share the same canonical memory store. Users can benefit from existing context before a response, and every newly learned memory can be traced to the evidence that supports it.

## Live recall before the response

| Surface | How it works | Benefit |
|---|---|---|
| Chat | While the user types, the composer sends debounced draft revisions tagged with an utterance ID. Vault searches existing memory against the evolving request. When the user sends the message, Vault checks that the prepared context still matches the final text and current conversation, permissions, and memory state. The normal retrieval path is available when prepared context cannot be reused. | Starts recall during time the user already spends composing. Edits to the draft, memory changes, and permission changes are accounted for before Chat uses the result. |
| Voice | On supported OpenAI realtime paths, Vault receives incremental transcription while the caller speaks. Transcription comes from the realtime conversation connection or a dedicated live-transcription connection, depending on the setup. Vault assembles successive revisions by audio item and runs them through the same preparation system as Chat. The browser can supply recalled context to the realtime model during the utterance. | Gives the agent an opportunity to recognize references to prior decisions and preferences mid-call, with less need for the caller to explain them again. |
| Shared preparation | Results are bound to the user, workspace, authenticated session, conversation, segment, and utterance. New revisions supersede old ones. The runtime checks current permissions, preferences, history, and memory state before handing results forward. Draft text and partial transcripts are used for preparation. Durable learning operates on finalized captured evidence. | Limits cross-session leakage and stale context, and lets users revise a thought before it becomes part of the evidence used for learning. |

An example is “What did we decide about the launch date?” Recall can start when the request first takes shape and refine as the project name arrives. The benefit depends on the speed and quality of retrieval and, during Voice, the availability of live transcription.

Implementation references: [Chat composer](../frontend/src/browser-voice/conversation/useLivePreparation.ts), [final Chat handoff](../app/vault_runtime/live_memory/chat_runtime.py), [live Voice transcription](../frontend/src/browser-voice/voiceLivePreparation.ts), [current-state validation](../app/vault_runtime/live_memory/current_state.py).

## Conversation tracking and concurrent ingestion

Vault tracks three distinct units in Chat. The **conversation** is the persistent thread. A **segment** is the bounded portion of that thread that Vault reviews as a session. A **turn** is one submitted request and its resulting events. The same conversation can continue in a fresh segment while a sealed segment is under review.

A segment can close explicitly, after 120 seconds of inactivity by default, or when a completed turn brings it to 32 turns or 48,000 bytes of captured text and events. An active response prevents closure. A segment containing unsuccessful turns can close as `incomplete`. Factual review requires complete capture for every turn in a sealed segment.

Different conversations can have active turns and reviews at the same time. The default runtime has four shared worker slots. Within a single conversation, one turn can be active at a time. Every sealed segment has its own durable review state. A PostgreSQL advisory lock fences review ownership for that segment across workers and processes. When different reviews touch the same canonical memory key, a separate lock serializes that write. Independent sessions can publish in different orders.

**Why it matters.** Segments give learning a bounded, identifiable source even when a conversation runs for days. Independent jobs let one session finish while another is active or retrying. Per-key write coordination preserves a consistent record and version history when sessions overlap.

Implementation references: [Conversation schema](../app/vault_runtime/conversation/schema.py), [session closure and queue](../app/vault_runtime/conversation/runtime_store.py), [worker dispatch](../app/vault_runtime/conversation/runtime.py), [memory reconciliation](../app/vault_runtime/memory/repository.py).

## What the memory agent does

| Stage | What Vault does | Benefit |
|---|---|---|
| Assemble evidence | For Chat, loads the original user input, final assistant answers, redacted tool results, and eligible attachment observations. Verifies scope and completeness and fingerprints the ordered source. Voice captures finalized transcript evidence through its own session path and uses the same canonical memory pipeline. | Gives the reviewer a reproducible source and a way to detect changes between analysis and publication. |
| Review and classify | A structured reviewer produces a session summary and zero or more memory candidates. Each candidate cites source entries. The reviewer is instructed to prioritize explicit user statements and verified tool results over unsupported assistant wording. Attachment-derived candidates must carry model-derived authority. The reviewer is instructed to omit credentials, transient requests, live tool-owned state, and unsupported inferences. | Keeps recall focused on information likely to matter later. Citations let Vault show where a memory came from. |
| Checkpoint analysis | Longer sources can be reviewed in bounded windows. Vault saves intermediate analysis, checks citations and coverage, and verifies the source fingerprint and reviewer binding before publication. | Lets large sessions be reviewed in parts and lets eligible retries reuse completed analysis. |
| Reconcile and publish | Checks suppression rules, reconciles candidates against canonical keys, and commits memory records, versions, evidence, and factual review completion together. Records an outcome for each source entry, including when no memory was proposed. Embedding happens separately. | Preserves evidence and completion together, allows a successful zero-memory review, and lets keyword recall work while vector indexing catches up. |

Implementation references: [Chat memory learning](../app/vault_runtime/memory/chat_learning.py), [reviewer contract and instructions](../app/vault_runtime/memory/openai_reviewer.py), [Voice memory learning](../app/vault_runtime/memory/voice_learning.py), [publication pipeline](../app/vault_runtime/memory/pipeline.py).

### What completion means

- **Turn completed** means the response finished. The factual reviewer separately checks whether its source capture is complete.
- **Segment sealed** means the reviewable conversation boundary closed. A sealed segment can enter the durable review queue.
- **Factual review reviewed** means analysis is checkpointed. **Factual review completed** means publication and source coverage committed. Finalizing the same completed source again returns an already-completed result.
- **Overall review completed** means the enabled review consumers reached completion. Factual Memory and procedural Decisions track their own outcomes. Factual memory can already be available while Decisions is still pending or has failed.

The dispatcher scans for due reviews every 30 seconds. A review can retry up to three attempts in a queue cycle. A review can be blocked if Vault cannot establish the required session authority. Eligible work can be recovered after a process exits. These distinctions make status meaningful and let Vault retry the incomplete consumer without republishing a completed factual review.

Implementation references: [Review recovery and states](../app/vault_runtime/conversation/runtime_store.py), [independent review consumers](../app/vault_runtime/conversation/runtime.py).

## Classification and identity

Vault classifies each memory along independent dimensions. A memory might be a `project` domain, `decision` type, and `user_asserted` authority. Those fields describe where it belongs, what it says, and how Vault knows.

| Dimension | Supported values | Benefit |
|---|---|---|
| Domain | `identity`, `personal`, `relationship`, `environment`, `project`, `device`, `platform` | Groups related information and supports domain-aware profile retrieval. |
| Type | `fact`, `preference`, `decision`, `episode`, `constraint`, `correction` | Distinguishes a statement of fact from a choice, preference, event, or operating constraint. |
| Evidence authority | `user_asserted`, `tool_verified`, `model_derived` | Preserves the distinction between what a user said, what a tool verified, and what a model inferred. |
| Confidence | `low`, `medium`, `high` | Gives profile recall a basis for preferring better-supported records. |
| Sensitivity | `normal`, `sensitive` | Lets default profile recall omit sensitive memories. |
| Visibility | `private`, `workspace` | Defines who can access a record. Automatic reviewer output is private. |
| Reconciliation intent | `create`, `confirm`, `correct`, `conflict` | Distinguishes supporting existing information from changing or disputing it. |
| Lifecycle | `active`, `conflicted`, `superseded` | Lets ordinary recall focus on active records. |

The record identity follows **workspace → visibility and owner scope → subject → domain → type → memory key**. An identical confirmation can attach evidence to the existing version. A correction can advance the version and keep the record active. A differing value without correction intent can advance the record into a conflicted state, which ordinary recall excludes. That helps prevent an ambiguous statement from silently becoming the basis for future answers.

A memory of type `decision` records what was decided. The separate procedural **Decisions** system learns reusable patterns for actions and tool selection. It owns its own review, rule, example, and activation records. This lets Vault remember both the outcome of a decision and, where supported, how to approach a similar request later.

Implementation references: [Classification contract](../app/vault_runtime/memory/contracts.py), [record reconciliation](../app/vault_runtime/memory/repository.py), [procedural Decisions schema](../app/vault_runtime/decision_learning/rule_schema.py).

## Storage and retrieval

Vault stores source history, session summaries and review checkpoints, canonical memory records, record versions, cited evidence, and embeddings in PostgreSQL. Versions preserve changes to remembered information. Evidence links a memory back to its transcript or source excerpt. Embeddings support similarity search. Suppression rules can prevent forgotten information from being reintroduced by a later review. This structure gives the agent concise current context and gives operators a way to trace how it was learned.

| Retrieval path | What it returns | Benefit |
|---|---|---|
| Query recall | Scoped lexical and eligible exact matches, combined with semantic similarity when a compatible embedder is available. The indexed backend uses PostgreSQL full-text search and pgvector. | Finds records through both exact terminology and paraphrases. Keyword recall remains available when semantic lookup is unavailable. |
| Profile recall | Active, normal-sensitivity memories with medium or high confidence, prioritized by domain and recency. | Gives the agent a small set of stable context without requiring the user to repeat it. |
| Same-thread continuity | The latest completed review summary from an earlier segment of the same Chat, when available. | Helps a new segment pick up the conversation without replaying the entire thread. |
| External integration | Paired clients such as Hermes and OpenClaw can use scoped search, get, and startup context, as well as proposal and action endpoints. Vault applies its access and write rules. | Lets multiple agents use shared durable context through a common boundary. |

Implementation references: [Memory schema](../app/vault_runtime/memory/schema.py), [query ranking](../app/vault_runtime/memory/retrieval.py), [indexed search](../app/vault_runtime/memory_search/postgres.py), [profile and evidence](../app/vault_runtime/memory/repository.py), [segment summary](../app/vault_runtime/memory/chat_learning.py), [integration service](../app/vault_runtime/external_memory/service.py).

## How to demonstrate it

1. Start typing about a known project decision in Chat and show relevant memory appearing before Send.
2. Ask about that decision aloud on a supported voice connection and show incoming transcript text driving retrieval during the utterance.
3. Explicitly teach Vault a new project preference. End that Chat segment and show its review move to completion while a separate conversation remains usable.
4. Ask about the newly learned preference in the other conversation and inspect the evidence for the recalled record.

This walkthrough demonstrates three user benefits in one sequence. Existing context becomes available earlier, a new fact survives the session in which it was learned, and the recalled fact can be traced back to its source.

*This overview describes the implementation and defaults at commit `5a67208`. Live transcription and semantic recall depend on the deployment’s provider configuration, credentials, and enabled features.*
