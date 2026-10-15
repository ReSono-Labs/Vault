# Code-backed duplication audit — initial findings

2026-10-07. Owner ordered validation, not more implementation. Internal source
inspection; no production/database operation, no deletion or runtime edits.
This supersedes C03B READY and the earlier unsupported remaining-work count.
This is an initial implemented-slice audit, not completed reconciliation of all plans.

## Actual built delta

Tracked runtime delta: memory/service.py backend injection and local_identity/
repository.py one optional conversation-erasure entry. New untracked runtime
packages: memory_search, conversation, decision_routing. Git diff alone omits
these untracked packages; inspected their actual files and implementation manifests.

| Change | Existing code compared | Finding |
|---|---|---|
| memory_search/legacy.py | memory/retrieval.py:MemoryRetriever; memory/service.py baseline diff | Adapter delegates directly; no second retrieval algorithm or store. New seam, existing behavior retained |
| conversation/repository.py:_require_authority | voice/repository.py:_require_authority | Confirmed repeated local authorization SQL/predicate. New shared-lock behavior does not erase the duplicated policy responsibility; consolidation/reuse requires reviewed change |
| conversation/schema.py | voice/schema.py; memory/schema.py | Three new identity/segment/turn tables overlap session/history functions but add submission keys/history version/segments absent from Voice schema. Not a second memory store. Necessity of this separate ownership remains unresolved; unmounted |
| decision_routing/selector.py | existing tools/catalog.py and Voice execution/permission paths | Offline finite selection projection/parser, no tool executor/permission store/model reviewer. No equivalent standalone selector located in inspected runtime; no production integration |
| proposed C03B events | conversation/schema.py submitted turns; memory/schema.py vault_transcript_entries; voice/schema.py provider events/invocations/results | Planned extra user-final event repeats persisted source identity/hash. Necessity was not proved; NOT implemented. READY withdrawn |

## Existing functionality that must not be rebuilt

memory/schema.py already defines canonical records, versions/evidence, transcripts,
summaries, ingestion and real pgvector embeddings. memory/voice_learning.py invokes
existing provider capture and MemoryPipeline.finalize; composition.py mounts this
memory pipeline. memory/openai_reviewer.py is existing factual review.
voice/schema.py already stores provider-event identities, tool-invocation state and
tool results; voice/evidence.py supplies bounded transcript projection. Presence
of an observer class is not proof it is wired universally in composition.
background_agent/sdk_runner.py already collects provided reasoning summaries;
that does not prove capture for every Voice/chat session.

Memory retrieval currently computes cosine over loaded embedding candidates in
memory/retrieval.py, while memory/schema.py contains no HNSW index. Indexed SQL
retrieval is an extension to existing vectors, not a reason for new embedding
storage. Missing full-session summaries/outcome attribution are integration gaps,
not proof that every existing ledger must be replaced.

## Limits and corrective checkpoint

No claim that all remaining packages are new or duplication-free. Retract the
17-work-package answer as an implementation estimate. No new tests run here;
tests cannot establish architectural necessity. Need source-to-plan inventory
for every remaining entry before another READY build. Preserve current owner
changes; do not remove working code to hide overlap. C03B and dependent full
capture/learning cannot advance under the superseded READY package.

The understand-diff skill was inspected for this audit; its prerequisite knowledge
graph is absent, so its graph workflow cannot run (requires /understand first).
Used direct diff, file inventory, schema and call-site inspection instead.
