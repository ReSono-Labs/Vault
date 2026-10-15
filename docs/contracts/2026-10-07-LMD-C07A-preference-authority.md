# C07A/r1 — persisted Live Memory setting and shared session authority

Original R18/R25/R28/R31, LC-R01–04 and BP-R01 control. Bounded child of C07;
register owns lifecycle. C13B supplies actual memory freshness, not session or
preference validation. No duplicate auth/settings registry is authorized.

## Actual source/reuse and exact delta

Absolute source root /home/christian/Documents/Projects/ReSono-Labs-Vault/.
voice/repository.py _require_authority and conversation/repository.py
_require_authority currently repeat the same session/user/workspace/membership
predicate. Extract that query literally into local_identity/authority.py
has_current_session_scope(cursor, user_id, workspace_id, local_session_id,
lock=False). Existing Voice wrapper retains no-lock behavior and own error;
conversation wrapper retains shared locks and own error. New consumers use this
one predicate with shared locks, not another SQL copy or fake Voice session.

Scoped Live Memory preference does not exist in current app/frontend search;
extension settings are per extension, not this user/workspace preference.
NEW live_memory/preference_schema.py creates vault_live_memory_preferences:
user_id/workspace_id composite primary key; enabled boolean default true;
epoch bigint positive default1; composite membership FK(workspace_id,user_id)
ON DELETE CASCADE. No drafts, tools or facts. Existing account cleanup deletes
memberships, so FK handles tombstones without a redundant optional delete hook.
Repeated ensure never resets rows. Missing row reads enabled=true, epoch=0;
absence is the scoped persisted-default policy, not a GET write.

NEW preferences.py owns immutable LiveMemoryPreference and injectable repository
with ensure_schema/get/set. Current authenticated session-scope guard held through
transaction; no caller-selected user/workspace API fields. Strict bool enabled
and nonnegative exact-int expected_epoch. Compare-and-swap first insertion at0;
existing update locks row, compares epoch, increments only when value changes.
Conflict raises typed error rather than silently overwrite another window.
On/Off/On ABA changes epoch; same-value retry with current epoch is idempotent.

VaultLocalApiApp optional injected live_memory_preferences. GET /live-memory
returns enabled/epoch; POST accepts exactly enabled/expectedEpoch, calls existing
authenticate/_csrf_token/require_csrf and repository. No arbitrary scope fields;
unsupported method404, missing module503, stale epoch409, invalid400, auth errors
existing401/403 mapping, no-store responses. Existing cookie SameSite/CSRF and
server body/security protections reused, not new origin/CORS engine.
composition.py initializes/injects this repository after local identity schema.
It mounts only the setting endpoint, not drafts/retrieval/learning/provider work.

## Boundary and proof

Allowed runtime files: NEW local_identity/authority.py, live_memory/preferences.py,
live_memory/preference_schema.py; existing voice/repository.py,
conversation/repository.py, local_api/app.py, composition.py. No other runtime,
dependency/frontend/config/provider/Background changes. New tests/unit/
test_live_memory_preferences.py and integration/test_live_memory_preferences_postgres.py;
existing test_conversation_identity.py may add only neutral authority dependency
to its existing module allowlist. Documentation allowed.

Targeted proofs: strict input validation before connection; extracted query retains
expiry/current-workspace/revocation and exact lock semantics/error types; initialOn,
per-user/workspace isolation, restart/repeated ensure, CAS concurrent first writes,
no-op/ABA epochs, switch/logout/expiry/revocation, membership/account deletion;
actual local API authentication/CSRF, extra scope fields denied, conflict mapping,
module absent/no-store. Reuse exact gated test DB fixture. Existing conversation
and Voice authority consumers run once, no paid providers/broad suites.

Counterexamples: global Off; stale session changes active-workspace setting;
GET mutates data; concurrent windows lose update; repeat ensure resets epoch;
helper drops Voice expiry or conversation shared locks; logical user tombstone
retains preference; Off disables ordinary final memory/review.

C06 must consume preference epochs in every publication/final guard and invalidate
actual queued work on Off; it is NOT implemented by this setting alone. No live
registry exists yet, so no ineffective cancellation hook is invented here. UI
toggle remains C09 integration. Removing injection yields unavailable endpoint;
retained preference rows contain no source data and must not be reset while
consumers run. Internal review/frozen source precede READY and runtime edits.
