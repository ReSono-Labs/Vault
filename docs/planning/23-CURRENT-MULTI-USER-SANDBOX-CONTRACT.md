# Current Multi-User Sandbox Contract

Status: accepted correction contract; implementation in progress  
Authority: owner decision and Voice sandbox donor inventory

## Required outcome

All four current users can maintain independent authenticated sessions and use
their own workspace, memory, Voice and Background capabilities at the same
time. Executable agent/capability work runs through the adapted Voice sandbox,
not directly against host secrets, database files or another user's area.

## Sandbox identity

Every run is bound to `user_id`, `workspace_id`, local session ID, run ID and
one fixed agent kind (`voice` or `background`). This does not introduce Agent
Packages or another agent identity.

## Enforcement

- Per-run private root and temporary filesystem.
- Only explicit read-only runtime artifacts and scoped workspace context mount.
- Clean environment; no inherited credentials.
- No database, Docker socket, host home or platform source mount.
- Network namespace default-deny; provider/tool access only through reviewed
  broker boundaries.
- CPU, address-space, file-size, process, open-file and wall-clock limits.
- Optional cgroup v2 hard limits where the platform provides delegation.
- Private stdout/stderr and support-safe metadata only.
- Fail closed when the configured sandbox probe or policy fails.

## Concurrent acceptance

Tests must run four authenticated users concurrently and prove independent
sessions, workspace writes, private memory ingestion/retrieval, Voice session
records and Background runs; cross-user object probing must fail during and
after load. One user's timeout, cancellation, crash or resource exhaustion must
not invalidate another user's session or data.

Linux uses the donor Bubblewrap boundary first. Windows and macOS require
equivalent later backends and cannot claim sandbox parity from logical database
scope alone.

## Exclusions

No additional agent, Agent Package, delegation, Foundry, hosted inference
gateway, excluded signal bundle, parental control, raised user limit or hotspot.
