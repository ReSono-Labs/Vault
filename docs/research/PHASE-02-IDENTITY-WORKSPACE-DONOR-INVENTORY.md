# Phase 2 Identity and Workspace Donor Inventory

Date: 2026-08-29  
Method: read-only source inspection

## Required outcome

Up to four local human accounts authenticate to the installed Vault and may
access only workspaces for which they hold an active membership. ReSono account,
tenant, hosted JWT, social login, email-delivery, service-account and enterprise
role authority are absent.

## Exact reusable Voice donors

Root:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/`

| Donor | SHA-256 | Reuse |
|---|---|---|
| `app/core/security/passwords.py` | `e58250e6a9770111e132c880e89ab2cfd8dd5156a955bca8de0040592fbbd431` | PBKDF2-SHA256 password hash/constant-time verify |
| `app/core/security/tokens.py` | `122f1f0f1df10e9733ca4ec59e4ec78dd9aed8eb817ac41e09dc5766ca8473ab` | SHA-256 opaque-token hash; hosted JWT creation/decoding excluded |
| `app/modules/identity_access/http_sessions.py` | `7fd768d903a3712120f37c8ad3ce2e022308cc7e0d8e155b70f7fa1a943d1912` | strict SameSite, HttpOnly refresh cookie and double-submit CSRF comparison |
| `app/modules/identity_access/normalization.py` | `869914ebcd640c5247a0e8af82599573a3cba081bcb5030c40b4815891cd78f3` | identifier normalization, adapted to local username/display-name authority |
| `app/modules/identity_access/policies.py` | `2a3746e58b89784feac3692fd2fc31e31aa90961bf03c134a76c2dc9c8c365a8` | session TTL, five-failure lock threshold and rate-limit constants only |
| `app/modules/identity_access/models.py` | `55f5f61d32c2f030e2cbf7a33ece4eb55bebb68cf6f3d1f2ce7d1f93ce64fd9d` | account/password/session/refresh/revocation field semantics only |
| `app/modules/identity_access/repository.py` | `dfae7c871a628276ebb7d0ae11260dd564a7e18c0c41f031a4545af8d0fa0b33` | account lookup, session create/find/revoke, failure accounting patterns |
| `app/modules/identity_access/services/base.py` | `788f0e086eea2ed64aa02fe5a36ff5f2ef7056eea89fd6243e8f9bca4017310a` | opaque refresh generation/hashing, session envelope and revocation patterns |
| `app/modules/identity_access/services/sessions.py` | `3074ff2328f161bcc0ed94c937ff9475ee43a41aead7f325fb004d2af17005f5` | password login, refresh rotation, expiry, logout and lockout behavior |
| `app/modules/account_onboarding/models.py` | `ce2bce358a6bb8402651755808985cfdebff1835d1e58ada41c0f659fa99b018` | workspace and active membership field/constraint semantics |
| `app/modules/account_onboarding/repository.py` | `b79b4cbb4e5f294e2dece81053588b19681b1043de574382783b70375e8d36fa` | workspace lookup/create and active-membership query patterns |

Applicable donor tests are `tests/integration/test_identity_registration.py`,
`test_identity_sessions.py`, `test_identity_models.py`, and
`test_onboarding_self_service.py`; only locally relevant cases may be carried.

## Explicit subtraction

- tenants and tenant-scoped roles;
- email as a required identity or verification channel;
- hosted signed access JWT and ReSono JWT secret;
- service accounts/API keys, developer/support/operator roles;
- terms/privacy/developer-policy acceptance workflows;
- SMS/email MFA, password-reset email and browser-approval email;
- Redis-backed/cloud-wide throttling;
- social/OAuth login and ReSono-hosted admin authority;
- device trust and step-up flows until separately grounded.

## Required new local boundary

`NEW`: local authority records must live in Voice Vault's existing PostgreSQL
`vault_private` boundary because the donor's accounts/workspaces are hosted
platform tables. The minimum new records are local users, password/login state,
workspaces, memberships, and opaque sessions. This is an allowed local-only
replacement, not a datastore redesign.

The first installer creates an owner setup credential outside normal onboarding.
Normal web onboarding remains name plus experience after authentication. The
credential mechanism must never silently create a passwordless management
surface.
