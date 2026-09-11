# Phase 4C M1 Structured Memory Reviewer Evidence

Date: 2026-08-29  
Status: PASS for bounded M1; production finalization remains M2

## Donor and adaptation

The implementation ports the admitted behavior from:

- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/agents/memory_reviewer.py`
  SHA-256 `12f494390e171a28b6016ab2df3ffb5e832424982af4a20a30dc6e48a2708267`;
- the already copied R1 SDK runner; and
- Vault's encrypted workspace provider credential boundary.

Target:

- `app/vault_runtime/memory/openai_reviewer.py`.

The reviewer is capability-only. It is absent from
`SYSTEM_AGENT_INVENTORY`, which remains exactly Voice and Background.

## Preserved behavior

- one bounded Agents SDK structured-output call;
- R1 contract version 2;
- exact domains, types, source authorities, confidence, sensitivity, and
  reconciliation intents;
- strict candidate fields and rejection of extra structured-output fields;
- 100,000-character transcript, 32-candidate, 4,096-character candidate,
  20,000-character summary, and 120-character key bounds;
- exact transcript citations required before a candidate is admitted;
- `shouldStore` gating and forbidden-secret filtering;
- current local user as private-memory subject;
- workspace-scoped encrypted provider access; and
- truthful failure with no fabricated review or memory.

## Verification

Command:

```text
uv run pytest -q tests/unit/test_openai_memory_reviewer.py tests/unit/test_background_openai_executor.py
```

Result:

```text
5 passed in 2.09s
```

Covered positives/negatives include exact cited candidate mapping, wrong
contract, secret and uncited filtering, provider failure, empty transcript,
malformed JSON, candidate bounds, credential scope, and Background context
regression.

## Limits

This evidence does not claim production composition, Voice transcript intake,
finalize-on-close, embeddings, PostgreSQL integration, Browser Voice teardown,
or Background phase-evidence parity. Those remain M2–M4.
