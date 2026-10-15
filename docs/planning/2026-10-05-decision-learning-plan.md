# Session evidence, learned decisions and rebuildable generations

October8 current Chat mount: C14H/I/J and C03G/H qualify sealed canonical Chat
sources; C14K/L publish indexed examples and automatically activate only qualified
read-only rules; C15C joins the existing live memory/decision path; C14M supplies
immutable existing-rule context for example-only/revision learning. The actual
mounted second-segment test proves one definition advances to version2, not a
duplicate rule. Voice remains unknown/analysis-only as described below. Standalone
Decisions transport is now mounted; historical “not built” notices below are not
current status. Register r44 owns status; no full-release claim.

C14N adds the explicit post-analysis/pre-save reconciliation step: existing active
HNSW examples identify candidates; the same configured review model compares full
behavior/applicability and the proposal batch. Add phrasing to the same ID; retain
conditions/slots/capabilities/exclusions when adding nuance to a new version; make
a new ID only for distinct behavior; defer ambiguity. This is model classification,
not SQL/keyword classification. Existing scoped repositories validate and save.
The separate prompt preserves outcome assessments and citations exactly, treats all
session text as untrusted, and never promotes throwaway speculative work to success.
Analysis/reconciliation checkpoints and catalog epochs fence retries/publication.
See [C14N](../contracts/2026-10-08-LMD-C14N-semantic-reconciliation.md) and its
[bounded evidence](../reviews/2026-10-08-C14N-reconciliation-evidence.md).

Current reviewer schema is v3 under
[C14J](../contracts/2026-10-08-LMD-C14J-resolution-usefulness.md): adds required
evidence-linked request_resolution/usefulness without another model call. Earlier
v2 descriptions below are retained historical implementation evidence, not the
current output contract. C14I owns actual post-segment Chat dispatch; C14H owns its
canonical projection. Unknown source coverage still cannot teach/activate rules.

Current document set: [authority map](2026-10-07-live-memory-document-authority.md).
This plan owns its design concern only; original grounding controls requirements,
register controls build status, and historical reviews/manifests are not work orders.

2026-10-07 revalidation notice: [Decisions/evidence grounding amendment](2026-10-07-decisions-api-evidence-grounding.md)
is controlling for the resumed API and speculative-evidence scope. This plan's
affected mapping, evidence, learning, removal and provider assumptions require
Phase01 revision, then Phase02 review. Earlier API-unavailable/deferred wording
is historical and does not override the amendment. No build readiness added.

Revision: LMD-LEARNING-PLAN-r4. Phase02 corrected candidate; authority grounding r11
plus LMD-DA-G-2026-10-07-r2. API adapter planned separately, not built.

## Separation

Production Voice mount allocation: [C14G](../contracts/2026-10-07-LMD-C14G-voice-review-mount.md)
extends the existing Voice finalization boundary with an independent procedural
call through the configured memory model/runner. Current canonical Voice source
coverage is unknown, not complete: durable assessments are permitted; every
changing proposal/publication is rejected. Acknowledged transcript writes under
[C03E](../contracts/2026-10-07-LMD-C03E-capture-acknowledgment.md) do not prove tool,
context, feedback or original-model coverage. Failed writes block both reviewers.
This is not the qualified rule-learning/activation or Background goal scheduler
mount; those remain separate prerequisites, not success inferred from analysis.

Owner implementation clarification: reuse the existing memory review's configured
provider/model execution logic with a distinct procedural prompt/output contract.
Sequential independent calls initially are allowed by the owner's parallel-or-after
choice. [C14A](../contracts/2026-10-07-LMD-C14A-shared-reviewer.md) owns bounded
reuse/validation; no memory reviewer replacement, mandatory Decisions API learning
call or new agent identity. Durable publication remains separately allocated.

New `decision_learning/` owns procedural proposals, deduplication, immutable
versions, publication and generation rebuild. New `decision_routing/` owns
eligible rule retrieval/collapse and optional finite-selector interface.
Neither owns grants, canonical R1 memory learning, conversation turns or tools.
Canonical memory type decision remains recalled knowledge. Procedural examples
are retrieval evidence, not executable instructions or permission.

Conversation evidence references actual final input, bounded tool outcomes,
errors/corrections, memory IDs/versions and available model summaries.
Original reasoning summary, transcript summary and reviewer inference have
different provenance. Record unsupported/absent/interrupted/truncated evidence
truthfully. Voice-provider reasoning availability remains conditional.

