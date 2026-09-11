# Phase 3 Voice/R1 Memory Merge Evidence

Date: 2026-08-29  
Status: PASS

## Implemented donor behavior

- Voice-shaped PostgreSQL storage under `vault_private` for transcripts,
  summaries, canonical memories, immutable versions, evidence, ingestion,
  pending actions and real-provider embeddings.
- Exact R1 reviewer contract v2 domains, types, authorities, intents,
  confidence and sensitivity labels.
- Local `private` and `workspace` visibility adaptation backed by Phase 2 users,
  memberships and revocation.
- Canonical reconciliation with PostgreSQL transaction advisory locking,
  create/confirm/correct/conflict state, versions and attributable evidence.
- Fingerprinted transcript ingestion and completed-state idempotency.
- Citation-required session finalization and summary persistence without an
  embedding provider.
- R1 recursive tool-evidence secret redaction and 16 KiB bound.
- Prepared, same-session, later-user-entry confirmation for correction and
  forgetting; pending actions are single-use.
- Lexical/exact retrieval plus optional real-provider semantic ranking and
  clean provider-failure fallback.
- Stale embeddings are removed whenever canonical content changes.

No memory/reviewer agent was added. `MemoryReviewer` is only a capability
protocol used by the fixed Voice/Background Agent execution boundary in later
wiring.

## PostgreSQL and regression proof

A disposable loopback-only `postgres:16-alpine` instance ran the complete
suite with `VAULT_TEST_DATABASE_URL` set:

```text
70 passed in 38.80s
```

The Phase 3 tests prove:

- eight-relation schema creation and schema fingerprint;
- unknown classification rejection;
- transcript and ingestion idempotency;
- create/correct versions with evidence;
- summary persistence and completed pipeline replay;
- sensitive memory exclusion from automatic profiles;
- lexical, exact and explicitly supplied semantic test-provider ranking;
- provider failure lexical fallback;
- content-change embedding invalidation;
- real later user-transcript confirmation and action single use;
- correction and deletion outcomes;
- workspace-memory access, one shared canonical record, member-attributed
  correction and immediate revocation denial;
- private memory isolation and cross-object probing denial across all four
  supported local users.

## Donor integrity

Voice admitted donor hashes remained exactly those recorded in
`docs/research/PHASE-03-VOICE-R1-MEMORY-INVENTORY.md`. Voice commit and tracked
diff fingerprint remained:

```text
commit 0f3b34223f745920e79d1d9db301f3b639d08393
tracked diff 0d9a4ce77e3707940c4f3becc5ecbfb641eb50f4df975c7e971f52e14e6942da
```

R1 admitted donor hashes also remained exact. R1 commit and tracked diff
fingerprint remained:

```text
commit 91d9e70bbe156f03c79399a458416f0bebd20210
tracked diff 90f9c55912d93683e5e3dea53688b6190c2685c6437259d418520fc6be7551ff
```

Both donors were already materially dirty and continued receiving unrelated
untracked/external work during this build, so their whole-status fingerprints
changed. No admitted file hash or tracked-diff fingerprint changed, and this
project performed no donor write, reset or cleanup.

## Scope exclusions preserved

- no Build Agent or additional agent identity;
- no hosted authentication or cloud synchronization;
- no Link/Tailscale routing;
- no document/file storage;
- no shared Hermes/OpenClaw/external consumer API;
- no fabricated hash/random semantic vectors;
- no new memory labels or product behavior.

The disposable PostgreSQL container was stopped and removed after proof.
