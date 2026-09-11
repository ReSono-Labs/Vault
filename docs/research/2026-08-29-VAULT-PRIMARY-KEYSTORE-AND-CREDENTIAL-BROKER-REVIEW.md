# Vault Primary Keystore and Credential Broker Review

**Date:** 2026-08-29  
**Status:** `RESEARCH ONLY / CONDITIONAL`  
**Implementation authority:** None

## Decision summary

Vault can be the primary keystore for Hermes, OpenClaw, and other approved
systems. A Vault-issued ephemeral token is possible, but it authenticates the
external system **to Vault**. It does not automatically become a valid OpenAI,
Anthropic, mail, calendar, or other provider credential.

There are two valid integration modes:

1. **Credential broker/proxy — preferred.** The external platform receives a
   short-lived Vault capability token. It sends the allowed provider operation
   to Vault; Vault uses the real credential and returns the result. The real key
   never leaves Vault.
2. **Secret resolution — compatibility mode.** The external platform invokes a
   Vault secret-source adapter. After authenticating and authorizing it, Vault
   returns the actual provider key through an encrypted channel. The adapter
   holds the key only in process memory where possible. This supports software
   that must contact the provider directly, but the external host/process can
   read and misuse the key while it is present.

For OAuth, Vault may store the long-lived refresh token and issue or return a
short-lived provider access token. For a static API key, Vault cannot shorten
the provider's credential lifetime unless that provider offers scoped or
ephemeral credential issuance. Rotation remains provider-specific.

## Verified platform support

### Hermes

Hermes supports composable external secret sources. A standalone plugin may
implement `SecretSource.fetch()` and register through
`ctx.register_secret_source()`. Hermes resolves secrets at process startup and
hydrates the provider variables it needs. Its official documentation presently
describes Bitwarden, 1Password, command helpers, and standalone secret-source
plugins.

Official evidence:

- <https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/secrets/index.md>
- <https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/environment-variables.md>

**Vault fit:** ship a standalone Vault secret-source plugin. Its bootstrap
credential is an integration credential, not a provider key. The plugin may
fetch approved secrets at startup. This is compatibility mode because resolved
keys enter the Hermes process environment. A future provider adapter could
instead point Hermes at a Vault-hosted OpenAI-compatible broker endpoint,
keeping upstream keys inside Vault.

### OpenClaw

OpenClaw supports `SecretRef` values backed by environment, file, or executable
providers. Native plugins may publish an executable secret-provider integration
in their manifest. OpenClaw resolves these references into runtime snapshots and
supports audit, dry-run apply, and reload workflows.

Official evidence:

- <https://github.com/openclaw/openclaw/blob/main/docs/gateway/secrets.md>
- <https://github.com/openclaw/openclaw/blob/main/docs/cli/secrets.md>
- <https://github.com/openclaw/openclaw/blob/main/docs/plugins/manifest.md>

**Vault fit:** ship a Vault plugin that publishes a SecretRef exec-provider
preset, or configure a tightly controlled standalone exec resolver. The resolver
authenticates to Vault, requests only the referenced secret, prints it only on
the expected private stdout contract, and never writes it to disk or logs. This
still exposes the resolved value to the OpenClaw gateway process. Broker mode is
stronger where OpenClaw's provider configuration can target a Vault-hosted
compatible endpoint.

## Token and identity model

Do not use one reusable “Vault API key.” Use a two-stage enrollment and runtime
model:

1. Vault creates a random, short-lived, single-use pairing code. The stored
   server representation is a keyed digest, not plaintext.
2. The remote adapter presents the code over authenticated TLS and proves the
   intended Vault endpoint.
3. Vault registers one integration identity for the exact installation/profile
   and returns a durable device credential or client certificate through that
   protected session.
4. The durable credential is stored in the remote operating-system keystore or
   a locked service-owned file when no portable keystore exists.
5. At runtime, that identity requests a short-lived capability token bound to:
   integration ID, user/workspace, secret/provider, operation, audience,
   expiration, and a unique token ID.
6. Vault validates current grants on every use. Revocation overrides an
   otherwise unexpired token.

Recommended capability-token properties:

- random opaque token, or an asymmetric signed token only where offline
  verification is required;
- 5–15 minute lifetime for broker requests and one use or seconds-to-minutes for
  raw-secret retrieval;
- exact audience and Vault endpoint binding;
- no secret value, provider refresh token, user session, or workspace-wide
  authority inside the token;
- replay protection for pairing and raw-secret retrieval;
- rate, concurrency, and spend/request ceilings; and
- independently revocable integration and grant records.

An opaque token is preferable for the normal online design: Vault can validate
revocation and policy centrally, and no downstream service needs Vault signing
keys. A signed token is useful only when a component genuinely must verify it
without contacting Vault.

