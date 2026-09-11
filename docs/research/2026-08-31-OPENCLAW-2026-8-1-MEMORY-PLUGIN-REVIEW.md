# OpenClaw 2026.8.1 Memory and Plugin Review

Date: 2026-08-31  
Exact donor: `.donors/openclaw-v2026.8.1`  
Commit: `ea806575e6450e4d1efdfc72c19f04be982a1b9b`  
License: MIT  
State: sparse, read-only source review; not installed

## Version conclusion

Current official source identifies itself as `2026.8.1`. There is no verified
official semver `2.0` release identifier. The material “2.0” change is the new
plugin/runtime generation: native manifests, exclusive capability slots,
`registerMemoryCapability`, SQLite-first runtime state and stricter public SDK
boundaries.

## Current memory architecture

- `plugins.slots.memory` selects exactly one `kind: "memory"` plugin.
- `memory-core` is the default slot owner.
- `memory-core` registers `memory_search`, `memory_get`, prompt construction,
  flush planning, runtime authorization and public artifacts.
- Its built-in index is per-agent SQLite with FTS5, optional sqlite-vec and
  hybrid retrieval, while curated memory remains file-backed product content.
- `memory-lancedb` demonstrates the external memory-plugin pattern: register
  tools, `before_prompt_build` auto-recall, successful `agent_end` auto-capture,
  service lifecycle and an optional memory capability.
- Memory plugins must use `openclaw.plugin.json`, declare `kind: "memory"`,
  publish their tool contracts and be selected in the exclusive memory slot.

## Native SQL conclusion

OpenClaw is SQLite-first for its own global and per-agent runtime state. The
public runtime includes keyed state/SQLite facilities, but this does not make
OpenClaw's database a shared cross-system memory authority. Direct access to
Vault PostgreSQL would bypass Vault integration identity, grants, scope,
classification, attribution, replay control and revocation.

The Vault adapter therefore needs no local SQL schema. It should be stateless
apart from OpenClaw's normal plugin registry/config state and communicate only
with the loopback Vault memory contract.

## Minimal Vault adapter

1. Native JavaScript package with `openclaw.plugin.json`.
2. `kind: "memory"`; selected through `plugins.slots.memory`.
3. Exact namespaced tools: `vault_memory_search`, `vault_memory_get`,
   `vault_memory_store`, `vault_memory_correct` and `vault_memory_forget`.
4. `before_prompt_build` performs bounded recall and injects data-only context.
5. Successful `agent_end` submits one bounded attributable proposal.
6. Vault credential determines user/workspace scope; client supplies neither.
7. No OpenClaw core patch, local memory database, migration, marketplace,
   background framework or compatibility shim.

## Compatibility consequence

Selecting the Vault plugin replaces `memory-core` in the exclusive memory slot.
Its file-backed memory search, dreaming, standing-intent tool and public
artifact exports are not silently retained. That is preferable to two
competing canonical memory systems. OpenClaw's unrelated SQLite runtime state
continues normally.

## Required proof

- manifest discovery and exclusive-slot selection;
- exact tool registration;
- automatic recall and successful-turn proposal;
- correction/forget only with their exact Vault grants;
- no scope fields or database credentials;
- timeout/failure containment;
- revocation and replay denial; and
- no change to the pinned donor.
