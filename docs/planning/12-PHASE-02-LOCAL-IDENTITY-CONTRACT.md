# Phase 2 Local Identity and Workspace Contract

Status: frozen candidate v1

## Scenario

An installed Vault has one to four local human users. Each user authenticates
with a local password/session and can access only active-member workspaces.
Workspace sharing is explicit and revocable.

## Entities

- `local_user`: fixed local identity, display name, normalized login name,
  password hash, status and lock state; exactly the bootstrap user carries the
  local `is_device_owner` authority needed to manage users;
- `local_workspace`: locally owned data scope;
- `local_workspace_membership`: user/workspace relation with `owner` or
  `member` type and active/revoked status;
- `local_session`: opaque bearer session represented at rest only by a token
  hash, with issued/expiry/revocation/active-workspace state;
- `setup_credential`: one-time installer bootstrap authority, deleted after
  owner creation.

## Hard constraints

- maximum four non-deleted human users, enforced transactionally;
- only the bootstrap device owner may create additional local users;
- no email requirement, tenant, cloud account, JWT, social login or service key;
- passwords use the exact Voice PBKDF2 format and constant-time comparison;
- session tokens are random opaque values, stored only as SHA-256 hashes;
- login failures lock at the donor threshold; successful login clears failures;
- refresh rotates the token and invalidates the previous value atomically;
- logout/revocation takes effect immediately;
- every workspace operation checks active membership in the same transaction or
  repository boundary as the operation;
- owner membership cannot be silently removed; ownership transfer is deferred
  unless a required flow proves it necessary;
- browser mutation/refresh uses strict cookies and CSRF proof;
- local onboarding preference is name plus experience; credential bootstrap is
  a separate installer/security concern.

## Schema and API boundary

Add only `vault_private.local_users`, `local_workspaces`,
`local_workspace_memberships`, `local_sessions`, and the minimum migration
metadata/indexes. Phase 2 API admits setup completion, login, refresh, logout,
current principal, workspace list/create, membership add/revoke and active
  workspace selection. No memory, agent, extension or remote route is admitted.

Workspace file keys reuse Voice normalization. Host filesystem access is only
for bounded staging/materialization, after membership authorization, and must
pass the Phase 2 traversal/symlink guard. Canonical document storage remains the
Voice PostgreSQL projection admitted in Phase 3.

## Required verification

- exactly four users succeed and the fifth is rejected under concurrency;
- correct/incorrect password, five-failure lock and non-disclosing errors;
- expired, revoked, replayed-old-refresh and CSRF-invalid sessions denied;
- every pairwise cross-user/private-workspace access denied;
- explicit shared membership succeeds, then fails immediately after revocation;
- SQL identifiers are parameterized and principal/workspace scope cannot be
  supplied solely by caller-controlled payload;
- donor password/token vectors and applicable session cases remain compatible;
- real PostgreSQL integration proof and unchanged donor fingerprints.

## Stop conditions

Stop if implementation requires a ReSono secret/endpoint, adds passwordless
management, weakens the four-user or membership boundary, or imports hosted
identity services wholesale.
