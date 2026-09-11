# Grounding Correction Review

Review type: internal same-context correction review  
Status: CONDITIONAL; implementation remains paused pending dependency inventory

## Corrected authority

- Vault already exists in Voice.
- Voice `app/vault_runtime/` and Browser Voice are primary.
- ReSono hosted authentication/control authority is removed, while local
  authentication remains.
- The complete updated R1 memory labels/domains/lifecycle are a required merge
  into existing Voice Vault memory boundaries.
- Exactly Voice Agent and Background Agent remain.
- All non-system agents, Agent Foundry and Build Agent are removed.

## Drift attacks

| Attack | Result |
|---|---|
| Treat project as a new Vault design | Rejected; extraction language controls |
| Make R1 the runtime architecture | Rejected; R1 is secondary, with memory merge explicitly required |
| Invent SQLite/new `src/vault` layout | Rejected scaffold removed |
| Interpret cloud-auth removal as no authentication | Rejected; local account/session authority required |
| Treat every first-party agent as a system agent | Rejected; system role definition controls |
| Remove useful features together with specialist agents | Rejected; capabilities remain as tools/services where grounded |
| Keep Build Agent because it is “system-only” in donor | Rejected by explicit owner decision |

## Remaining conditional evidence

The borrowing matrix is consistent and the R1 fixed generic Background Agent is
mapped. Phase 1 must not resume until the Voice Vault import dependency closure
identifies exact file subsets. This is a research task, not an owner-decision
blocker.
