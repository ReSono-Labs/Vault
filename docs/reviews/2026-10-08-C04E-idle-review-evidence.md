# C04E — idle Chat review and independent progress

Actual mounted path: submit/terminal completion/text-free editing heartbeat →
scoped persisted activity → existing recovery dispatcher (30-second poll) →
current principal resolution → locked activity/history recheck → existing segment
seal/queue → SAME bounded review worker and factual/procedural models → separate
durable consumer progress and existing output/publication checkpoints.

Default idle interval 120 seconds; effective dispatch normally 120–150 seconds
after the last delivered activity update. Frontend edits are throttled to one
text-free heartbeat per 15 seconds, independent of Live Memory. Heartbeats do not
persist drafts or create learning evidence. No new polling loop or model identity.
New traffic/running responses stop idle sealing. Chat conversation/history version
is unchanged; only the completed review segment rolls forward.

Markers: exact first/last turn ordinals; separate memory/decision pending,
completed, failed, disabled or not_requested; factual source fingerprint and
source-by-source candidate dispositions or reviewed_no_memory_proposal; original
procedural source/observation IDs with existing assessments/proposals. Successful
consumer skipped on retry. Segment result references expose saved count, review/
generation identity and publication versus activation status. No_change is not
an activated rule. GET review-status returns the latest 50 owned segments.
Older completed records without newly added metadata remain unknown, not backfilled.

Focused actual isolated-Postgres tests cover recent activity, running-turn exclusion,
heartbeat versus stale idle discovery, CSRF denial, idle checkpoint, same Chat
continuation, factual success/procedural failure and the reverse, retry without
repeating the successful consumer, empty factual output with completed coverage,
real canonical saved memory and original procedural source markers. Existing
restart/locking/exhaustion/authority test remains included. Seven frontend hook
checks pass, including text-free throttled edit activity; TypeScript no-emit passes.
18 focused publication/source unit checks pass. Providers synthetic; no paid or
installed-database calls, tool replay, deploy or external donor changes.

Limits: this is idle scheduling and coverage, not full large-history compaction,
windowed model analysis or full-session semantic-quality acceptance. Existing
oversize/incomplete-source guards still fail honestly; failures retain retry
status rather than advancing a successful consumer boundary. Revoked authority
cannot be silently replaced; automatic historical backfill remains disabled.
