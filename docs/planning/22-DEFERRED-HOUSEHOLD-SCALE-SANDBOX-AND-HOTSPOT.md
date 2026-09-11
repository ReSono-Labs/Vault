# Deferred User Scale, Parental Controls and Hotspot Direction

Date: 2026-08-29  
Status: deferred direction only; no implementation authority

## Owner direction

Vault may later support more than four local users, parental/guardian controls,
and an optional secured hotspot when Vault is intentionally packaged for an
Orange Pi 5 or another edge device.

None changes the current build phase. Each requires later owner activation,
donor review where applicable, a threat model, contract and tests.

Concurrent multi-user operation and sandboxing are current requirements moved
to `23-CURRENT-MULTI-USER-SANDBOX-CONTRACT.md`; they are not deferred here.

## Current architecture that carries forward

The schema uses opaque user, workspace and session identifiers rather than
numbered user slots. The four-user ceiling is an application-policy constant,
not a database shape. Current repository/service boundaries scope sessions,
memory, Voice, Background runs, Mail, Calendar, Contacts/personal records,
extensions, credentials, tools and workspace paths by authenticated user and
active workspace.

PostgreSQL transactions and independent opaque sessions are compatible with
multiple active users. Existing tests prove user-creation concurrency,
pairwise private-workspace denial, cross-user memory denial and revocation.
They do not yet prove sustained simultaneous Voice, Background, Mail, Calendar
and extension workloads.

## More users

The current limit remains four. A scale phase must make the ceiling explicit
and configurable, add pagination, evaluate capacity, and test concurrent
workloads and resource exhaustion without weakening master-account protection
or cross-user denial.

## Parental controls

Parental controls are a future policy layer, not permission to inspect or merge
private memory by default. A later contract must decide guardian/member
relationships, age/consent treatment, allowed controls, audit visibility,
recovery, emergency override and managed-user visibility. Tool, connection,
schedule, content and spending/model limits are possible policy categories,
not accepted features.

The permanent master account is a suitable administrative root, but current
master controls are not completed parental controls.

## Edge-device hotspot

Hotspot support is deferred until an edge-device phase is explicitly opened.
It is not part of the current desktop/local release and does not reopen hardware
deployment now. A later hotspot must be optional, default-off, authenticated,
isolated from database/direct runtime ports, and expose only authenticated
Browser Voice management. OS networking, Wi-Fi hardware, firewalling,
credential rotation and recovery require target-specific research. Link and
Tailscale remain separate remote-connectivity options.

## Future gates

1. Explicit owner activation and anti-drift entry review.
2. Configurable user limit without replacing the identity model.
3. Parental-control privacy/authority threat model before UI or policy code.
4. Hardware hotspot research only after selecting an edge target.
5. Browser Voice visual lock for all future management UI.