Durable finalization uses a stable source fingerprint and independently
idempotent memory and procedural outputs. Inspect existing memory claim/write
recovery before assuming atomic publication. Accepted canonical memory must
survive procedural review failure. Define retry ownership, crash windows and
partial publication before building O6. No durable unsent draft learning.

## Lifecycle proposals and reserved decisions

Owner policy [BP-R02–03](2026-10-07-live-memory-build-policy-grounding.md)
supersedes the earlier all-inactive proposal: validated read-only rules may
activate automatically; write or unknown-effect rules remain inactive. Current
grants, confirmations and final-input validation remain mandatory. Until those
gates are implemented, conversation continues through the normal model.
Forgetting retains history but suppresses relearning from reviews and rebuilds;
retention is not authorization to replay a forgotten fact. Numeric confidence
thresholds and write-rule activation policy remain unspecified.

Later active rules require current scoped definitions/examples, required slots,
version/generation, ambiguity fallback and current capability/grant checks.
Collapse example hits by definition; do not merge invoice status with account
balance because they share vocabulary. Stable capability references resolve
through the existing catalog; an unavailable provider preserves the rule but
makes that route ineligible. Do not add example integrations.

Rebuild creates an inactive generation from retained authorized evidence,
validates it, then atomically switches the active pointer. Failed builds leave
the current generation intact. Rollback never replays external actions or
restores forgotten knowledge. Cache invalidation follows generation/memory/
permission changes. Exact schema/DDL belongs to a reviewed near-term contract.

## Outcomes

| Outcome | Entry / deliverable | Positive / negative proof | Recovery and exit |
|---|---|---|---|
| O6 | O4/O5 usable evidence; retention/retry decisions; durable capture and independently retryable review | Restart/duplicate ingestion keeps one result; procedural failure preserves memory; summaries don't outweigh failed tools | Disable procedural worker; preserve canonical learning. Exit durable attributed final evidence |
| O7 | O2/O6; lifecycle decisions; versioned inactive rules/examples and generation build | Similar paraphrases preserve definition; last-word/slot ambiguity defers; no stale/deleted source resurrection | Keep prior generation and fallback. Exit validated proposals, not implicit activation |
| O8 | O7; explicit activation/effects/capability contract | Current eligible known rule works; selector absent falls back; tool removal/revocation blocks | Deactivate generation/selector; existing tool authority remains. Exit authorized routing with failure evidence |

Each outcome owner is Christian for acceptance; maintainer implements only
reviewed contracts. Tests include wrong-but-well-formed rule, unknown effect,
concurrent rebuild, crash before/after activation and source deletion.
Stop on grant invention, unsupported schema promises or unresolved activation.
Decisions mapping is owned by [selector plan](2026-10-07-decisions-selector-plan.md).
Docs exist; SDK/account verification and reviewed contract remain prerequisites.
Its absence blocks neither chat nor indexed/live memory.

## Explicit relational storage proposal

These distant objects define storage responsibilities, not ready-to-run DDL.
Freeze actual types/indexes only after lifecycle/activation decisions. All under
vault_private with authenticated scope; no Decisions API schema is invented.

| Object | Required candidate fields and boundaries |
|---|---|
| `vault_decision_generations` | generation_id PK, user/workspace scope, source snapshot fingerprint, learner contract/provider/model, state building/validated/active/retired/failed, timestamps; one active scoped pointer changed atomically |
| `vault_decision_definitions` | definition_id PK, generation_id FK, stable capability_ref, semantic key, version, conditions_json, required_slots_json, action_description, status proposed/active/inactive, evidence counters/confidence metadata, source fingerprints, timestamps; definition describes behavior, never grants |
| `vault_decision_examples` | example_id PK, definition/version FK, final utterance/example text, source turn/evidence IDs, observed outcome/correction, provider/model/dimensions/preprocessing identity, embedding vector, fingerprint, timestamps; HNSW dimension-compatible index |
| `vault_decision_reviews` | review_id PK, scope/session/source fingerprint/learner contract unique, lease/retry/state, proposals/dispositions, errors/timestamps; independent from canonical memory ingestion |
| `vault_decision_activations` | scope PK, active generation FK, activation epoch, authorized actor/policy identity, previous generation/timestamps; no activation before approved policy |
| `vault_decision_execution_evidence` | Read-only scoped projection of canonical conversation events/selections/tool results; NOT another stored event ledger or copied payload table |

