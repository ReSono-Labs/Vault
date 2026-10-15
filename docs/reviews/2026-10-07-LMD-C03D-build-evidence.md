# C03D/r1 — existing Voice producer source-claim capture

Actual source/reuse review established API/browser already passes utterance text
and canonical index. Existing LocalToolAuthority.prepare_voice_invocation now
stores nullable canonical source index/fingerprint on that existing invocation,
only when an authorized scope/session user transcript matches. No copied text,
new ledger, model, grant or invocation engine. Additive nullable paired columns;
credential-only Voice schema remains installable without memory relations.

The claim is authenticated-client linkage, **not** original model causality,
provider finality or accepted outcome. Missing/racing/mismatching/non-user/malformed
source produces NULL and does not block ordinary tools. Existing immutable
invocation retry never overwrites initial provenance with later user context.
Consumers must rejoin scoped source/hash at review/publication; deletion cannot
make a stale reference authoritative merely because a hash remains.

Executed tests: **23 actual isolated PostgreSQL passes in 49.84 seconds** across
new source producer, existing Voice runtime and provider credential modules;
**22 focused units in 0.50 seconds** for schema and atomic capture compatibility.
New test uses actual VoiceToolRuntime/catalog/grant/claim/result path, checks exact
match, cached replay/no second execution, hindsight prevention and null cases.
No paid provider, private user session or test DB outside exact harness. New fixture
also independently rejects non-allowlisted targets before reused reset fixture.
`git diff --check` passed. Historical source audit/Voice manifests are preserved;
new producer/schema hashes explicitly supersede those affected source snapshots.

Remaining C03C: original model/provider causal IDs, readable summaries, denied/
browser-local tool attempt coverage, durable producer acknowledgments and qualified
complete source projection. Existing memory analysis/capture not rebuilt. No
automatic procedural learning or complete-session assertion from these columns.
