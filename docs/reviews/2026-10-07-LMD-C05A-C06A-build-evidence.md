# C05A/C06A/r2 — bounded component build evidence

2026-10-07; same-context internal implementation review, not owner acceptance,
comparative quality or production adoption. On feature/live-memory-decisions,
uncommitted; owner work retained. Contract/r2 reviewed before runtime build;
r1 source manifest preserved and r2 separately frozen. No donor modifications.

## Implemented exact scope

live_memory/voicemem_stream.py extracts VoiceStream external-text method seams
from pinned stream.py: _speculate -> canonical preparation port; _kick -> one
pump/latest pending and debounce/max-wait; _ready_memory -> current validated
result only; _confirm -> immutable exact/changed-final validation and deadline;
_reset_turn -> transient clearing; feed_partial -> every edit including empty.
New event token rejects identical-snapshot Off/resume races; increasing revision
rejects ABA/out-of-order/conflicts and scope changes. Donor cancellation/old-ready/
changed-final shortcuts explicitly removed for observed safety defects.

NEW contracts.py reuses C17A scope/input/evidence/candidate types and canonical
RetrievalMatch. NEW preparation.py performs shared-snapshot memory/decision work
in parallel, honors explicitly validated retention, then at most one dependent
decision reconsideration when recalled memory changes. No selector API or learned
definitions fabricated. Required injected guard/reuse ports have no permissive
production implementations. Off/IME/deletion invalidate ready state and pending
work; final timeout/cancel rejects late results without pretending threads stopped.

WorkerBudget holds explicit global/per-user permits until actual to_thread work
finishes, even when a waiter is canceled. Failed parallel branches drain siblings;
stream invalidate/wait_closed supports safe shutdown. Guard checked before/after
validation; final rebound cannot publish if invalidation races a slow guard.

Apache license copied byte-identically, SHA256
cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30;
modified-file attribution carries exact upstream commit. Only pyproject package-data
entry added; dependencies/lock unchanged. Wheel inclusion declaration tested,
actual wheel build NOT performed: setuptools/wheel/build absent from current venv;
no package download/install. Distribution validation remains before release.

## Actual final verification

- New module tests: 41 passed; three repeated runs performed after final correction.
- Focused command: .venv/bin/python -m pytest -q
  tests/unit/test_live_memory_component.py tests/unit/test_memory_search_boundary.py
  tests/unit/test_memory_search_boundary_callers.py tests/unit/test_indexed_memory_search.py
  tests/unit/test_conversation_identity.py tests/unit/test_decisions_selector_boundary.py
  tests/unit/test_voice_capture_transaction.py — 239 passed, 1.89s.
- Final .venv/bin/python -m pytest -q tests/unit — 528 passed, 4 failures, 14.74s.
  Same prior Mail audience, DocumentsPanel prohibited marker, MCP migration
  workspace-source assessment and workspace_files prohibited marker failures.
  Not a full green suite. Earlier run additionally exposed our overly specific
  timing assertion; corrected to scheduler opportunity rather than guaranteed
  thread-start/retrieval latency, then final full run above passed all new tests.
- Genuine thread/barrier tests prove parallel retrieval, actual permit lifetime,
  failed-branch drain, cancellation and stale publication rejection. Synthetic
  callback relevance decisions are NOT proof of a real relevance model/loader.
- C01/C02/C03A/C03R/C17A implementation manifest checks all OK, unchanged.
  git diff --check clean. Test harness remained stopped; no DB tests/migration here.
- Donor before/after status hash unchanged:
  dbe6940219ca400dec69739c1aea8a79fe95b6eb27d0eb944fd702f71a3ee7f1;
  materialized stream Git blob matches pinned 79a9aa566d18248ce3bf8ce3e0f71f659a3dddb3.

## Deliberately not claimed

No Chat/voice/API/composition mount, canonical epoch/current relevance implementation,
production preferences/defaults, real procedural store/Decisions transport, model
calls, paid experiments, memory-quality or useful-answer latency evidence. Full
C05/C06 remain not READY. Off here is a caller input, not the C07 persisted setting.
No raw drafts/tools/learning/source history persisted; no second memory authority.
Next source-backed contract work: actual C06 guard/context loaders and C13 memory
epoch/maintenance prerequisites, retaining C05 comparative adoption gate.
Removal requires no schema/data rollback; delete isolated component/tests/license
and its package-data entry. Production composition is unchanged.
