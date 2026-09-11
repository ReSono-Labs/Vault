# Security and Privacy Threat Model

Status: frozen candidate v1

| Threat | Required control | Negative evidence |
|---|---|---|
| Cross-user/workspace access | Repository-level scoped predicates | User A cannot enumerate/read/mutate B |
| Session theft/CSRF | HttpOnly session, origin and CSRF checks, expiry | Cross-origin mutation denied |
| Weak local credentials | Memory-hard password hashing, rate limits, safe recovery | Offline hash and brute-force review |
| Path traversal/symlinks | R1 confined workspace rules | Escape and symlink tests denied |
| Malicious archive | R1 quarantine/limits/schema/confirmation | Traversal, bomb and collision corpus denied |
| MCP credential leakage | Sealed secret store; config separation | No secret in DB export/log/model context |
| SSRF | R1 outbound destination validation | Private/metadata/redirect targets denied |
| Integration overreach | Revocable identity and operation scopes | Revocation immediately denies access |
| Memory poisoning | Evidence, authority and reconciliation pipeline | Conflicts do not silently overwrite |
| Unsafe upgrade | Signed artifact, backup, migration and rollback | Failed upgrade restores prior state |

Loopback is the default trust boundary, not authentication. Third-party code is
disabled by default. Sensitive values are redacted before evidence/model use.
Audit history is attributable but must not retain plaintext secrets.

Security review is required at every phase exit. A high-impact unresolved
finding blocks only its dependent phase and release.
