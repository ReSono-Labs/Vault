# Hermes/OpenClaw Shared Memory Live Test Log

Date: 2026-08-31  
Environment: local Linux host; Vault Docker package; Hermes `0.20.5`; OpenClaw
`2026.8.1` (`ea80657`); Node `24.15.0`  
Scope: Vault plugin UI, external-memory boundary, Hermes provider, OpenClaw
memory-slot plugin, TLS, onboarding migration, inference and two-way memory  
Secrets: credentials and tokens are deliberately omitted

## Current result

The scoped Vault service accepted independently issued Hermes and OpenClaw
credentials. A durable memory proposed with the Hermes credential was retrieved
with the OpenClaw credential, and a durable memory proposed with the OpenClaw
credential was retrieved with the Hermes credential. Vault remained the
canonical store; neither adapter accessed Vault PostgreSQL directly.

This proves the HTTP authorization, classification, reconciliation and
cross-client retrieval path. Full automatic turn-lifecycle acceptance remains
partially open as listed under **Open items**.

## Test and incident chronology

| Area | Check or observed failure | Result | Resolution/evidence |
|---|---|---:|---|
| Vault regression | Backend suite after Phase 10 external-memory changes | PASS | 231 backend tests passed before live deployment. |
| Frontend regression | Frontend unit tests | PASS | 9 tests passed. |
| Frontend packaging | TypeScript/Vite production build | PASS | Production build completed and emitted the Connections UI. |
| Production UI | Deployed image contained `Agent memory`, `External memory access`, and `Connections` strings | PASS | Updated Docker image was deployed without replacing named data volumes. |
| Vault health | `/health` after deployment | PASS | PostgreSQL, schema and pgvector reported healthy. |
| HTTPS responsiveness | Browser and `curl` stalled during TLS setup | FAIL, FIXED | TLS was wrapped around the listening socket, allowing an idle handshake to block the accept loop. TLS wrapping is now deferred per accepted connection. |
| HTTPS concurrency regression | Health request while 20 raw TCP connections remained idle | PASS | Valid HTTPS request completed in about 0.022 seconds; follow-up health request completed in about 0.023 seconds. |
| Focused Vault server tests | `tests/unit/test_vault_runtime_local_server.py` plus package-runtime tests | PASS | 5 tests passed after the accept-loop fix. |
| Hermes package discovery | `hermes_agent.memory_providers` entry point | PASS | `resono-vault -> resono_vault_hermes:register` discovered in the Hermes venv. |
| Hermes activation | `hermes memory status` | PASS | Provider installed, available and selected as active. |
| Hermes credential/TLS search | Real provider `vault_memory_search` call | PASS | Provider authenticated to Vault and returned a valid search response. |
| Hermes gateway reload | Restart existing Hermes systemd user service | PASS | Service restarted and remained active. |
| OpenClaw install precondition | Install OpenClaw 2026.8.1 with Node 24.14.1 | FAIL, FIXED | OpenClaw required Node 24.15.0 or newer in the 24.x line. Node was upgraded to 24.15.0 and the pinned install succeeded. |
| OpenClaw local-source policy | First local plugin install | EXPECTED BLOCK | OpenClaw required explicit review confirmation for non-ClawHub code. The reviewed local package was installed with `--force`. |
| OpenClaw capability consent | Plugin install without capability acceptance | EXPECTED BLOCK | Reinstalled with `--accept-capabilities`; plugin then installed disabled pending configuration. |
| OpenClaw configuration | Credential reference, Vault URL, memory slot and grants | PASS | Credential stored in protected global dotenv; config contains the environment reference. `resono-vault-memory` selected in `plugins.slots.memory`. |
| OpenClaw runtime inspection | Plugin import and registration | PASS | Five tools registered: search, get, store, correct and forget. Two conversation hooks registered. |
| OpenClaw direct adapter search | Invoke installed plugin's actual `vault_memory_search` handler | PASS | Vault returned a valid response over verified TLS. |
| OpenClaw onboarding | Workspace setup failed with legacy-state migration message | FAIL, FIXED | Gateway stopped; `openclaw doctor --fix` migrated workspace setup state to SQLite, removed verified legacy state and repaired seven orphaned session bindings. |
| OpenClaw conversation hooks | Hooks blocked for non-bundled plugin | FAIL, FIXED | Enabled only `plugins.entries.resono-vault-memory.hooks.allowConversationAccess`; runtime inspection then reported `hookCount: 2`. |
| OpenClaw inference | Minimal agent turn, GPT-5.6-sol, minimal reasoning | PASS | Returned exactly `setup-ok`. |
| OpenClaw inference recheck | Minimal agent turn, GPT-5.6-sol, medium reasoning after user saw stale error | PASS | Returned exactly `inference-ok`; OAuth route reported usable. |
| Python 3.13 TLS | First two-way test with Vault CA | FAIL, FIXED | Python 3.13 rejected missing Authority Key Identifier. Vault CA/server generation now emits SKI and AKI. |
| Python 3.13 CA usage | Retest after SKI/AKI change | FAIL, FIXED | Python 3.13 required `keyCertSign` when CA path length is present. Correct critical Key Usage extensions were added to CA and server certificates. |
| Modern TLS regression | Python 3.13 verified `/health` using Vault local CA | PASS | HTTPS returned 200 without disabling certificate verification. |
| Classifier behavior | Two temporary/fabricated interoperability markers | EXPECTED REJECT | Both proposals returned 202/reviewed with `memoryCount: 0`; Vault correctly declined one-time test data. No cleanup was required. |
| Real shared memory, Hermes write | Hermes credential proposed the user's open-plugin-standard requirement | PASS | Vault returned 202/reviewed with `memoryCount: 1`. |
| Real shared memory, OpenClaw read | OpenClaw credential searched for the Hermes-written requirement | PASS | One matching canonical memory returned with the expected content. |
| Real shared memory, OpenClaw write | OpenClaw credential proposed Vault-as-canonical-store architecture decision | PASS | Vault returned 202/reviewed with `memoryCount: 1`. |
| Real shared memory, Hermes read | Hermes credential searched for the OpenClaw-written decision | PASS | Two relevant results returned; the top result stated that Vault is the canonical shared store for Hermes and OpenClaw. |
| Proposal timing | Automatic OpenClaw proposal used a five-second timeout | FAIL, FIXED | Live writes took about 5.4–8.6 seconds. Proposal timeout is now 30 seconds in both adapters; read timeout remains 5 seconds. |
| Hermes adapter tests after timeout change | Provider unit tests | PASS | 2 tests passed with the installed source on `PYTHONPATH`. |
| Adapter redeployment | Reinstall Hermes package and OpenClaw local plugin | PASS | Both gateways restarted; Hermes reports provider available and active. OpenClaw reports plugin loaded, activated, memory slot selected, five tools and two hooks. |
| Global agent-tool namespace | Standardize Hermes and OpenClaw public memory tools | PASS | Both adapters now expose `vault_memory_search`, `vault_memory_get`, `vault_memory_store`, `vault_memory_correct`, and `vault_memory_forget`; manifests, handlers, deterministic recall registration, and Hermes tests agree. |
| Namespaced OpenClaw get via Codex route | Ask the live agent to invoke `vault_memory_get` for a known accessible item | BLOCKED UPSTREAM | OpenClaw advertised the namespaced plugin tool, but the Codex-backed route handled it as a connector-style memory call and returned `external_ai_memory_item_not_found` before the plugin handler produced a successful receipt. The same item and credential succeeded through the installed adapter's Vault HTTP boundary. |
| Hermes namespaced tool regression | Provider tests with all five public names | PASS | 2 tests passed using the provider source on `PYTHONPATH`. |
| OpenClaw automatic capture | Complete an ordinary successful turn with no explicit memory tool, then search with the Hermes credential | PASS | Hermes independently retrieved the newly classified auto-approval constraint; `successfulToolNames` was empty for the originating turn. |
| Hermes automatic capture | Complete an ordinary Hermes primary turn with no explicit memory tool, then search with the OpenClaw credential | PASS | The OpenClaw credential retrieved the newly classified bounded-startup-profile requirement. |
| Shared startup profile API | Retrieve startup context through a scoped integration credential | PASS | Returned the same bounded `profile_memories()` selection used by Voice: active, normal-sensitivity, medium/high-confidence memory, limited to eight by default. |
| OpenClaw automatic startup injection | Fresh session asks for known dog name/breed without calling tools | PASS | Returned Teddy as a Maltese–Poodle mix from injected Vault context. The custom hook does not require OpenClaw turn tool authority because authorization is enforced by its scoped Vault credential. |
| Startup profile regression | Vault local server, PostgreSQL external-memory API, Hermes provider, OpenClaw syntax/manifest | PASS | 4 local-server tests, 3 PostgreSQL integration tests and 2 Hermes tests passed; JavaScript and manifest validation passed. |
| Local browser pairing | Plugin-generated credential hash, signed-in Vault approval, authenticated polling and resulting memory access | PASS | PostgreSQL acceptance test completed the full flow and used the plugin-held plaintext credential for a successful scoped search. Vault never received or stored its plaintext value. |
| Pairing deployment smoke test | Start and poll an unapproved pairing through deployed HTTPS API | PASS | Vault returned a short code and `pending`; the exact smoke-test row was removed afterward. |
| Pairing UI/package build | Connections deep link and both adapter pairing commands | PASS | Frontend 9 tests and production build passed; Hermes console command and installed OpenClaw pairing script are executable. |
| Self-disconnect contract | Revoke twice with the same runtime credential, then attempt search | PASS | Both disconnect calls returned revoked and subsequent memory access was denied; 5 PostgreSQL external-memory tests passed. |
| Agent-side cleanup | Hermes and OpenClaw disconnect commands | PASS | Live destructive testing proved that Hermes removes the credential and disables its external provider, while OpenClaw removes the credential, restores `memory-core`, and disables the Vault plugin. |
| Full destructive disconnect | Disconnect both original adapters and test their old credentials | PASS | Both old credentials returned `external_memory_authorization_denied`; Hermes returned to built-in-only memory and OpenClaw restored `memory-core` before both packages were uninstalled. |
| Permanent revoked-row removal | Remove revoked connection records after revocation | PASS | Backend permits deletion only for revoked records in the signed-in scope. UI now shows **Remove** for revoked rows. Five PostgreSQL tests and nine frontend tests passed. All previous revoked rows were deleted; the final list contains only one active Hermes and one active OpenClaw connection. |
| Real Hermes browser pairing | Install, run pairing command, approve in signed-in Vault, activate and restart | PASS | Pairing code was carried in the URL; no manual code or credential entry was required. Startup context returned Teddy as half Maltese and half Poodle. |
| Real OpenClaw browser pairing | Install, run pairing command, approve in signed-in Vault, configure slot and restart | PASS | Pairing code was carried in the URL; the page showed Pairing complete. Runtime reports plugin loaded/activated, five tools and two hooks. Startup context returned Teddy as half Maltese and half Poodle. |
| Fresh-pair automatic cross-agent save | Ordinary no-tool turn in each agent, queried with the opposite newly paired credential | PASS | OpenClaw retrieved Hermes's permanent-removal requirement and Hermes retrieved OpenClaw's automatic pairing-URL behavior. |
| Pairing UI ambiguity found during live test | Manual Create agent access remained visible immediately after approval | FAIL, FIXED | The accidental duplicate was revoked and removed. Pairing mode now hides the manual form and ends on a dedicated Pairing complete message. |

