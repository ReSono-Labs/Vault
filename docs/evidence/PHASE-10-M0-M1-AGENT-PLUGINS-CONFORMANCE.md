# Phase 10 M0–M1 Agent Plugins Conformance Evidence

Date: 2026-08-31  
Result: accepted for the supported Agent Plugins 1.0 subset  
Contract: `docs/planning/25-PHASE-10-AGENT-PLUGINS-AND-EXTERNAL-MEMORY-CONTRACT.md`

## Delivered

- unknown `plugin.json` top-level fields are diagnosed and ignored;
- a non-object `extensions` value is diagnosed and ignored as required;
- an empty `mcpServers` map is valid;
- invalid individual Skills and MCP server entries are skipped with diagnostics;
- independently valid Plugin components remain installable; and
- Plugin preflight returns nonfatal diagnostics to the owner.

No new executable transport or runtime was added. Streamable HTTP remains the
only executable MCP transport. Discovery still grants nothing, safe mode and
exact grants remain controlling, and Plugin code is not imported into Vault.

## Donor and standards state

The authoritative standard and schemas are frozen in the Phase 10 inventory.
The local Hermes checkout remained read-only at
`41447a6d7063b2772b0c2f26a5b22d9bd444fb43`. OpenClaw remains donor-blocked and
was not installed or modified.

## Verification

Focused parser/lifecycle:

```text
22 passed in 0.25s
```

All extension unit tests:

```text
38 passed in 0.34s
```

PostgreSQL extension/API tests:

```text
11 passed in 17.87s
```

Supported full workflow:

```text
228 passed in 140.46s
Frontend: 9 passed
Production TypeScript/Vite build: passed
```

## Negative conclusions

- no component gained a grant from discovery or installation;
- no invalid sibling component caused a valid component to execute;
- no third system agent or agent-registration path was added;
- no broad Vault API, routing, marketplace, event framework or Plugin SDK was
  introduced; and
- no Phase 9 or OpenClaw implementation work was pulled forward.

