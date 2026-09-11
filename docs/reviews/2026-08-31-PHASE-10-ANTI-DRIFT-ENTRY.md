# Phase 10 Anti-Drift Entry Review

Date: 2026-08-31  
Review type: internal same-context review  
Decision: `CONDITIONAL CONTINUE`

## Grounding result

- The owner explicitly activated planning for standards-based Plugins and
  Hermes/OpenClaw compatibility.
- Grounding already authorizes optional revocable external memory adapters.
- Vault remains complete without external agents and remains the canonical
  memory authority.
- Plugins remain capabilities for the fixed Voice and Background agents; no
  third agent is introduced.
- Phase 9 routing is not pulled forward. Phase 10 is loopback-only.

## Minimality attack

Rejected as unnecessary for the admitted outcome: general Vault exposure,
Mail/Contacts/Calendar APIs, stdio/SSE execution, arbitrary in-process Plugin
code, marketplace/update/signature infrastructure, event/webhook framework,
client-specific extension namespace, cross-device pairing, keystore brokering,
automatic import and continuous bidirectional mirroring.

The retained work is the minimum complete chain: standards correction, scoped
local memory service, Hermes adapter and donor-gated OpenClaw adapter.

## Blocking findings

OpenClaw has no frozen local donor. M4 remains `BLOCKED/REOPEN` until the exact
release, paths, hashes, license and compatibility tests are recorded. This does
not block M0 research, M1 conformance correction, M2 Vault service work or M3
Hermes work after their own gates pass.

## Entry judgment

Planning is ready. Implementation starts only milestone by milestone. M0 is the
next authorized action; later milestones may not borrow its expected evidence
in advance.