## Timing observations

- Vault classification/reconciliation writes observed: approximately 4.4 to
  8.6 seconds.
- Vault searches observed: approximately 0.8 to 1.9 seconds.
- The original five-second proposal deadline was therefore invalid even on the
  local host. Both adapters now allow 30 seconds only for proposals.

## Stored test outcome

Fabricated and explicitly temporary markers were rejected by classification
and never became memories. Two real user requirements were intentionally kept:

1. Vault is the canonical shared memory store used by Hermes and OpenClaw.
2. Vault's plugin system should follow the open plugin standard, remain
   plugin-based where possible, and avoid unnecessary core changes.

No credential values are present in this document.

## Open items

1. **OpenClaw memory tool ownership:** behavioral testing proved that bundled
   `memory_get` won the original duplicate name and expected a file `path`.
   Both adapters are now standardized under `vault_memory_*`. OpenClaw loads
   and advertises those five names, but its Codex-backed route intercepted the
   live `vault_memory_get` call as connector memory and returned
   `external_ai_memory_item_not_found`; this upstream routing conflict remains
   open.
2. **Correction and forget:** authorization code and unit coverage exist, but
   a live cross-client correction and forget sequence has not yet been logged.
3. **Revocation:** credential revocation is implemented and tested in the
   backend suite, but live Hermes/OpenClaw behavior immediately after revocation
   has not yet been recorded.
