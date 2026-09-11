# R1 Voice Prompt and Tool Correction Evidence

Status: IMPLEMENTED; BACKGROUND HANDOFF OPEN  
Date: 2026-08-29

## Boundary

This correction ports current R1 session behavior into the existing standalone
Voice/Vault runtime. It adds no agent identity and no excluded feature family.
Donor projects were read only. The source trace is
`docs/research/2026-08-29-R1-VOICE-SESSION-PROMPT-TOOL-TRACE.md`.

## Implemented

- Scoped memory and prior-summary startup context.
- Primary Voice and canonical tool guidance.
- Installed Skill disclosure and `load_agent_skill`.
- Durable scoped MCP projection restoration.
- Browser/provider/local-runtime function-call round trip with serialized calls.
- Exact-once invocation ledger and bounded/redacted tool evidence remain active.
- Memory lookup, explain, explicit remember, correction, forget and later-confirm tools.
- R1 Realtime PCM/noise/transcription/VAD and automatic tool selection settings.
- Existing complete user/assistant transcript and close-triggered memory finalization.

## Verification

```text
python3 -m py_compile app/vault_runtime/**/*.py
142 backend unit tests passed
13 Voice runtime/local API PostgreSQL integration tests passed
8 Browser Voice tests passed
TypeScript compile and Vite production build passed
```

The LAN configuration regression now asserts the accepted rule: a non-loopback
bind without a TLS certificate is rejected with the TLS-specific error.

## Open item

Voice-to-Background goal intake is not completed or claimed here. It may target
only the existing fixed Background Agent and must pass a separate anti-drift
review before implementation evidence can be recorded.
