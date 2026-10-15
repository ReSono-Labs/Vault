# C07A/r1 internal source/attack review

Same-context review: PASS bounded setting/shared-predicate extraction only.
Actual sources inspected: Voice and Conversation session-scope predicates;
local_identity schema membership unique(workspace,user), account cleanup deleting
memberships; local_api handle/auth/CSRF/no-store server paths; composition schema
and injected owners. Current app/frontend search found no Live Memory preference.
No donor modified. NEW setting justified by BP-R01, not extension settings reuse.

Preserve exact query parameters and Voice unlocked/Conversation shared-lock
semantics. Extract instead of third auth SQL copy. Do not weaken dependency test:
add only the neutral local identity authority module. Typed shared predicate
returns bool; each existing caller retains its own established error type.

Reviewed absent-row CAS race: INSERT ON CONFLICT DO NOTHING RETURNING; loser
raises conflict, never silently writes. Existing row FOR UPDATE serializes update;
expected epoch checked before mutation. Missing defaultOn0 is read-only; first
explicit set persists epoch1. No-op retains current epoch, true ABA increases it.
Foreign-key cascade from membership handles existing logical erasure path.

API injection mounts only setting metadata. Authentic session and cookie/header
CSRF proof reused; extra user/workspace payload rejected. Off is a requirement on
future C06 guard/cancellation wiring, not falsely claimed from this endpoint.
No numerical tuning, provider transport, paid call or final-memory disable added.
Freeze this contract/review/source before runtime edits; no full C07 readiness.