Rebuild source deletion must invalidate affected proposals/examples and trigger
scoped active-generation review. Retention/reintroduction follows the same owner
policy as session evidence, not an implicit everlasting corpus. Current grants
and confirmation stay in existing authorities; no new rule-permission table.
Query scope in SQL, collapse examples by valid definition, then current runtime
eligibility before finite selector/model fallback. Missing capability, uncertain
slot or conflicting examples defer. Unknown external tool effect cannot be retried
blindly; existing tool authority decides its recovery. Optional Decisions adapter
implements the finite-selector port after SDK/account verification and reviewed
contract, independently of storage and final-input validation.

## October7 authoritative evidence and review refinement

This section owns new procedural evidence semantics (DA-R04–09/12); capture
remains conversation_evidence-owned. Exact table/types frozen later in C03/C14.
Do not collapse these independent axes into one status:

| Axis | Candidate values / meaning |
|---|---|
| Phase | provisional preparation; finalized request; post-result review |
| Origin | original model proposal; Decisions answer; deterministic code; tool result; reviewer inference; user correction |
| Preparation disposition | current; superseded; abandoned; reused after final validation; rejected at final validation |
| Execution | not requested; proposed; denied; awaiting confirmation; invoking; completed; failed; canceled-before-execution; effect_unknown |
| Tool report | no result; returned non-error; returned error; truncated/incomplete |
| Request outcome | supported resolved; corrected; unresolved; unknown |
| Usefulness | supported necessary/helpful; supported unnecessary; harmful; unknown; with evidence and assessor identity |

Store scoped conversation/segment/turn/revision identities, event ID and canonical
sequence, causal parent/proposal/selection/call/result IDs, input/context source
fingerprints and available-at-decision evidence IDs, memory versions, candidate
definition mapping/generation, policy/capability epoch, producer identity and
timestamps. Timestamps alone do not prove causality. Missing links remain unknown.
Keep candidate-set identity, provider answer/probabilities and final reuse check;
no fabricated Decisions rationale. Original summary availability is per model call.
Summary truncation/interruption/redaction and output contract versions are explicit.
Evidence append/recovery and source deletion follow existing capture contracts.

Legacy warning: voice/tools.py complete() marks invocation succeeded even when
result.is_error is true. Its DB state is an execution/recovery fact, not a success
label for learning. Bounded transcript evidence slices at 16384 characters and may
be incomplete/non-parseable; prefer authorized original result when retained,
otherwise report unknown/truncated. TranscriptEntry projection omits metadata.
Do not silently change legacy enums; project into new evidence axes by adapter.

Provisional drafts remain transient. Retain only non-content operational IDs,
timings/dispositions under approved policy; no unsent text/examples in learning.
At finalization record only attributable current preparation reused/rejected for
the submitted turn; avoid preserving deleted draft text in prompt snapshots.
Abandoned predictions can measure waste without teaching user intent. Persisted
raw speculative diagnostic corpora require a separate retention decision.

### Reviewer procedure

1. Claim independent scoped review by immutable finalized source fingerprint and
   learner contract. Establish coverage, causal ordering and actual source quality.
2. Reconstruct decision points from evidence available then, separately from eventual
   outcomes. User/tool content is evidence, never reviewer-policy instructions.
3. Distinguish attempts, replayed cached outcomes, denied calls, recovery and unknown
   effects. Evaluate successful request resolution separately from tool transport.
   No implicit user acceptance from silence; inferred usefulness remains inferred.
4. Propose create/add-example/revise/no-change/insufficient-evidence with citations,
   conditions/exclusions, required slots, stable capabilities, counterexamples,
   supporting and contradictory outcomes. Missing reasoning need not reject linked
   final input/results, but never invent the original rationale.
5. Validate proposal against capability catalog and schema, deduplicate by semantic
   function and evidence identity; compare existing definitions. Similar wording
   alone cannot merge distinct operations. Same call/replay is not another success.
   Generated paraphrases are labeled synthetic, not observed successful examples.
6. Publish inactive proposals/examples idempotently. Acceptance/promotion remains
   reserved; correction invalidates dependent examples/versions without erasing
   source history. Memory and procedural publication failures stay independent.

### Historical read-only audit (no data inspected yet)

Allocated to C10/O-DA-A in the current register, separately from history UI and
later procedural publication. No private-history access authorized by allocation.

