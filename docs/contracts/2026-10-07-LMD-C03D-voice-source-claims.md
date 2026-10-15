# C03D/r1 — preserve existing Voice invocation source claim

Existing authenticated Voice API already passes user_utterance and its canonical
transcript index into ToolInvocationContext; LocalToolAuthority.prepare_voice_invocation
does not persist those fields. NEW adaptation of these exact existing Vault
voice/tools.py/schema.py sources, no new source ledger/payload/model/permission.
Persist only observed canonical index and text fingerprint when an actual scoped
role=user transcript at that index already matches normalized provided text.
Missing, racing, malformed or mismatching source remains NULL; do not block tools
or infer context from timestamps. Label the linkage **client_claim**, not original
model causality, user acceptance or provider-confirmed finality. The first durable
claim is immutable; replay does not overwrite it using later utterances.

Add nullable source_utterance_index/fingerprint to existing invocation relation,
paired constraints. No FK to memory transcript (Voice schema can install without
memory tables); read-time source qualification must rejoin authorized source and
revalidate hash, never treat a stored claim as current after source deletion.
No raw user text duplicated. Existing user/scope/session ownership and grant,
claim/result/replay/recovery behavior unchanged. Query only if a well-formed claim
was supplied; missing optional memory relation leaves truthful NULL. Normal
composition already initializes memory before Voice, independently checked.

Internal prebuild review CONTINUE bounded actual producer metadata. Tests existing
Voice public runtime captures current matching user row, source text/index mismatch
or absent gives NULL, source replay cannot introduce hindsight, non-user/foreign
source cannot link; existing tool execution states and cached replay preserved.
Actual isolated PG only, no provider or historical user data. This does not claim
complete session capture, causal proof, summary availability or automatic learning.
