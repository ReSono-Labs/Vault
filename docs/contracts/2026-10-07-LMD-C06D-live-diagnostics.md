# C06D/r1 — live Decisions backend operational logging

Owner explicitly requests live backend logging for analysis and review once wired.
Grounded scope is non-content operational diagnostics, not retained draft training
corpus. Reuse actual ParallelPreparation/VoiceMemStream/DecisionSelector stages,
Python logging already used by local_api/server.py. NEW decision_routing/diagnostics.py;
narrow event-only hooks in existing three lifecycle files. No another scheduler,
source ledger, durable raw draft, permission change or learning-success counter.

JSON stderr records use schema version, wall timestamp, event/reason enums,
pseudonymous hashed scope/conversation/segment/utterance/turn IDs, revision/event
sequence, per-preparation attempt ID, counts and monotonic elapsed milliseconds.
Never text, fingerprints of draft text, memory content, arguments, provider
payload/exception text, credentials, probabilities masquerading as permissions.
IDs are hashed before logging; no raw local session token. Explicit bounded fields;
logger failure must not change recall/selection/cancellation/publication outcomes.
Default local logger emits INFO JSON to stderr when live component is created;
does not reconfigure root logging or create files/cloud telemetry. Package logs
remain operator-owned. Injectable diagnostic sink supports tests/removal.

Actual events: revision accepted/skipped, preparation start/reuse decision,
recall/decision completion and memory-dependent reconsideration, ready/stale/error,
stream invalidation, exact final reuse/fresh final/timeout/cancel; selector begin
and selected/fallback reason, never selected route execution proof. All exact
events must be verified via real existing controller and selector tests, including
stale work and throwing logger. This is diagnostic event emission, not a claim
that currently unmounted production live paths already run.

Internal prebuild review CONTINUE: logging after validated stage transition only;
allowlist fields/reasons and protected emission; no snapshot repr/raw errors.
Postbuild review must trace actual emitted events, privacy sentinel tests, final
reuse/stale/cancel/fallback behavior and document remaining analysis gaps.
