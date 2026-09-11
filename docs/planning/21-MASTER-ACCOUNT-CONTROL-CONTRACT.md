# Master Account Control Contract

Status: accepted correction contract  
Authority: owner four-user decision and existing Phase 2 local identity model

## Outcome

The first onboarded account is the permanent master account (`is_device_owner`).
It controls the lifecycle of the other three local accounts. This completes the
existing four-user feature; it does not add roles, organizations, cloud
administration or another account hierarchy.

## Required controls

- Master lists and creates secondary accounts, up to four active accounts.
- The master may create secondary accounts during the optional post-bootstrap
  onboarding step or later from Account management.
- Master resets a secondary account password and unlocks it.
- Reset revokes every existing session for that secondary account.
- Master removes a secondary account from local access.
- Removal immediately revokes all sessions and workspace memberships and
  archives workspaces owned by the removed account.
- The master account cannot be reset through secondary-account controls or
  deleted. It uses the existing verified-current-password flow.
- Secondary accounts cannot invoke any master account operation.

## Deletion meaning

Account removal is a security-safe soft deletion of identity authority. It does
not silently erase memory, Mail, Calendar or audit data. Destructive data purge
is a separate privacy workflow and is not invented by this correction.

## API and UI

- Existing `/local-users` owner-only list/create remains authoritative.
- Reset and removal are scoped by opaque user ID and require master auth plus CSRF.
- Account UI shows controls only beside secondary accounts.
- Reset requires a temporary password of the existing minimum length.
- Removal requires explicit confirmation and reports its immediate effect.
- UI retains Browser Voice account-management classes and visual language.

## Master-selected secondary-account access mode

The master chooses exactly one mode when creating or resetting a secondary
account:

1. `setup_link` — Vault generates a one-time, expiring setup credential. The
   secondary user opens the local setup link and chooses their password before
   receiving a session. The plaintext credential is shown once and only its
   hash is stored.
2. `temporary_password` — the master supplies a temporary password. Login is
   allowed only into a restricted session that must change the password before
   any workspace, memory, Voice, Background, connection or extension route can
   be used.
3. `master_managed` — the master supplies and controls the password. The user
   may sign in normally but cannot change it. The master may replace it, which
   revokes all existing sessions.

The mode is visible to the master and affected user. `setup_link` and
`temporary_password` become `user_managed` after successful password choice.
There is no email delivery, MFA, security-question, helpdesk or cloud recovery.

Setup credentials expire after seven days, are one-use, are scoped to one
secondary account, and do not create a session until the user supplies a valid
new password. Master reset invalidates every prior setup credential and session.

Restricted temporary-password sessions may call only `/me`, password change
and logout. Server-side routing enforces this; hiding UI is not sufficient.

## Future age classification

Every secondary account requires one master-supplied classification:
`under_18` or `adult`. This is NEW local Vault metadata and is visible to the
master. It does not currently change permissions or agent behavior. Birth date,
calculated age, parental controls and age verification remain out of scope.

## Acceptance

1. Master reset changes authentication, unlocks the target and revokes all old sessions.
2. Master removal prevents login and revokes sessions/memberships.
3. Master cannot target itself or the permanent master identity.
4. Secondary users receive authorization denial.
5. Unknown/deleted targets deny without leaking credentials.
6. Four-user limit counts only non-deleted users.
7. PostgreSQL integration, HTTP, frontend and full regression tests pass.
8. One-time setup credential replay/expiry/wrong-user attempts fail.
9. Temporary-password sessions cannot reach any protected product route before change.
10. Master-managed users cannot change their own password.
11. Optional onboarding account creation and later Account management use the
    same API, four-user limit, access modes and required age classification.
