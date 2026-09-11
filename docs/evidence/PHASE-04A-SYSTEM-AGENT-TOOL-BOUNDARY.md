# Phase 4A System-Agent and Tool Boundary Evidence

Date: 2026-08-29  
Status: PASS — bounded entry slice; Phase 4 remains open

## Implemented

- Immutable runtime inventory containing only `voice` and `background`.
- No registration, installation or mutation API for agent identities.
- R1/Voice-derived canonical tool definition and catalog shapes.
- Tool schema validation, fixed-agent audience filtering, local authorization
  callback, invocation context and observational evidence callback.
- Dynamic capability-source replacement for later Plugin/MCP integration; it
  changes tools only and cannot change system-agent inventory.
- Exact Phase 4 donor inventory and frozen build contract.
- Corrected master-plan wording so Voice—not R1—is the primary Voice/provider/
  tool donor.

## Verification

After locking `jsonschema==4.23.0` and synchronizing the reproducible
environment:

```text
.venv/bin/pytest -q tests/unit
55 passed in 3.15s
```

Tests reject every prohibited sampled identity (`build`, `foundry`, `hub`,
`specialist`, `coordinator`, `developer`, `marketplace`, `package`,
`generated`, `research`, `communications`) and prove tool audience,
authorization, schema and collision enforcement.

## Anti-drift result

This slice creates no Voice session, provider, Background run or extension
lifecycle behavior beyond the frozen order. It does not copy Voice
`agent_packages/`, Agent Foundry, Agent Hub, Build Agent, specialist agents,
Link/A2A or cloud authority. Phase 4 remains open pending Voice sessions,
provider boundaries, transcript/tool wiring, Background Agent persistence and
the full exit suite.
