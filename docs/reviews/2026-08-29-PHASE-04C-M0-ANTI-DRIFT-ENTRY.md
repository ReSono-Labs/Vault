# Phase 4C M0 Anti-Drift Entry Review

Date: 2026-08-29  
Review type: internal same-context anti-drift review  
Candidate: contract 20 plus Phase 4C donor cut-point inventory  
Result: `CONTINUE` for M1–M3 donor-supported work; Background automatic
canonical-memory writeback remains `BLOCKED/REOPEN`

## Reviewed authority

- `GROUNDING.md`
- `INDEX.MD`
- `SKILLS.MD`
- `docs/protocols/ANTI-DRIFT-PROTOCOL.md`
- `docs/planning/PROJECT-BORROWING-MATRIX.md`
- `docs/planning/FEATURE-DONOR-MAP.md`
- Phase 3 and Phase 4 research, contracts, evidence, and exit reviews
- `docs/planning/20-MANDATORY-R1-MEMORY-LEARNING-INTEGRATION-CONTRACT.md`
- `docs/research/PHASE-04C-R1-MEMORY-LEARNING-DONOR-CUTPOINTS.md`

## Findings and corrections

1. The first correction draft duplicated document number 18. It was renamed to
   the uniquely numbered controlling contract 20 and stale references removed.
2. Phase 3/4 evidence proved component behavior but not production composition.
   Progress now limits those claims and reopens Phase 4C.
3. Voice scoped memory was constructed but not placed in actual Realtime
   instructions. An early bounded correction exists; M2 must prove it fully.
4. Production had no composed R1 reviewer/finalize chain or authenticated
   transcript-finalize surface. M1/M2 explicitly own these gaps.
5. The initial M3 draft assumed Background results should automatically enter
   canonical memory. R1 proves `memoryReferences`, memory tools, and durable
   phase evidence, but no automatic writeback. The invented behavior was
   removed and marked blocked.
6. Voice donor finalization calls Platform Learning and Agent Hub. Those are
   excluded. The accepted cut point retains Voice transcript/close behavior and
   joins it to the R1 reviewer/pipeline without those callbacks.

## Material decision gate

- Question: may implementation resume, and at what boundary?
- Authority: owner requires updated R1 memory/learning, donor code reuse, two
  system agents, no invented features, and anti-drift.
- Alternatives: continue from incomplete prose; invent a new unified learning
  flow; port exact donor-supported slices; stop all memory work.
- Selection: port exact Voice capture/close plus complete R1 reviewer,
  pipeline, context, tools, and Background evidence behavior into Vault scope.
- Counterexample: a change adds another identity, imports Platform Learning or
  Agent Hub, downgrades R1 taxonomy, leaks scope, or creates Background
  writeback absent donor evidence.
- Dependents: production composition, local API, Browser Voice close path,
  Background run records, Phase 4C evidence, release readiness.
- Result: `CONTINUE` for M1, M2, and donor-supported M3. `BLOCKED/REOPEN` only
  for Background automatic canonical-memory writeback.

## Entry conditions

- Exact absolute donors, functions, tests, dependencies, commits, and file
  hashes are recorded.
- Donors were inspected read-only.
- R1 is functional authority for memory/learning; Voice remains storage and
  local authorization authority.
- Reviewer remains capability-only; agent inventory remains exactly two.
- Positive, negative, isolation, failure, replay, recovery, and exclusion tests
  are specified per slice.
- Excluded features remain excluded.

## Readiness statement

M1 may begin with the bounded R1 reviewer capability port. Each slice must
reread Grounding and Index, update evidence, and fail honestly. This internal
review does not prove implementation or public-release readiness. Phase 6
visual evidence and Phase 7 licensing remain separately blocked.
