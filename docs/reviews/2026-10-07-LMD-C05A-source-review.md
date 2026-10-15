# C05A/C06A pinned-source and necessity review

Internal same-context source review; not comparative quality or owner acceptance.
Authority: original R02–05/R09/R18/R25/R28/R31 and LC-R01–04. Branch
feature/live-memory-decisions. Existing C01/C02/C03A/C17A remain canonical.

## Observed source, not assumed integration

Read-only donor acquisition: /tmp/vault-voicemem-pinned.gprFGO, exact commit
6cacb3c1e7fca2679f3bf95451f6b480efd9a783. Files materialized from that commit,
not clone HEAD. stream.py was read in full. Its VoiceStream._speculate, _kick,
_ready_memory, _confirm, _reset_turn and feed_partial are the external-text seam.
The scoped extraction starts from these methods, not a generic new controller
mislabelled VoiceMem. Turn/StreamState become canonical typed preparation state.

Absolute donor source:
/tmp/vault-voicemem-pinned.gprFGO/voicemem/stream.py.
SHA256 6f302b8131341d5cdbaf74d4d96f7ceb46a873fc5f3deb55cc58f1fc45528fc1;
Git blob 79a9aa566d18248ce3bf8ce3e0f71f659a3dddb3.
LICENSE SHA256 cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30.
Read root Apache-2.0 license. Recursive pinned tree contains no NOTICE file;
selected stream source has no separate copyright/license header. Preserve the
license verbatim in Vault and explicit upstream attribution/modified-file notice.
This review does not approve uninspected model weights or full-package dependencies.
Read-only status before/after inspection SHA256:
dbe6940219ca400dec69739c1aea8a79fe95b6eb27d0eb944fd702f71a3ee7f1.
No package installation, model download or donor execution.

Observed gaps: empty edits ignored; _ready_memory retains an old result while
new work runs; _confirm rebinds old result to changed final text; canceling the
task wrapping to_thread does not bound surviving workers. These require the
specific revision/final/worker adaptations below, not wholesale reuse.

Inspected alternatives: local_query_classifier.py uses E5 and lazy downloads;
brain.py search/Rank depend on foreign slot/entity graph/store and hit/activation
writes. They cannot be copied into a read-only canonical Vault query unchanged.
Their classifier/narrowing quality remains C05 evaluation, not this extraction.
tests/test_session_context.py tests committed-history buffering, NOT draft
retention/late-memory/final correctness. Do not report donor tests as Vault proof.

Existing Vault sources: app/vault_runtime/memory_search/contracts.py defines the
C01 scoped query port; memory/retrieval.py owns RetrievalMatch/ranking;
decision_routing/contracts.py owns scope/input/evidence/CandidateChoice types.
No live revision scheduler is present in app/frontend/tests; existing Voice
capture and final submission remain source authorities, not this module.

## Material gate

Question: full package, fresh controller rewrite, or external-text extraction?
Choose the last per LC-R03, keeping donor method seams and replacing only proved
unsafe behavior. New parallel factual/procedural orchestration is explicitly NEW
per LC-R02. Counterexample: import donor stores/audio, or claim generic code is
VoiceMem without extraction provenance. CONTINUE bounded unmounted component.

Question: does component testing authorize production enablement? No. The existing
plan's comparative retrieval/quality gate remains before adoption. This extraction
can establish revision and concurrency correctness without claiming quality,
provider access, epoch loaders, Chat/voice mount or full C05/C06 completion.
Counterexample: injected test validators treated as real membership/relevance
validation. CONDITIONAL for production; CONTINUE isolated component tests.
