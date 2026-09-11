# Phase 2 Local Identity and Workspaces Evidence

Date: 2026-08-29  
Result: PASS

## Proven outcome

The standalone Vault now owns local users, passwords, opaque sessions,
workspaces, memberships and device-owner authority inside Voice Vault's
PostgreSQL `vault_private` boundary. It uses no ReSono account, tenant, hosted
JWT, social login, service API key or cloud endpoint.

## Donor provenance

Exact Voice sources and hashes are frozen in
`docs/research/PHASE-02-IDENTITY-WORKSPACE-DONOR-INVENTORY.md` and
`docs/planning/13-PHASE-02-WORKSPACE-PATH-BOUNDARY.md`. Preserved behavior:

- PBKDF2-SHA256 with 600,000 iterations and 16-byte salts;
- constant-time password comparison;
- SHA-256 at-rest opaque token representation;
- 30-day session semantics, refresh rotation and revocation;
- five-failure lock threshold;
- strict HttpOnly refresh cookie plus double-submit CSRF pattern;
- workspace/member scope and Voice relative file-key normalization.

Grounded adaptations are the local `vault_private` records, transactional
four-user limit, installer setup credential, device-owner flag, and OS symlink
guard. These replace hosted authority without replacing the Voice datastore.

## Result files

| File | SHA-256 |
|---|---|
| `app/vault_runtime/local_identity/models.py` | `2841cf3ec02f10b8e5639f10d0b1501726102d3e1bf0641fce489ee8e4dde512` |
| `app/vault_runtime/local_identity/schema.py` | `911fc7d4e2123cab73f9510dc997b4c2cbf36966aad06d664c00d9bfe44b55c6` |
| `app/vault_runtime/local_identity/repository.py` | `0312e2b62de02056d7deecd6348c6543510af2488878506bed017e7a43063003` |
| `app/vault_runtime/local_identity/service.py` | `e8851a820d8d777d2442181ffa6c5443018fb28564d5b6ed6133eb849cc99beb` |
| `app/vault_runtime/workspace_paths.py` | `5ba5f0e07d1568c410e80d91608f9e4ca0c1771b6c7ca597f677ef3127cfa52a` |
| `app/vault_runtime/local_api/app.py` | `1f6c94c38ff4acdfeea347d7daacb3cc92eff8f6976543a940efd4f794e0f5d5` |

## Verification

A disposable `postgres:16` instance on an ephemeral loopback port ran the full
suite: `48 passed in 19.07s`. The container was removed afterward.

Evidence covers:

- atomic one-time bootstrap and setup-credential consumption;
- only bootstrap user has device-owner/user-management authority;
- exactly four concurrent local users; one of two racers for the fourth slot
  succeeds and the other receives the limit error;
- donor-compatible password and token vectors;
- correct login, generic incorrect/unknown errors and five-failure lock;
- hashed-only password/session/CSRF database representation;
- expired, logged-out, rotated/replayed and bad-CSRF denial;
- all twelve ordered cross-user workspace attempts among four users denied;
- explicit sharing succeeds and revocation immediately invalidates a session
  active in the revoked workspace;
- workspace owner membership cannot be revoked;
- real loopback HTTP register/login/current-user/user-create/logout cookies;
- schema idempotency/fingerprint;
- traversal, absolute, tilde, symlink-root and symlink-component denial.

The product scan found no hosted JWT, OAuth, social login, ReSono API URL,
service API key, R1 tunnel, Foundry or Agent Hub code.

## Donor immutability

Voice donor pre/post fingerprints still match:

- tracked diff: `0d9a4ce77e3707940c4f3becc5ecbfb641eb50f4df975c7e971f52e14e6942da`;
- complete status: `c04e2a6182a1630afee7e46b6662dd2fbc5cf6c52c3267b9c9cb4750ff542332`.
