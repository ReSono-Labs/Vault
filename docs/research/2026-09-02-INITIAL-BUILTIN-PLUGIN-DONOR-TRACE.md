# Initial built-in plugin donor trace

Date: 2026-09-02  
Scope: Markets, Weather, News, Local Events, Agent Mail

These five features are capabilities of the two fixed Vault system agents. They
do not create agent identities. They are permanent built-ins: a user can turn
them on or off but cannot delete them. Imported third-party Plugins, Skills and
MCP connections remain removable.

## Donor behavior retained

- Weather uses the Voice Open-Meteo location and forecast route and requires no
  API key. Vault stores a primary location and up to 12 additional locations.
- News retains the Voice topic list, 1–10 headline limit and canonical RSS feed
  map. Feed URLs are intentionally hidden from the normal user interface.
- Markets retains the Voice overview, symbol search, quote and news tool
  contracts. This standalone build uses the already configured local provider's
  cited live-search route rather than importing the hosted Alpha Vantage secret.
  The provider-neutral search boundary dispatches to OpenAI Responses Web
  Search, Gemini Google Search grounding, or xAI Responses Web Search according
  to the workspace's selected provider; credentials never cross endpoints.
- Local Events retains setup-first location/radius/interests, live public-web
  discovery and the existing Calendar authority boundary. No ReSono cloud
  fallback is admitted.
- Agent Mail retains a distinct mailbox role and the canonical Mail
  read/search/archive/compose/confirmed-send behavior. It uses the same local
  encrypted credential store but cannot resolve a normal personal mailbox.

## Local implementation boundaries

- Catalog/state/configuration: `app/vault_runtime/builtin_plugins.py`
- Runtime tools: `app/vault_runtime/builtin_plugin_tools.py`
- Agent Mail role/tool adaptation: `app/vault_runtime/email_*` and
  `app/vault_runtime/signals/email/session_tools.py`
- Local API: `/builtin-plugins` and `/mail/agent-accounts`
- UI: `frontend/src/browser-voice/CapabilitiesPanel.tsx`

Activation is checked during tool projection and again during invocation. All
settings are scoped to the authenticated local user and active workspace.

Public-search results share one local contract: answer text, public URL
citations, provider identity and model identity. Results without a grounded
answer or at least one valid public citation are rejected.