Use authorized scoped repository/export access; no unsafe test fixtures or direct
unscoped production dumps. Inventory retained sessions/transcripts, invocation and
result joins, provider/model/response IDs, final user/assistant input, ordering,
summaries, errors/corrections, duplicate/unknown effects, truncation and deletions.
Report coverage counts and redacted representative source references per channel.
Classify source as linked-outcome eligible; transcript-only tentative; or insufficient.
Timestamp-adjacent calls without proven turn mapping stay tentative. Report unknown
provider/capability version rather than assigning current catalog semantics to old
calls. A summary/completed flag does not prove complete session coverage.
No reviewer calls, data export/publication or active routing in the read-only audit.
Historical proposal generation requires reviewed data/retention/forget-replay policy.
Never replay old tools while reconstructing history.

Required counterexamples: old draft route differs from final; successful but unneeded
call; returned isError with succeeded state; later correction; interrupted write
effect unknown; cached replay; late summary; missing turn link; tool output prompt
injection; duplicate session review; forgotten source; absent provider reasoning.
Trace: DA-R04/05/06/07/09 → O-DA-B/C03/C14; DA-R08 → O-DA-A/C10;
DA-R12 → O-DA-D/evaluation. Removal preserves final evidence/canonical memory.

## Phase02 exact procedural storage contract model

This owns procedural storage; evidence storage is in complete-session plan.
SQL generation/installation is C14 work after C03 identities and source policy.
All IDs text (current local convention), timestamps timestamptz; positive versions
integer; source fingerprints lowercase SHA256 text with length64 constraint.
Authenticated scope=(user_id,workspace_id) is private to the owning user initially:
no cross-user learned-rule sharing implied. user/workspace deletion CASCADE owned
procedural rows; active membership required for all reads/writes. Future sharing
requires separate reviewed policy, not inference from shared canonical memory.

Relations use composite scope foreign keys throughout; ID uniqueness alone cannot
prevent cross-scope relationships. Scope FKs point to current local authorities;
UNIQUE(user_id,workspace_id,id) on each referenced parent. Existing session evidence
is NEVER child of a generation and never deleted when a generation is dropped.

| Object | Exact candidate columns / relational invariants |
|---|---|
| vault_decision_generations | generation_id text PK; scope; schema_version integer>0; compiler_version text; source_snapshot_fingerprint text; state text CHECK building/validated/active/retired/failed; created_at/updated_at; UNIQUE(scope,generation_id). Active state alone is not authority: active pointer is sole routing authority |
| vault_decision_definitions | definition_id text; generation_id text; version integer>0; scope; decision_key text; conditions_json jsonb object; required_slots_json jsonb array; capability_refs_json jsonb array; action_description text; exclusions_json jsonb array; status text CHECK proposed/active/inactive; created_at; PK(scope,generation_id,definition_id,version); UNIQUE(scope,generation_id,decision_key,version); composite generation FK CASCADE. Definition version content immutable; changes create version, not in-place edit |
| vault_decision_examples | example_id text PK; scope; generation_id/definition_id/definition_version matching composite FK CASCADE; example_text text; example_kind text CHECK observed/synthetic/counterexample; outcome_class text CHECK resolved/corrected/unresolved/unknown; source_set_fingerprint text; source_review_id text nullable; enabled boolean; provider/model text nullable; dimensions integer nullable; embedding vector nullable; embedding_fingerprint text nullable; created_at. Missing embedding remains explicit and not semantic-matchable. Observed evidence uniqueness by(scope,definition version,source fingerprint,example_kind); synthetic examples never raise observed success counters |
| vault_decision_reviews | review_id text PK; scope; conversation_id/segment_id text; source_snapshot_fingerprint text; learner_contract_version integer>0; provider/model text; state CHECK queued/running/retryable/failed/completed; lease_owner/lease_until nullable; attempts integer>=0; proposals_json jsonb array; source_coverage_json jsonb object; error_code nullable; timestamps. UNIQUE(scope,conversation,segment,snapshot,learner contract). Lease acquired atomically; no duplicate reviewer publication |
| vault_decision_activations | scope PK/membership CASCADE; nullable generation_id text composite FK SET NULL (generation_id); epoch bigint>=0, zero only before first activation; policy_version text; actor_user_id text; changed_at. C14E before-delete triggers invalidate dependent source/catalog and advance epoch, avoiding erasure-blocking RESTRICT. Locked compare-and-swap expected epoch; all retained/new rules requalified under same scope; pointer swap plus retirement/new active state one transaction. BP-R02 permits automatic validated read-only activation, not automatic write activation or a grant bypass |

