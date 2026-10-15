# C13D — retained history, bounded canonical relearning suppression

Owner authority BP-R03: retain history, suppress relearning. NEW lifecycle guard
over existing canonical memory, not another memory store. Exact reused Vault files
under `/home/christian/Documents/Projects/ReSono-Labs-Vault/`:
`app/vault_runtime/memory/{schema,repository,pipeline,models}.py`; existing confirmed
forget path in `memory/service.py`; existing scoped authority/canonical advisory lock.

Decision CONTINUE: a confirmed repository deletion atomically records scoped
non-content digests of every stored version and canonical identity/source-entry IDs,
then deletes the canonical memory through its existing cascade/epoch mechanism.
All reconciliation checks suppression under the SAME canonical lock before writes.
Same normalized content is rejected even if a reviewer changes the key; paraphrased
replay of the same canonical fact with suppressed original source IDs is rejected.
Private suppression applies to its owner only; workspace-visible suppression applies
to that workspace, never another one. Account/workspace erasure cascades tombstones.
No retained content or secret text in tombstones; transcript history stays intact.

Counterexample: model paraphrases AND changes canonical identity AND cites new
evidence. Deterministic digests cannot establish semantic equivalence. This bounded
guard is not claimed to solve that case; semantic review/rebuild qualification remains
required before full BP-R03 acceptance. No guessed semantic-similarity threshold,
blanket session suppression or irreversible block of all future facts in a domain.
Explicit later reintroduction uses only the existing canonical user-role
`memory.intent.remember` event, scoped to the current user/workspace, cited by the
candidate and captured after the matching suppression timestamp. Ordinary new
transcript text or reviewer-assigned evidence labels cannot override suppression.
No automatic unforget, owner override UI or source-history erasure is added.

Pipeline skips explicitly suppressed candidates and continues other candidates;
unrelated errors still fail normally. Explicit remembered facts are not silently
unsuppressed. Existing confirmation/grants remain mandatory. Idempotent additive
schema setup only; tests use the allowlisted isolated database. Test normalized
replay, renamed key, paraphrase/old evidence, different fact/new evidence, isolation,
all-version suppression, concurrent forget/reconcile and retained transcript.
Internal prebuild review: bounded CONTINUE; full semantic suppression CONDITIONAL.

October8 Chat provenance correction: REUSE the same suppression table/transaction
and already-validated canonical `source_ref_json`. NEW adaptation only in existing
`memory/suppression.py` and its repository call: include original Chat sourceId
in the existing source_entry_ids array under `source-ref:` namespace, both when
forgetting all prior versions and when checking incoming evidence. No copied
content, schema, model, embedding threshold or separate suppression authority.
This closes same-identity paraphrase replay using the same Chat source, NOT
paraphrases with changed identity/new evidence. Test original Chat provenance
survives canonical deletion, old-source paraphrase denied, different-source new
fact allowed, legacy Voice and scope guards unchanged. CONTINUE: original BP-R03;
ignoring nullable transcript IDs would defeat the existing guard for Chat.

## Approved semantic completion — October8

Forgetting is an explicit user action through the existing confirmed deletion
path. This amendment closes the changed-wording/identity/new-evidence gap above
for automatic learning using the SAME factual reviewer and canonical publisher
shared by Chat and Voice. No new agent, memory store, vector tombstone, similarity
threshold, source-history copy or contract document is introduced.

Before publication, resolve forgotten content digests against already-retained
original factual review outputs (including window steps), exact original
transcripts and existing memory tool results. Only exact digest-matched fact text
is supplied to the existing configured reviewer. Never reconstruct missing text
from a digest, send unrelated private history to the model, or add deleted content
to suppression records. Original review/session history retains its existing
lifecycle and account/workspace erasure behavior.

The reviewer compares every candidate with every applicable forgotten fact,
independently of subject/key/domain/type or new source IDs. Repeated assertions,
paraphrases and a combined fact containing the forgotten assertion are suppressed.
Genuinely different facts/new values remain eligible. Unknown, invalid, omitted
comparisons, provider failure, missing original history or exhausted bounds cause
a retryable failure BEFORE any canonical publication; they never authorize replay
or silently mark an unrelated fact permanently suppressed.

The transient qualification binds the user/workspace, candidate meaning/identity
and complete current suppression fingerprint. Recheck under the existing shared
workspace forget fence in the publication transaction. Any concurrent forget
invalidates the qualification and rolls back the whole publication. Durable model
results reuse existing factual analysis checkpoints with source/input/provider/model
bindings; retry does not repeat completed factual analysis. No new job/queue/store.
Confirmed corrections use the same guard before consuming their action, so they
cannot bypass suppression or lose confirmation on failure.

Only the existing original later user memory.intent.remember event or explicit
Chat remember flag can authorize reintroduction. Reviewer labels and ordinary
repeated statements cannot. A subsequent forget renews the suppression timestamp
using actual deletion time and revokes older remember evidence, including on an
existing digest row. Suppression rows still contain only digests, original source
IDs, scope and timestamps.

Explicit bounds: 1024 applicable suppression rows; up to4096 retained rows/16MiB
per existing history owner; eight candidates by eight forgotten facts per call,
100000 input characters and at most128 comparison calls per publication. Missing
or out-of-bounds retained evidence stays retryable; explicit later remember remains
available without reconstructing deleted text. No unlimited-corpus or model-accuracy
claim is made. Mounted provider tests here are synthetic, not real-provider acceptance.

Verification:725 unit checks passed;39 distinct focused PostgreSQL integration
checks passed across suppression, mounted Chat learning, canonical memory and
Voice shared learning/confirmation history. The same-digest second-forget consent
renewal check was extended and passed again. These cover paraphrase/new identity/
new evidence, embedded forgotten assertions, distinct facts, explicit reintroduction,
missing retained meaning, uncertain/invalid/provider-failed comparisons, current
scope/state fences, concurrent forget rollback/retry and correction rollback.
All integration data/providers were isolated/synthetic. Diff whitespace check passed.
