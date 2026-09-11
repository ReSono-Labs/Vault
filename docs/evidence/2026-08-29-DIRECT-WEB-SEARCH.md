# Direct Web Search Acceptance Evidence

Date: 2026-08-29  
Status: implemented and locally running

## Acceptance

- Orange Pi successful event traced: `web_search` → `web.search` → registered
  `web` adapter, completed without fallback.
- Exact Voice tool name, description, `{query}` schema, Responses built-in
  `web_search` request, live freshness, low search context, untrusted-evidence
  instruction and mandatory citation behavior preserved.
- Standalone adaptation resolves the authenticated account's effective encrypted
  shared or individual provider key. No credential enters tool arguments,
  results, logs or memory.
- Tool is registered read-only for the fixed Voice and Background agents and is
  visible in Library → Tools.
- No External AI, social post, recipe, local-event, package-agent or Web-fetch
  feature was admitted.

## Verification

```text
Focused backend: 7 passed
Supported backend suite: 214 passed
Frontend: 9 passed
Frontend production build: passed
Local Vault health: passed
Public edge anonymous rejection: passed
Public authenticated health: passed
Outbound DNS/TLS/provider route: passed
```

The local runtime was rebuilt and restarted at
`https://192.168.1.170:8765`. A newly started Voice session receives the tool
definition because Realtime tool enumeration is fixed at session creation.
