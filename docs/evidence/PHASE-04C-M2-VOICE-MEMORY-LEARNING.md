# Phase 4C M2 Voice Memory and Learning Evidence

Date: 2026-08-29  
Status: PASS for M2; M3/M4 remain

## Implemented donor chain

- Browser Voice retains its visual presentation and captures only the four
  final transcript event variants proven by the Voice donor; streaming deltas
  do not become duplicate durable evidence.
- Authenticated local event intake binds provider event, Voice session, local
  user, workspace, role, index, payload hash, and transcript.
- Browser close waits for outstanding transcript writes before closing the
  server session and triggering learning.
- Normal UI teardown requests the same close path.
- Voice close invokes the R1 structured reviewer and the existing
  citation-required, fingerprint-idempotent reconciliation pipeline.
- Empty sessions close truthfully with `skipped_empty`.
- An authenticated `/finalize` retry surface preserves R1 recovery behavior
  after a reviewer/provider failure or uncertain client response.
- No Platform Learning, Agent Hub, cloud authentication, or third agent was
  imported.

## Files

- `app/vault_runtime/memory/voice_learning.py`
- `app/vault_runtime/local_api/app.py`
- `app/vault_runtime/composition.py`
- `frontend/src/browser-voice/BrowserVoiceApp.tsx`
- `frontend/src/browser-voice/localApi.ts`
- `tests/integration/test_phase4_local_api_postgres.py`

## PostgreSQL verification

A disposable `pgvector/pgvector:pg16` container bound only to
`127.0.0.1:55436` ran:

```text
VAULT_TEST_DATABASE_URL=postgresql://postgres:<redacted>@127.0.0.1:55436/resono_vault_test \
uv run pytest -q tests/integration/test_phase4_local_api_postgres.py \
tests/integration/test_memory_postgres.py \
tests/integration/test_voice_runtime_postgres.py \
tests/unit/test_openai_memory_reviewer.py
```

Result: `26 passed in 40.22s`.

The dedicated API proof covers final-event acceptance, identical replay,
close-triggered cited learning, one canonical memory, and already-completed
retry. Existing suites cover conflicting replay, session scope, lifecycle,
reconciliation, versions, evidence, retrieval, correction/forget confirmation,
and isolation. The disposable container was removed afterward.

## Frontend verification

- Vitest: `2` files, `6 passed`.
- TypeScript and Vite production build: PASS.

## Limits

This is internal offline/provider-injected evidence. A live owner-credential
review call is not claimed. M3 Background memory-reference/phase-evidence parity
and the M4 full regression/anti-drift exit remain open. Phase 6 screenshot and
Phase 7 license gates are unchanged.

## 2026-08-29 R1 live-session and failure-finalization correction

The exact R1 live text projection from
`/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/android/feature/voice/src/main/java/com/resonolabs/feature/voice/VoicePageView.java`
and `VoiceSessionStateTracker.java` is now present in Browser Voice. User final
transcripts replace the central session detail; assistant transcript delta
events append into that same detail while audio is produced; only final events
become durable transcript evidence.

Review also closed a lifecycle gap: a provider/browser failure after a Vault
Voice session has been created now invokes the same close/finalize path as an
explicit stop. Final event and close requests use browser `keepalive`, while
normal close still waits for all tracked final-event writes before requesting
ingestion. No third agent was created: the existing R1-derived structured
memory-review capability runs through `VoiceMemoryLearning` and the canonical
`MemoryPipeline` after the Voice session ends.

Focused verification:

- frontend: `2` files, `8 passed`; TypeScript/Vite production build passed;
- PostgreSQL API integration: `3 passed`; and
- ingestion test now requires ordered user and assistant final transcript text
  to reach the reviewer before close-triggered reconciliation succeeds.
