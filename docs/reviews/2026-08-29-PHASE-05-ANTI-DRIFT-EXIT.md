# Phase 5 Anti-Drift Exit Review

Date: 2026-08-29  
Decision: PASS; Phase 6 planning may begin

## Grounding reread

Reviewed `GROUNDING.md`, `SKILLS.MD`, `INDEX.md`, the copied anti-drift
protocol, donor map, borrowing matrix, donor-porting rule, master plan, Phase 5
inventory/contract and progress ledger.

The implementation remains a standalone Vault capability layer:

1. Voice Vault/runtime concepts remain primary.
2. R1 contributes only the frozen missing extension security/lifecycle slices.
3. No ReSono Labs cloud authentication or control-plane authority exists.
4. Extension authority is local and scoped to existing users/workspaces.
5. Agent inventory remains exactly Voice Agent and Background Agent.
6. Plugins, Skills, MCP servers and tools are capabilities, never agents.
7. There is no Build Agent, Foundry, Hub, package/specialist/generated agent or
   agent delegation/import surface.
8. Link, Tailscale, remote management, A2A and shared external memory remain
   deferred.

## Adversarial findings resolved

| Potential drift/failure | Resolution |
|---|---|
| Import archive executes code | Plugin/Skill content remains data; no automatic script/import path |
| Skill grants tools through frontmatter | `allowed-tools` is parsed only and grants nothing |
| MCP discovery silently grants tools | Discovery only persists validation output; exact grants are separate |
| Dynamic tool leaks between users | Tool definitions carry exact local user/workspace scope and catalog filters at listing/invocation |
| Disabled/revoked connection remains callable | Durable grant is rechecked on invocation and catalog sources are removed on scope/extension/safe-mode change |
| Credentials enter manifests/model/API | Public config rejects credential headers; AES-GCM secret owner returns them only to transport construction |
| First boot exposes third parties | Runtime setting defaults third-party projection off |
| Replacement loses stable version | Staged rename, previous tree and recovery record preserve/restore stable content |
| Failed component collision partly installs | PostgreSQL transaction rolls back extension and ownership changes; filesystem service rolls back/removes staged version |
| Donor “built-in” agent returns through Plugin | Schema, source scan and immutable inventory reject all identities except Voice/Background |

## Evidence judgment

The full 151-test PostgreSQL-backed suite covers Phase 5 happy paths and
required security negatives. Donor commit/diff hashes remain unchanged. The
index, donor inventory, build contract, evidence and progress ledger identify
the current owners and limits.

No Phase 5 requirement is supported only by file presence. Phase 5 exits.
Browser Voice remains untouched until a separately frozen Phase 6 donor/UI
contract is reviewed.