## Secure delivery choices

| Method | Real provider key leaves Vault? | Use |
|---|---:|---|
| Vault provider broker/proxy | No | Preferred for AI/provider calls where a compatible endpoint can be configured |
| Vault OAuth broker | Usually no refresh token; access token may be returned | Provider-specific OAuth integration |
| Hermes secret-source plugin | Yes, into Hermes memory/environment | Compatibility when direct provider access is required |
| OpenClaw SecretRef exec resolver | Yes, into OpenClaw runtime snapshot | Compatibility when direct provider access is required |
| Shared file, database mount, `.env` copy | Yes, persistent | Rejected |
| Secret in URL, command argument, QR code, logs, MCP/tool result, or model context | Yes and broadly exposed | Rejected |

If a raw key must be returned, the adapter must request one exact secret by
opaque secret ID. Vault returns it once over mutually authenticated TLS; the
adapter sends it directly to the native secret-resolution interface, avoids
shell interpolation and command arguments, redacts stdout/stderr and crash
dumps, and never exposes it to agent tools, skills, MCP servers, sandboxes, or
memory. This reduces exposure but cannot protect the key from root or a
compromised Hermes/OpenClaw process on that device.

## Keystore ownership and scopes

Vault encrypts provider credentials at rest under a local master encryption
key. Each secret record belongs to one user/workspace and records provider,
purpose, credential type, creation/rotation state, and allowed integrations.
Secret values must never enter the R1 memory/learning store.

The permanent master account may manage household account integrations, but an
integration receives only explicitly granted secret references and operations.
Memory permission does not imply secret permission. AI inference, mail send,
mail read, calendar write, contacts read, and administrative secret management
are separate grants.

The Vault master encryption key must not be derived solely from an application
constant or stored beside the encrypted database without OS/hardware protection.
Cross-platform key custody requires a separate design for Linux secret service
or TPM/file protection, macOS Keychain, Windows DPAPI/Credential Manager, backup,
headless startup, and recovery. Orange Pi hardware capabilities vary; no TPM may
be assumed.

## Onboarding proposal

The optional external-system step may offer:

- **Memory only**;
- **Credentials only**; or
- **Memory and credentials**.

After pairing, Vault lists available provider connections without exposing
secret values. The master chooses the Vault account/workspace, provider,
permitted operations, broker mode or compatibility secret resolution, and any
usage limits. The screen must explain plainly when a real key will leave Vault.
“Use broker mode” is the default; “allow this device to retrieve the provider
key” is a separate high-risk confirmation.

Detection never grants credentials. Importing a key found in an existing agent
configuration requires explicit selection, redacted preview, successful
validation, and confirmed removal from the old plaintext location. Vault must
not silently scrape `.env`, auth files, browser storage, or OS keystores.

## Security gates before implementation

- threat model the broker, resolver, pairing, host compromise, replay, confused
  deputy, SSRF, prompt injection, malicious plugins, and denial/spend abuse;
- define an exact supported secret-bearing field inventory for pinned Hermes and
  OpenClaw releases;
- ensure integrations cannot enumerate secret names outside their grants;
- authenticate the endpoint independently of Link/Tailscale routing;
- keep provider responses and credentials out of memory ingestion and logs;
- enforce user/workspace scope at the service/repository boundary;
- test concurrent users and integrations for cross-scope leakage;
- test rotation, revocation, expired tokens, offline behavior, lost device,
  restore, and master-key recovery;
- sandbox resolver processes and strictly bound output, timeout, and environment;
- document the residual fact that raw-secret compatibility mode trusts the
  external host and process; and
- never claim “key never leaves Vault” unless broker mode is used end to end.

## Anti-drift decisions

| Question | Status | Decision |
|---|---|---|
| Vault as primary keystore | `CONDITIONAL` | Feasible and aligned with local-first Vault |
| Ephemeral Vault capability tokens | `CONDITIONAL` | Yes; they authorize Vault operations, not third-party providers |
| Provider broker/proxy | `CONDITIONAL / PREFERRED` | Keeps static API keys inside Vault |
| Raw-key secret resolution | `CONDITIONAL / COMPATIBILITY` | Supported by both platforms but trusts their host/process |
| OAuth token brokering | `OPEN / PROVIDER-SPECIFIC` | Store refresh token; mint/refresh access token only where provider supports it |
| Automatic secret discovery/import | `REJECTED` | Explicit user selection and migration only |
| Shared database or `.env` synchronization | `REJECTED` | Bypasses Vault authority and persists plaintext exposure |
| Keystore implementation | `NOT AUTHORIZED` | Requires a separate contract, OS custody design, and donor inventory |

