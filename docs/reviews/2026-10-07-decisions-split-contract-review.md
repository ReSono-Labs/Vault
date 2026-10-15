# Build-readiness review — dependency splits

Review LMD-DA-CR02-r1. Same-model/context INTERNAL SELF-REVIEW, not external or owner
acceptance. Original request: continue preparing tight reviewed builds without
implementation. Grounding original r11+DA r2; prior Phase02 review source premises
retained. Input identities: split-contract-candidate.sha256; corrected output exact
hashes in decisions-build-ready.sha256. Baseline source HEAD unchanged.

## Findings and first correction/re-review

| ID | Severity / independent source | Requirement / scope | Classification | Disposition |
|---|---|---|---|---|
| S01 | Major: C03/C08 each depend on conversation identities absent in actual code | R12/R24/DA-R07; capture | Correction | C03A header/segment/final-turn owner first; C03B consumes verified IDs. No event/model/UI dependency in root |
| S02 | Major: live SDK/access/policy prerequisites attached to pure selector mapping | DA-R01/02/11 | Correction | C17A offline deterministic mapping/validator; C17B actual SDK separately. Offline Selected observation cannot authorize action |
| S03 | Major: local_identity.owner_remove_user tombstones user; user FK cascade insufficient for shared-workspace conversations | Existing erasure/R31/DA-R11 | Correction | Exact optional-table erasure-list entry and actual remove_user test; scope/cascade preserves other users |
| S04 | Major: auth can become invalid between SELECT predicate and turn append | Scoped authority/DA-R10 | Correction | New owned transactions lock current auth rows through commit, no legacy auth changes; concurrency negative test |
| S05 | Major: parser bool coercion and supplied candidate hash permit plausible wrong mapping | DA-R02/03 | Correction | Exact type/range checks and recomputed ordered canonical hash; candidate strings only; no tool dispatch |
| S06 | Verification: test Compose PG16 exists but container stopped; destructive fixture drops schema | Data safety / C03A | Verification | Existing harness startup within build; exact DB/loopback-port/test-volume gate BEFORE fixture, no production tests; skipped DB proof not success |
| S07 | Minor: fixed text bound could be misrepresented as final model/Chat capability | R24/34 | Correction |65536 UTF8 internal root fail-fast bound only, no truncation; later large-input contract explicitly revises |

Re-review: C03A scoped PK/FK and composite segment reference prevent cross-user joins;
login expiry does not delete retained conversation but blocks reads until current
auth. Same-key retry compares actual text before version condition, old-key retry
returns original and doesn't increment version. Header/segment create one transaction,
submitted text immutable. New root not imported into host; no inference/retention
policy or new agent activated. Specific optional deletion entry remains no-op with
no table, no broad cleanup redesign. Authority copied from actual neutral predicate,
not imported Voice identity. New schema introduced only through test/manual explicit
ensure_schema, not production deployment. Deadlock retry not hidden.

C17A matches documented single workflow choice and reserved fallback; transport
injected, no SDK/credential reads. is_current/cancel/deadline checked before and
after blocked evaluation; physical abort/quota still C06/C17B responsibility. Exact
mapping resolves definition/version, probability not instruction. Handwritten docs
fixtures and altered values reject self-generated expected results. Strict JSON
source limits already exist; no new JSON framework or weakened validator. Unused
low_confidence union does not select a threshold. No calibrated execution claim.

Contract completeness: outcome, authority/input versions, owner/dependency direction,
actual source conventions, exact allowlists, forbidden host duties, typed interfaces,
schema constraints/transactions, positive+negative/concurrency/deletion tests,
checks/stop/rollback/evidence/exit all present. Later capture/API/live inference
proof stays dependent, not waived or assigned to pretend implemented foundation.
New design beyond owner scope: none; splitting changes delivery order, not product.
No semantic two-cycle stop issue remains; corrections re-reviewed once.

## Decisions

- C01/r3 PASS/READY: unchanged legacy search seam; metadata rebinds latest reviewed
  plan/source.20 baseline focused tests pass0.22s. New boundary tests still build duty.
- C03A/r1 PASS/READY: build scoped unmounted identity persistence and specified
  isolated tests. Docker startup/actual DB proof occurs during build; failing setup
  stops slice. No prior migration proof needed for unmounted new tables in test DB;
  production migration still explicitly forbidden.
- C17A/r1 PASS/READY: build pure functional mapper/parser/no-op with fake transport;
  no endpoint/account/SDK prerequisite until C17B. No active routing or scope proof
  falsely inherited from this slice.
- C03B/C17B and other dependent feature contracts NOT READY until foundation outputs
  verified and their exact contracts re-reviewed. Activated routing/historical replay,
  release thresholds and paid experiments remain reserved gates.

Next route Phase03 C01/r3 only on implementation authorization, then verify/checkpoint
before dependent contract review. C03A/C17A also dependency-ready standalone roots
but not permission to implement all phases in one turn. User asked ready-to-build,
no runtime changes this turn. Existing planning worktree preserved.

Evidence: candidate freeze, actual source inspection incl deletion/helper/strict JSON,
test DB status read-only (stopped), original package hash verification,20 existing
unit tests, output hashes/link/whitespace checks. No new code, schema install, DB
read of user content, real endpoint/SDK upgrade, browser/audio or independent review.
Assurance: ready to START staged build, not whole-feature execution/release readiness.
