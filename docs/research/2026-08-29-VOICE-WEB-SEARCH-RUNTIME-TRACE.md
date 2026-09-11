# Voice Web Search Runtime Trace

Date: 2026-08-29  
Status: donor trace complete; bounded standalone port implemented

## Governing requirement

Vault must expose the same direct Web search that successfully ran in the
Voice Vault on the Orange Pi 5. This is a public-read tool of the two fixed
system agents. It is not the excluded External AI product, a signal family, or
another agent.

## Observed successful execution

Read-only inspection of the active Orange Pi Vault journal found the completed
event at 2026-08-29 17:51:

- tool name: `web_search`;
- target: `web.search`;
- handler: `web`;
- dispatch path: `registered_adapter`;
- outcome: `completed`;
- failure code: `none`; and
- duration: 10,775 ms.

No cloud routing or ReSono authentication step appeared in the execution path.

## Exact donor paths

- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/contracts/internal/browser_voice_tools.py`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/web_search_provider.py`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/signals/openai_search.py`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/session_tools/brokers/web.py`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/session_provider_request.py`

The deployed verification copy was read at the matching paths below
`/opt/resono-vault/` on `orangepi5`. Donors were not modified.

## Preserved behavior

The standalone tool keeps the donor name and one-field `{query}` schema. Voice
is told to announce a short research preamble and call the tool for current or
time-sensitive public information. The adapter:

1. normalizes and bounds the query to 2,000 characters;
2. resolves the authenticated user's effective shared or individual OpenAI key;
3. calls `POST /v1/responses` with the built-in `web_search` tool and low search
   context;
4. supplies the current UTC date and `live_only` freshness policy;
5. treats Web material as untrusted evidence and sends no private memory or
   workspace context;
6. extracts only `http`/`https` URL citations without embedded credentials;
7. rejects empty answers or answers without valid citations; and
8. returns `web.search` evidence through the canonical local tool result.

## Required standalone adaptations

The donor obtained provider settings from the Voice platform configuration.
Standalone Vault instead uses its existing encrypted, workspace-scoped
`VoiceProviderCredentialStore`, including the owner's shared-key policy and an
account's optional individual key. The configured Background/text model is the
local Responses model because Vault has no ReSono-hosted search-model selector.
No provider secret is placed in tool arguments, responses, logs, prompts, or
memory.

The large donor session runtime and its unrelated signal, package-agent,
External AI, and social-post handlers were not copied. The canonical Vault
catalog supplies the same tool schema and dispatches the bounded adapter.
