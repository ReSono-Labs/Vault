# C13B/r1 — canonical retrieval epochs and scoped state loader

Candidate; register owns lifecycle. Original R02–07/R18/R28/R31/R33 and LC-R01–02;
storage plan already proposes record retrieval_epoch. Full-build direction does
not authorize duplicate stores or unsafe cache reuse. Tests are targeted per owner.

## Actual necessity and chosen mechanism

Absolute Vault root /home/christian/Documents/Projects/ReSono-Labs-Vault/:
memory/repository.py reconcile_memory can update confidence/source_authority and
updated_at without incrementing current_version. memory/schema.py has no epoch.
live_memory contracts depend on an injected validity guard, not a real loader.
MemoryRecord/MemoryRetriever must remain unchanged for existing consumers.

Add retrieval_epoch bigint positive/default1 at the END of existing records.
Owned BEFORE INSERT/UPDATE trigger initializes/increments it for any change to
returned canonical record fields, including recency timestamps. Explicit epoch
overwrites cannot reset it. Existing version indexes/DTO shape remain identical.

Per-record checks alone miss a newly inserted memory, including an empty previous
result. Alternatives: re-search always, hash entire corpus, or scoped counters.
Select small vault_memory_scope_epochs table (workspace_id, nullable user_id,
retrieval_epoch positive; UNIQUE NULLS NOT DISTINCT; parent FKs CASCADE). NULL is
shared workspace corpus, user_id is only that user's private corpus. Actual package
and isolated test target PG16, supporting this uniqueness. No facts/text/vectors
or new memory authority in this table. Separate scopes prevent another user's
private updates invalidating/revealing their activity to this user's context.

Owned AFTER record trigger bumps affected old/new corpus keys once each; unchanged
records do not bump. Delete advances the old scope; visibility/scope moves advance
both. Same transaction as canonical write/rollback. Parent existence/deletion
guards avoid reinsert after FK cascade; account logical tombstone cleanup explicitly
erases private counter rows after memories via existing optional erasure hook.
Seed scope rows from workspaces/memberships only, no memory scan or provider/backfill.
Initialize shared workspace scope on first canonical insert too; this prevents a
later visibility transition needing a new FK lock while holding an old record lock.

NEW immutable MemoryRetrievalState and MemoryRetrievalSnapshot DTOs wrap unchanged
MemoryRecord with epoch, scope IDs and shared/private counters. Fingerprint hashes
only contract/scope/counters, not raw content. Canonical repository method
retrieval_snapshot(user_id, workspace_id, memory_ids=()) requires existing membership
guard with shared authority locks, reuses _scope_sql. Single SQL statement reads
scope counters and requested active record snapshots coherently. Input batch max
25, reusing existing retrieval limit; reject malformed/duplicate IDs. No entire
corpus, vector JSON, embeddings, model or writes during read. Missing/inactive/
wrong/private records absent; denied authority raises existing authorization error.

## Exact build boundary / downstream limits

Only memory/schema.py, models.py, repository.py and local_identity/repository.py
optional epoch erasure row. NEW tests/unit/test_memory_retrieval_state.py and
tests/integration/test_memory_retrieval_state_postgres.py. Documentation allowed.
No service/composition, search/ranking/provider, live interfaces, conversation
identity/auth, UI/setting or procedural schema changes. No installed DB access.
No second current-session predicate: this loader is memory membership authority,
NOT final session/preference/capability/generation validation (C06 remains).
No adoption/retention/activation choices invented. Metadata counters do not replace
semantic relevance; changed meaning still requires actual relevance/retrieval.

## Internal attack review required before READY/build

Counterexamples: confirmation metadata changes at same version; empty result then
new fact; private other-user fact changes shared counter; correction/delete/ABA;
scope move; concurrent increments lost; rollback increments committed; account
tombstone leaves counters; cascade trigger resurrects deleted parent; epoch reset;
migration shifts SELECT * indexes or repeats resetting live counters.
Single canonical trigger path covers raw DB writes too, not just reconcile_memory.
Keep triggers invoker, fully qualified table references/fixed search_path.

Targeted real PostgreSQL: additive old-record migration preserving IDs/versions/
evidence/vector fingerprints, repeated ensure_schema, changed/no-change/explicit
epoch reset, metadata confirmation, empty/add/delete, scope/private/shared/isolation,
rollback, concurrent scope increments, revocation, erasure and workspace cascades.
Use existing exact isolated fixture/global safety gate; no paid providers. Run
new state tests plus relevant vector-write/memory regressions once, no full suite.
Freeze candidate/source; same-context internal review is not owner acceptance.
Rollback disables consumers, leaves additive metadata; never reset counters while
prepared caches are active. Full C13 maintenance/C06 mounts remain separate.