Review-to-example source links use the shared source-reference contract: current
authorized evidence must exist when proposals/examples publish or route. Stored
source references remain evidence IDs/fingerprints, not copied unredacted content.
Source erasure invalidates dependent examples/proposals via registered cleanup and
epoch before caches can route. Definition/exemplar deletion never deletes sources.
Do not make canonical evidence FK CASCADE depend on derived review. History-policy
questions remain blockers for historical reconstruction, not schema guesswork.

Indexes: B-tree(scope,generation,status/decision_key) on definitions;
B-tree(scope,definition version,enabled) on examples; B-tree(scope,state,lease_until)
on reviews. JSONB GIN only for demonstrated containment query, not automatic index
on every JSON column. Examples HNSW expression index uses embedding::vector(1536)
vector_cosine_ops WHERE enabled AND provider='openai' AND
model='text-embedding-3-small' AND dimensions=1536 AND embedding IS NOT NULL.
Query matches expression/predicate, joins scoped active generation/definition;
filters scope in SQL BEFORE application handling. Underfill/widen/exact fallback
follows memory-search indexed policy; no Python scan as semantic implementation.

Finite vector validation: positive matching dimensions, vector_dims=dimensions,
real provider output, current example-content/preprocessing fingerprint; no fake
embeddings. Rebuild vector identity independently; a generation cannot be validated
while required semantic examples are incomplete. Small exact SQL query is valid;
representative ANN index-use proof required before claiming HNSW delivery.

Observation counts/confidence are derived from unique qualified evidence identities,
not incremented on each reviewer retry. Store calibrated routing policy separately
from retrieved example distance and provider confidence. Initial publication has
no activation pointer change. Failure after proposal commit before acknowledgment
retries identical identity; generation pointer unchanged on failed rebuild.

Migration order: approved shared evidence IDs -> generations/reviews -> immutable
definitions/examples -> indexes/verified embedding backfill -> inactive generation
validation -> separately authorized activation pointer. Additive resumable runner
owns schema metadata; no decision schema work added inline to memory/schema.py.
Concurrent HNSW build outside transaction with invalid-index detection. Test only
isolated allowlisted DB; backup/restore proof before production migration. Rollback
disables readers/workers first; owned derived generation cleanup is explicit scoped
operation after pointer retirement; no broad DROP schema or source-history deletion.
Retention, promotion and capacity conditions prevent production READY claims.

## October7 owner outcome clarification and built deltas

[Outcome grounding](2026-10-07-decision-outcome-grounding.md) adds separate
tool/context/result correctness, tool/context/result/overall user satisfaction,
and failure attribution. C14F reviewer v2 uses the existing scoped model runner,
explicit GOAL prompt, exact point-linked evidence and unknown handling. A non-error
tool return is insufficient; wrong context/result or negative satisfaction cannot
teach a successful rule. All assessments, including failures/no-change, persist in
the existing review checkpoint's additive assessments_json. No new model identity,
duplicate memory review or fabricated historical assessment. Old v1 checkpoints
are retained, not silently relabeled v2. Production source qualification remains.

C14E compiles each single-review building generation against the current catalog;
unchanged rules/examples preserve original source review references and vectors.
Example-only changes preserve behavior and old examples; behavioral revisions
advance the current version exactly once. Current source/suppression/quality and
capability gates are mandatory callbacks, not implemented production policies.
C15B reads active-pointer epoch and real indexed candidates, then rechecks source
and read-only capabilities. Neither component executes a tool. Final meaning,
slots, grants/confirmation and the actual producer/worker/Chat/Voice mount remain.
Status and evidence belong to the contract register, not this section.


### Completion continuation — owned read-only historical qualification surface

GET /conversations/decisions/qualification pages at most10 owned finalized Chat
segments/Voice sessions using an explicit after cursor. It reconstructs through the
existing canonical source gates, including original attachment verification, and
reports source/linkage/failure/feedback counts, actual captured provider/model
bindings, hashed representative source IDs and eligible/tentative/insufficient
classification. Voice sessions without a review bridge are included without
creating one. Unknown historical provider/capability versions remain unknown.
No provider calls, tool replay, source export, publication, queue writes or automatic
backfill occurs. Even linked-outcome-eligible input is not a successful procedure or
an activation grant. Authentication/current workspace authority applies to every
page. Isolated mounted verification proves pagination, no private text in output,
no model calls/DB writes and unauthenticated denial. Actual private historical data
has not been audited by these synthetic checks; reviewed scoped access is still
required by the read-only audit policy above.
