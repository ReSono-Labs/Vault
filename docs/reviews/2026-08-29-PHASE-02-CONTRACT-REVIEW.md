# Phase 2 Contract Anti-Drift Review

Review type: internal same-context adversarial review  
Result: PASS for implementation entry

## Material decision gate

Question: where does standalone user/session/workspace authority live when the
Voice donors implement those records in the hosted platform?

Authority: Grounding requires local accounts, private workspaces, local
authentication, Voice Vault datastore preservation, and no ReSono authority.
Source inspection proves Voice Vault already uses PostgreSQL and the Voice
identity module contains reusable password/session/membership behavior.

Alternatives considered:

- copy hosted identity wholesale — rejected because tenants, service accounts,
  cloud JWT, email workflows and enterprise roles violate scope;
- replace Voice Vault storage with SQLite — rejected as architecture drift;
- one shared appliance token — rejected because it cannot prove user/workspace
  isolation;
- local records inside `vault_private` using copied Voice security semantics —
  selected.

Counterexample: if a protected operation can accept an account/workspace pair
without resolving an active session and membership from local storage, the
selected design has failed even when endpoint tests pass.

Dependents: all later memory, agent, tool, extension and Browser Voice access.
Decision: `CONTINUE` with the frozen Phase 2 contract.

## Adversarial findings resolved

- The four-user limit applies to non-deleted human accounts and must be locked
  transactionally, not counted in application memory.
- Setup credentials are separate from the name/experience product onboarding;
  this avoids silently weakening authentication or changing the visual flow.
- Hosted JWT is not needed; opaque locally stored session hashes provide local
  authority and immediate revocation.
- Workspace IDs from requests are selectors only. Repository authorization is
  authoritative.
- Shared workspace membership is in scope; ownership-transfer workflow is not
  required and remains deferred.
- The contract introduces no agent, memory, extension, UI, routing or remote
  management behavior.

Donor fingerprints remain equal to the Phase 1 baseline. Implementation may
start with the smallest schema/security slice and must update the Index before
claiming any additional surface.
