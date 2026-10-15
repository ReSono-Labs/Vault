# LMD-C03 — attributed final evidence capture

AUDIT HOLD: parent allocation, not a build instruction. C03A identity exists;
stale C08 dependency below is historical. Existing transcript/provider/tool
ledgers must be reused where sufficient; new ledger necessity unproven. Current
feature audit provides the source inventory; no owner branch lookup required.
Body below is a superseded design envelope, NOT approved DDL/paths/interfaces.
Current register and source-first analysis/module plans govern delta-only review.

Revision r1; lifecycle DRAFT/DEPENDENCY-BLOCKED, not READY. Governing original r11,
amendment r2, corrected October7 candidate and source manifests. Outcome DA-R04–08/
R12/R22/R32: distinguish captured finalized intent, original proposal, execution,
result, replay and missing evidence without changing tool authority. No historical
learning, raw drafts, active routing, provider model call, UI or grant change.

Owning module conversation_evidence; existing Voice/provider/transcript/tool ledgers
preserved. Exact new files: conversation_evidence/{__init__,contracts,repository,
voice_adapter,schema}.py; tests/unit/test_conversation_evidence.py and
tests/integration/test_conversation_evidence_postgres.py. No other new runtime
directories. New evidence tables only after reviewed identity/migration sub-contract.
Allowed existing paths/seams in module plan C03 paragraph; no broad file rewrites.
Use existing donor repository adapters, no copied canonical reconciliation.

Interfaces: append_final_event(principal:LocalPrincipal, conversation_id:str,
producer_key:str, producer_event_id:str, event:FinalEventInput)->AppendAck;
snapshot(principal, conversation_id, through_sequence:int)->EvidenceSnapshot;
seal(principal, conversation_id, producer_watermarks)->SealResult.
Input types match analysis-plan canonical evidence model; server authority establishes
IDs/scope; client cannot submit authoritative tool/model outcomes. Trusted producer
adapters distinguish browser transcript observations from server-verified tool results.
Append transaction resolves current membership/session, locks owned conversation,
compares duplicate canonical payload, allocates sequence and records event. Ack only
after commit; changed duplicate -> conflict; no duplicate execution implied by retry.

Voice adapter must map existing voice session and source provider identity to shared
evidence without requiring new Chat session. Capture provider ledger + transcript
through one connection-aware transaction or outbox reviewed before build. Equal
duplicate can repair missing projection; altered duplicate cannot overwrite source.
Don't reset historical source indexes; reversible mapping for reviewer citations.
Tool adapter observes denial, invocation claim, handler exception, complete(result),
effect_unknown and cached replay. Actual ledger remains execution authority. Result
is_error has separate field even when ledger succeeded. No rerun to repair capture.
Original reasoning captured per model call; unsupported/no summary truthful.

Prerequisites BLOCKING: C08 conversation/segment/turn identity for Chat evidence;
reviewed Voice source identity alternative may permit a smaller Voice-first contract;
transaction-aware repository API and migration runner/erasure/stop integration;
isolated Postgres version and safe DSN/restore fixture. No dependencies waived.
Contract must be split/re-reviewed before implementation if Voice-first selected.
Payload byte/node limits and oversized references must freeze in that reviewed
sub-contract; silent truncation rejected. Policy defaults not invented here.

Positive/negative checks: atomic commit/replay after crash between provider/transcript;
changed duplicate409; no cross-user/workspace causal parent; late summary stays same
call; denial/error/unknown effects/replay differentiated; raw draft rejected; missing
range cannot seal complete; teardown marks capture gap; delete prevents stale worker
publication; existing Voice authorization and current memory finalization compatible.
Test DB name allowlist resono_vault_test; isolated volume only; no production fixtures.
Save migration forward/rollback/restore and source-linked runtime trace evidence in
docs/reviews/2026-10-07-LMD-C03-build-evidence.md during later build. No such evidence
exists now. Stop on source loss/authority change, roll back injection not history;
completion needs actual append/capture integration and reviewed diff, not dataclasses.

Review disposition: contract is detailed enough to identify exact blockers, not
permission to scaffold. C03 must not be marked READY before identity/persistence
contract and migration recovery proof are available. Acceptance owner Christian;
future implementer maintains bounded workers, no date/spend commitment.