4. **Local plugin provenance:** OpenClaw may warn that the adapter is local and
   not ClawHub-verified. This is expected for development, but release packaging
   and signed/published provenance remain future release work.
5. **Credential rotation:** credentials were intentionally pasted into the
   testing conversation. They should be rotated after this test cycle.

## Commands represented by this log

The session used the following categories of checks. Secrets were loaded from
protected local configuration and were never written into evidence output.

```text
uv run pytest -q tests/unit/test_vault_runtime_local_server.py tests/unit/test_package_runtime.py
PYTHONPATH=integrations/hermes-vault-memory/src uv run pytest -q integrations/hermes-vault-memory/tests
npm run build
docker compose build initialize vault
docker compose up -d initialize postgres vault
hermes memory status
hermes gateway restart
openclaw plugins inspect resono-vault-memory --runtime --json
openclaw gateway status
openclaw agent ... --thinking minimal|medium --json
verified HTTPS external-memory propose/search calls with separate Hermes and OpenClaw credentials
```

## Acceptance statement

The shared credential-scoped Vault memory boundary is live, bidirectional and
proven through both automatic turn lifecycles. Optional startup memory now uses
Voice's canonical bounded profile selector. Do not yet mark every Phase 10
proof closed: runtime named-tool ownership, live correction/forget and live
revocation remain explicit verification work.
