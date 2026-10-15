# C03B plan and contract review

Review ID LMD-C03B-CR-r1. Phase02; internal same-model/context self-review only.
No independent review, owner acceptance or implementation verification asserted.
Original request: modular removable live memory/decisions, real finalized session
evidence and reasoning summaries, review without learning abandoned predictions.
Grounding r11 plus DA r2; partial drafts allowed provisionally, not durable learning;
GPT-Live excluded. Freeze: C03B-review-candidate.sha256 records DRAFT candidate;
C03B-review-source.sha256 binds inspected source. Final READY manifest records
post-review lifecycle changes; historical DRAFT hash intentionally differs.

## Independent reconstruction and findings

Submission currently owns its connection, auth and private turn history. Voice
events and transcript projection use separate commits. Existing tool observer is
not universal failure/denial coverage. Therefore full C03 parent cannot simply be
mounted or treated as complete. Verified conversation IDs remove stale C08 cycle;
offline C17A neither executes tools nor proves final selection capture.

| ID | Severity | Exact evidence | Violated source | Dependents | Classification | Resolution |
|---|---|---|---|---|---|---|
| F1 | Major | analysis r4 assigns identity DDL to C08; actual C03A schema exists | Owner exact wiring; DA-R04 | C03/C08 | Correction | analysis r5 uses actual C03A; parent hash rechecked |
| F2 | Major | conversation submit owns transaction; Voice capture calls record_provider_event then append_transcript | Lossless provenance/recovery; DA-R04/05 | Evidence/review | Correction | Bounded C03B submits and appends in one transaction; Voice remains follow-on |
| F3 | Major | Separate valid conversation/segment/turn references could mismatch without five-column parent key | Private scoped source authority | Evidence/erasure | Correction | Exact composite key+FK and existing-schema upgrade required |
| F4 | Major | Contiguous user-final events do not prove assistant/tool/summary coverage | DA-R05/07/11 | Reviewer/learning | Correction | source_coverage always not_established; no seals/jobs/review trigger |
| F5 | Major | Entire full-capture parent needs trusted producers, model/tool outcomes and closure not present in verified roots | Small reviewed slice/no invented capture | C03/runtime | Correction | C03B bounded user-final foundation; C03C explicit remaining allocation, not waived |
| F6 | Major | Legacy duplicate provider event accepted=False cannot guarantee projection repair | Durable idempotency | Future Voice capture | Verification | Not corrected by C03B; blocks later Voice/full-capture claim, recorded C03C prerequisite |

## Material decision gates

Each gate records authority independent of the new contract. These are bounded
implementation corrections under existing owner request, not new activation policy.

| Question | Independent meaning/authority | Alternatives | Selected function | Counterexample | Dependents / status |
|---|---|---|---|---|---|
| Where is evidence committed? | Owner reliable session capture; actual C03A uses one connection | after-commit callback; generic outbox; same-transaction canonical append | Same transaction for local user submission, no second DSN | Crash after turn commit loses event | C03B CONTINUE; rollback tests mandatory |
| What source is authoritative? | DA-R04 separates predictions/execution; actual immutable turn rows | caller payload; copied transcript; actual scoped turn | derive metadata from persisted turn, checksum verified | client fabricates successful action | C03B CONTINUE; no outcome producer interface |
| Does this establish complete capture? | Owner requires summaries/tools; actual adapters are missing | infer complete from rows; manufacture summary; explicit incomplete coverage | no completeness/learning claim, C03C retains requirement | 100 user events but no tool failure evidence | Review/learner STOP until C03C |
| Is this another ledger? | Owner module removability; planned canonical conversation events | Voice-only private store; second decision log; shared canonical ledger | one conversation_evidence table, expand later by reviewed migration | reviewer merges incompatible duplicate transcripts | C03B CONTINUE; no alternate owner |
| How are deletion and scope enforced? | Existing C03A private conversation account erasure; current auth SQL | UI-only filter; ID-only FK; scoped composite FK | same current local authority, cascade actual turn | shared workspace member reads another private history | C03B CONTINUE; real DB denial/erasure tests |
| Are snapshots bounded and truthful? | Owner no hidden omissions; finite resources | first100 treated complete; unbounded fetch; paginated frozen watermark | limit+1 paging and interval gaps, coverage unknown | late append alters review input or hidden tail | C03B CONTINUE; pagination/gap tests |

## Contract attack and re-review

DRAFT r1 frozen before this review. Checked original groundings against each
allowed path/interface/DDL, retry and crash case, denial, erasure, concurrency,
rollback and follow-on requirement. No new runtime, schema application or data
review executed. The absence of assistant/tool/summary adapters is explicitly
outside this next outcome, not waived for complete-session readiness.

One correction cycle applies F1–F5 to governing plans and narrow contract; F6 is
an explicit later blocker. Re-review finds no unresolved blocker to the bounded
atomic submitted-turn outcome. Public C03A methods must retain parity, including
old-key retry after later history. Additive constraint must work on existing C03A
tables, not merely fresh tests. Provider/tool effects never replay for repair.
All three existing implementation manifests checked successfully, source unchanged.

Decision PASS for bounded plan and C03B/r1 contract only. Mark exact revision READY
after this recorded review; identity bound in C03B-build-ready.sha256. Permitted
next action: Phase03 C03B/r1 only, stop after its verification/checkpoint.
Full C03/C03C, chat UI/model, live draft preparation, Decisions transport and
procedural learning remain unready. Unperformed checks: new code/DB tests,
production migration, real summaries, historical replay, independent review.
No claims of test passing are inferred from this document.
