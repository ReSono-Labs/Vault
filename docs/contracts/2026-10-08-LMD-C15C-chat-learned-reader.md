# C15C — active learned candidates in the existing Chat preparation path

REUSE `ActiveDecisionQueries`, `ChatPreparationRuntime`, the existing shared
VoiceMem/ParallelPreparation lifecycle, Decisions selector, scoped embedder,
current-state guard and final handoff. No second draft owner, recall loop, timer,
tool dispatch or learning producer. NEW joining code in the existing Chat host.

Internal prebuild review CONTINUE: on the existing decision branch, check for an
active catalog before paying for a query embedding. Embed the same bounded trusted
draft/history context used by recall, retrieve indexed examples (20/5), validate
authoritative conditions/required slots/exclusions/current sources/grants, and
offer those finite candidates to the existing selector. If no valid learned
candidates/provider, preserve catalog proposal/normal model fallback. The selector
must receive full applicability constraints, not merely a workflow title.

Cache only the revision-bound candidate identities, query vector and active
generation/epoch/capability fingerprint in the existing ephemeral stream entry.
Every publication/final reuse rechecks the active reader/current source; stale
revision, erase/forget, pointer switch or grant change drops the preparation.
This conservative qualification can be expensive: benchmark/optimize separately,
never replace it with a permissive gate. No new model/embedding call during status
or final validation. UI labels learned rules distinctly from catalog proposals.
Final model still verifies meaning/slots and invokes ordinary authorized tools;
provisional selection grants no execution authority and never becomes successful
learning evidence. Existing tracing/revision disposal is unchanged.

Proof: actual mounted Chat synthetic embedding/Decisions transport with learned
active pgvector rule, pre-Send preview, deletion/edit invalidation, scoped Off and
current grant denial. Existing Chat/memory live tests cover shared lifecycle.

Measured correction: first mounted run timed out before provider selection because
qualification evaluated availability for the entire unrelated tool catalog several
times. Reuse metadata for historical schema comparison; capability capture obtains
only explicit capability IDs referenced by scoped building/active definitions, and
still evaluates current availability/grants for each referenced tool. Add an
optional frozen-definition input to the existing capability adapter. This removes
unrelated provider checks, not current rule/source/grant validation or deadlines.

Same-revision memory-dependent reconsideration reuses the ephemeral query vector,
but not a stale selection/source gate. Existing safe selector diagnostics add
candidate kind/count and hashed generation/capability snapshot IDs for debugging;
no prompts, raw IDs, vectors or draft text enter logs or the training source.

UI uses a presentation-only formatter for learned applicability JSON: title,
conditions, required slots and exclusions remain escaped React text in the existing
bounded/wrapping preparation panel. Malformed/future descriptions remain escaped
plain text. No new state owner, layout, mic, timer or model call. Two focused render
checks cover readable constraints, safe markup and fallback representation.
