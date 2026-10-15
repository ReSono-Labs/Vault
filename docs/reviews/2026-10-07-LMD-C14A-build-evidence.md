# C14A/r1 — shared-model procedural reviewer evidence

Owner requested reuse of the same model or code logic with parallel-or-after
execution. The bounded C14A contract was written and internally reviewed before
source edits. Sequential independent calls selected initially; no replacement of
existing memory capture/analysis, new system-agent identity or provider SDK upgrade.

## Implemented

- Existing OpenAIMemoryReviewer.review delegates to new review_structured with
  its unchanged prompt/schema/input bound and original memory parser. The method
  owns the existing selected-provider/background_access model resolution, scoped
  credentials, reasoning, SDK executor and OAuth/base URL behavior. Existing
  Gemini request helper accepts optional prompt/schema; no parallel HTTP client.
- decision_learning/reviewer.py owns a distinct procedural prompt, strict frozen
  source/observation/capability/definition DTOs and typed proposals. It validates
  coverage, linkage, references, target definitions and attributed non-error
  resolved outcomes. Draft source types and silent input/output truncation are
  rejected. Synthetic examples do not represent observed success counters.
- decision_learning/finalization.py owns sequential callback execution with
  separate memory/decision completed/failed/disabled results. Both configured
  callbacks are attempted even when the first fails. Original exception strings
  never enter the returned status. It is not a durable worker/retry mechanism.

The same runner object is exercised for memory and Decisions in tests: same
configured model/credentials/executor, different names/prompts/output schemas.
The configured model is resolved normally for each call; there is no guarantee
of identical model if an owner changes selection between calls.

## Executed targeted tests

`tests/unit/test_decision_learning_reviewer.py` plus existing
`tests/unit/test_openai_memory_reviewer.py`: **23 passed in 0.81 seconds**.
Initial run exposed a set-versus-dict subset comparison bug in proposal reference
validation; corrected to dict.keys, then all targeted tests passed. Tests include
forged citations/capabilities/targets, duplicate IDs/extra fields, unknown effects,
denied/error/truncated/corrected outcomes, insufficient-evidence output, incomplete
coverage, drafts, input/output overflow, wrong contract, provider failure,
independent failure ordering, disabled branch and Gemini schema/prompt reuse.
`git diff --check` passed. Synthetic executors/HTTP response only; no private DB,
provider credentials or paid calls. No broad suite rerun.

## Explicit limitations / next build

This reviewer and coordinator are **unmounted**. There is no trusted production
source loader for this DTO yet, no durable procedural review job, rules/examples
repository, publication/activation, suppression gate, vector embeddings/HNSW or
production after-session hook. Existing memory finalization is unchanged. These
remain full C14/C03C/C15 work, not silently supplied by callbacks or booleans.

Complete coverage is an explicit input claim that the production source adapter
must prove; this module validates structure, not causal truth or semantic quality.
The conservative initial gate only accepts attributed successful handling as
changing proposals; broader correction-driven revision and direct-answer
procedures require the subsequent reviewed learner/publisher contract. No output
is automatically an executable rule or a grant. Source freshness/erasure and
forgotten-fact suppression must be rechecked at durable publication.

Official OpenAI documentation was fetched using OpenAI Docs skill before provider
implementation: https://developers.openai.com/api/docs/guides/structured-outputs .
It supports typed output schemas and requires handling invalid/incomplete output;
it does not prove procedural truth. Implementation uses the existing runner,
not another provider framework. Removing decision_learning leaves memory review
with its unchanged existing call contract.
