# Phase 4C R1 Memory/Learning Anti-Drift Exit

Date: 2026-08-29  
Review type: internal same-context implementation review  
Result: PASS for Phase 4C donor-supported scope

## Authorities reread

- `GROUNDING.md`, `INDEX.MD`, `SKILLS.MD`
- anti-drift protocol, borrowing matrix, feature donor map, master plan, phase
  contracts, progress ledger
- contract 20 and the Phase 4C donor cut-point inventory
- M1, M2, and M3 evidence

## Findings

1. Updated R1 remains functional authority for memory/learning. Voice Vault
   remains PostgreSQL and local user/workspace authority.
2. Voice now receives actual scoped memory context, captures only donor-proven
   final transcript events, finalizes non-empty sessions on close, and supports
   authenticated idempotent retry.
3. The R1 reviewer is strict, bounded, citation-required, secret-filtering, and
   capability-only. Runtime identity remains exactly Voice and Background.
4. Background now preserves R1 memory references, strict typed output, and
   durable phase evidence. Automatic memory writeback remains excluded because
   no donor proves it.
5. Platform Learning, Agent Hub, cloud authentication, External AI, social
   posting, recipes, local events, Build Agent, specialists, and new agent
   identities were not admitted.
6. No taxonomy label, lifecycle state, reconciliation rule, evidence/version
   behavior, correction/forget confirmation, or offline truthfulness was
   removed.

## Objective verification

Real PostgreSQL full suite:

```text
194 passed in 97.40s
```

Frontend:

```text
2 test files, 6 passed
TypeScript/Vite production build: PASS
```

Runtime inventory:

```text
system_agents=voice,background
```

Production exclusion scan found only the frontend negative test containing
excluded capability names; none were present as production capabilities.

Donor state remained:

```text
Voice commit: 0f3b34223f745920e79d1d9db301f3b639d08393
Voice tracked diff: 0d9a4ce77e3707940c4f3becc5ecbfb641eb50f4df975c7e971f52e14e6942da
R1 commit: 91d9e70bbe156f03c79399a458416f0bebd20210
R1 tracked diff: 90f9c55912d93683e5e3dea53688b6190c2685c6437259d418520fc6be7551ff
```

Generated Python cache files under `app/` and `tests/` and the disposable
PostgreSQL container were removed after verification.

## Material decision result

- Voice R1 post-session memory/learning: `ACCEPTED` for internal implementation.
- Background R1 memory-reference and durable-evidence parity: `ACCEPTED`.
- Background automatic canonical-memory writeback: `BLOCKED/REOPEN`; not part
  of R1 parity and not implemented.
- Live owner-credential model proof: not claimed.
- Phase 6 exact visual screenshot proof: still blocked by unavailable browser.
- Phase 7 public release: still blocked by missing licensor-approved license
  and notice authority.

Phase 4C is complete without expanding scope. This review does not clear the
independent Phase 6 or Phase 7 blockers.
