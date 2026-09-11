# AI provider contract

## Outcome

Vault has one selected AI provider per effective user workspace. That selection
is used by Browser Voice and by the fixed Background Agent. Provider credentials
remain encrypted and scoped by the existing shared/individual account policy.

Phase one providers are:

| Provider | Voice transport | Text/background | Default voice model | Default text model |
| --- | --- | --- | --- | --- |
| OpenAI | Realtime WebRTC | Responses/Agents SDK | `gpt-realtime` | `gpt-5.6-sol` |
| Google Gemini | Gemini Live WebSocket | Gemini `generateContent` | `gemini-3.1-flash-live-preview` | `gemini-2.5-pro` |
| xAI Grok | Realtime WebSocket | OpenAI-compatible API | `grok-voice-latest` | `grok-4-0709` |

Provider-specific protocol translation is contained in provider adapters. Voice,
Background Agent, tool authority, memory, transcripts, and the browser UI consume
Vault-owned contracts and do not contain provider credentials.

## Selection and credentials

- The master account may add or remove any supported provider.
- A user selects one configured provider. The selection is stored in Vault, not
  only in browser storage.
- Voice uses that provider's configured realtime model and voice.
- Background Agent and other text reasoning use that provider's configured text
  model.
- There is no silent fallback to another provider. A missing or unavailable
  selected provider produces an explicit error.
- Existing shared versus individual credential rules apply independently to each
  provider.

### API key or OAuth

- OpenAI supports either an OpenAI API key or **ChatGPT OAuth**.
- Gemini supports either a Gemini API key or **Gemini OAuth**.
- xAI currently uses an API key.
- API and OAuth credentials are encrypted separately. Adding one does not erase
  the other. Users can switch the active method or disconnect only OAuth.
- OAuth actions appear only when OpenAI or Gemini is selected. The buttons are
  explicitly labeled `ChatGPT OAuth` and `Gemini OAuth`.

ChatGPT OAuth uses the bounded device authorization, Codex text endpoint, token
refresh, and realtime SDP exchange proven by these R1 donor files:

- `runtime/resono_runtime/providers/openai/subscription.py`
- `runtime/resono_runtime/providers/openai/access.py`
- `runtime/resono_runtime/providers/openai/live_transport.py`

Gemini OAuth requires a Google OAuth web client. Configure the package with
`VAULT_GOOGLE_OAUTH_CLIENT_ID` and `VAULT_GOOGLE_OAUTH_CLIENT_SECRET`, then
register `https://127.0.0.1:8765/providers/gemini/oauth/callback` as an authorized
redirect URI for the default local package.

## Embeddings

Embeddings are a separate capability. Selecting a voice/text provider does not
claim that its text model can create compatible embeddings. Phase one preserves
the existing real OpenAI embedding adapter when an OpenAI API key is available
and otherwise keeps truthful lexical memory retrieval. A future embedding selector
must include model, dimensions, migration/re-index behavior, and availability; it
must not reuse the main provider selector implicitly.

## Native voice sessions

- OpenAI API: Vault mints an ephemeral client secret and the browser uses WebRTC.
- ChatGPT OAuth: Vault exchanges the browser WebRTC offer through the Codex
  subscription realtime path and returns the SDP answer.
- Gemini: Vault mints a constrained ephemeral Live API token and the browser uses
  the provider WebSocket directly.
- xAI: Vault mints an ephemeral realtime client secret and the browser uses the
  provider WebSocket directly.

Long-lived API keys never leave Vault. All three adapters receive the same frozen
Vault context and granted function tools. Provider events are normalized at the
browser boundary before transcript capture and local tool execution.

## Deliberate exclusions

- No new MCP server is part of provider inference.
- No generic STT -> text model -> TTS pipeline is included in phase one.
- No automatic provider failover, routing heuristics, model marketplace, or model
  discovery is included.
- Provider selection does not change A2A, external memory, or extension authority.
