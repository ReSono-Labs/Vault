# Master Account Controls Evidence

Date: 2026-08-29  
Status: complete

The existing first-account `is_device_owner` authority is now the permanent
master account and controls the lifecycle of the other three local accounts.

Implemented and proved:

- owner-only secondary password reset;
- reset unlocks the account and revokes every target session;
- owner-only secondary account removal;
- removal revokes sessions/memberships and archives owned workspaces;
- master self-target and identity-deletion denial;
- ordinary-user authorization denial;
- Browser Voice Account controls using retained donor visual classes; and
- master-selected one-use setup link, forced temporary-password change, or
  master-managed password for each secondary account;
- optional post-recovery onboarding creation and later Account management use
  the same owner-only endpoint and four-account limit;
- every secondary stores only `under_18` or `adult`, with no current policy
  effect and no birth date;
- restricted temporary-password sessions and one-use activation replay denial;
- no MFA, authenticator, email challenge or cloud recovery code; and
- no destructive memory/personal-data purge hidden behind account removal.

Verification:

- identity integration suite: `12 passed`;
- complete PostgreSQL suite: `196 passed in 110.05s`;
- frontend suite: `6 passed`; and
- production TypeScript/Vite build passed.

Superseding full regression after the account-mode and sandbox correction:
`203 passed` backend, `6 passed` frontend, production build passed.

Superseding regression after optional onboarding accounts and age
classification: `204 passed` backend, `7 passed` frontend, production build
passed.

Donor repositories were not modified. Multi-account behavior is NEW local Vault
work because the donor has no multi-account implementation. Password hashing,
opaque-session and Browser Voice presentation primitives remain traceable
adaptations rather than a false multi-account donor claim.
