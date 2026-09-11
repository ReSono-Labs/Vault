# Phase 10 M4 OpenClaw 2026.8.1 Adapter Evidence

Date: 2026-08-31  
Status: exact donor reviewed and package built; live activation remains open

## Exact donor

- tag: `v2026.8.1`
- commit: `ea806575e6450e4d1efdfc72c19f04be982a1b9b`
- license: MIT
- local sparse path: `.donors/openclaw-v2026.8.1`
- installed/executed: no

The donor was inspected read-only. Detailed findings are in
`docs/research/2026-08-31-OPENCLAW-2026-8-1-MEMORY-PLUGIN-REVIEW.md`.

## Delivered

`integrations/openclaw-vault-memory/` is a native OpenClaw memory-slot package
with:

- required native manifest and exact memory kind;
- current `>=2026.8.1` Plugin API compatibility declaration;
- search, get, automatic proposal/store, granted correction and granted forget;
- bounded automatic recall at `before_prompt_build`;
- bounded successful-turn proposal at `agent_end`;
- no user/workspace fields, local SQL schema or Vault database credentials; and
- failure containment through bounded HTTP requests and warning-only hook
  failures.

## Verification

```text
JavaScript syntax check: passed
package and plugin JSON parse: passed
npm package dry-run: passed (4 intended files, no bundled dependencies)
```

## Native SQL decision

OpenClaw's current SQLite-first state system remains owned by OpenClaw. The
adapter does not create parallel SQL state and never connects to Vault
PostgreSQL. Vault remains the only canonical shared-memory database.

## Remaining M4 exit

OpenClaw is not installed locally. Live plugin discovery, slot selection,
automatic recall and successful-turn proposal require a chosen OpenClaw
installation plus a Vault-issued integration credential. Those external-state
steps are not claimed.

