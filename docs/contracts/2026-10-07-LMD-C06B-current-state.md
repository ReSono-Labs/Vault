# C06B/r1 — coherent live validity and scoped Off invalidation

Original R02–05/R18/R25/R28/R31, LC-R01–04 and BP-R01. Bounded child of C06;
not full Chat, semantic relevance, procedural eligibility or production adoption.

## Exact source/reuse

Root /home/christian/Documents/Projects/ReSono-Labs-Vault/. Reuse C13B
MemoryRepository.retrieval_snapshot SQL/DTO/validation, C07A preference get and
local_identity.authority current-session predicate, C03A canonical conversation
headers/segments/turns and C05A VoiceMemStream.invalidate. No new source store,
auth predicate, scheduler, draft buffer, tools/provider or schema.

Extract existing memory batch validation and snapshot cursor body into internal
helpers; public method retains current authorization/transaction behavior.
Extract existing preference read into internal cursor helper, public get unchanged.
ConversationRepository owns NEW context_identity_in_transaction scoped minimal
read of canonical header+segment and optional final turn. Require open header/
segment. Draft returns current history version. Final verifies actual persisted
turn in the same segment/scope, exact input fingerprint, state submitted/running,
and header history_version == submitted_history_version+1. Return pre-submission
history version so an exact draft may rebind to its final without invalidating
it merely because its own immutable input was inserted. A competing newer turn
invalidates it. No reconstruction or fabricated final identity.

NEW live_memory/current_state.py owns immutable CurrentLiveState and injectable
LiveStateLoader. Capture ScopedPrincipalRef + InputIdentity in one short REPEATABLE
READ transaction: existing current-session shared lock, canonical conversation
identity, preference, scoped memory snapshot. No model/work/writes while locked.
Cursor helpers reuse canonical SQL, not independent copies. Loader DB URL owns
the single connection; injected repository instances supply cursor behavior only.
Explicit wrong database configurations cannot cause cross-connection reads.
Fingerprint hashes scope/session, conversation/segment/pre-submit history version,
preference enabled/epoch and memory corpus fingerprint; no text payload.

CurrentStateGuard.is_current(snapshot,prepared) loads current bounded memory IDs,
requires enabled, matching validity fingerprint, complete unchanged canonical
MemoryRecord values and prepared.snapshot==snapshot. Unknown/missing/inactive
memory invalidates; no freshness inference from current_version alone. A required
external_current callback also validates caller-owned context sources and any
procedural/capability/generation evidence. No defaultTrue or complete-context
claim. Guard errors reject preparation; underlying caller falls back normally.
This does NOT judge changed-input relevance or replace ReusePlan/search ports.

NEW live_memory/stream_registry.py tracks existing VoiceMemStream handles by
scope/session/conversation/segment/utterance, event loop and preference epoch.
No text/memory duplication. Explicit positive capacity; duplicate key/full rejects.
Registration/unregistration are loop-owned. Scoped preference-change callback is
thread-safe: remove affected old-epoch handles under lock, schedule invalidate on
their owning loop; never another user/workspace. On/Off epoch change invalidates
old caches; disabled value always invalidates. No kill/cancel-thread illusion;
owners still drain existing stream workers. New registration checks actual
provided CurrentLiveState scope/enabled; caller must capture freshly through guard.

VaultLocalApiApp optional live_memory_invalidator callback after successful POST
commit, before response. No hook on failed/conflicting writes. Production currently
has no registered live streams; later C08/C12 mount must inject registry callback.
CurrentStateGuard independently rejects Off even before loop callback executes.
Callback failure must not reverse committed setting: return503 with safe explicit
live_memory_invalidation_failed and committed enabled/epoch so caller can retry/
reload; normal model remains unaffected. No raw exception/draft logging.

## Allowed files / proof

Existing memory/repository.py, live_memory/preferences.py,
conversation/repository.py, local_api/app.py only; NEW current_state.py and
stream_registry.py. No composition/schema/frontend/dependency/provider/Background
changes. NEW unit/test_live_memory_current_state.py and integration/
test_live_memory_current_state_postgres.py; existing conversation dependency test
may admit only C17A InputIdentity/ScopedPrincipalRef contract import if required.
Documentation permitted. Existing repository contracts remain compatible.

Targeted tests: coherent state with concurrent metadata mutation between reads;
scope/private/final mismatch; same-final rebind and competing submission; Off/ABA,
current session revocation/expiry; missing/changed/deleted memory; no external
guard default; callback-before-response/conflict/failure semantics; real existing
VoiceMem stream pending debounce and blocked underlying worker invalidated through
actual scoped registry, other user's stream untouched, capacity/unregister/drain.
Exact isolated PG fixture only, synthetic callbacks, no paid providers. Re-run
relevant C13B/C07A and live component units once; no repeated broad suite.

Internal review/source freeze precede READY. Removal disables consumer/injection,
invalidates/drains handles; no durable migration/data loss. Full factual search,
relevance, C03C context-source coverage and C14/C15 decision guards remain required
before production mount. No live feature completion from this bounded guard.
