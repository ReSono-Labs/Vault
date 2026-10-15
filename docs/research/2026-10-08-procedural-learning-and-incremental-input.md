# Research application — procedural learning and changing input

Inspected online 2026-10-07/08 at owner request. Evidence, not replacement grounding
or additional product scope. Original grounding and current contract register remain
authoritative; papers do not certify Vault's implementation or predict its latency.

- [Agent Workflow Memory](https://arxiv.org/abs/2409.07429): reusable descriptions
  and parameterized steps induced from experiences. Apply to small scoped procedures,
  not hard-coded customer-specific tool calls. Successful trajectory evaluation is
  a prerequisite in its online workflow induction; irrelevant recalled workflows
  remain a possible failure mode.
- [ExpeL](https://arxiv.org/abs/2308.10144): contrasts successful and failed
  experiences and updates an existing insight collection. Supports revising existing
  rules and retaining negative evidence rather than duplicate-rule accumulation.
  Its learning approach need not update model weights.
- [Incremental dialogue](https://aclanthology.org/W14-4314/): distinguishes simulated
  and committed dialogue context, including typed input and validation. Supports
  transient revision preparation followed by final validation; does not require a
  second persistent conversation store or authorize speculative external actions.
- [ToolSandbox](https://arxiv.org/abs/2408.04682): intermediate/final milestones and
  forbidden events expose wrong arguments, state dependencies and missing-information
  failures that tool-name matching misses. Apply a small set of relevant counterexample
  tests, not the entire benchmark or a new evaluation framework.
- [Reflexion](https://arxiv.org/abs/2303.11366): separates action, evaluation and
  reflection; evaluation may use task checks, heuristics or models. Model reflection
  is not independent proof of success or evidence of user satisfaction.
- [Decisions documentation](https://developers.openai.com/api/docs/guides/decisions):
  choice questions select among supplied options; custom structured review belongs
  to the normal model path. Candidate choices can be assembled per request. This
  is an API, not a downloadable procedural-learning framework.

Application: existing shared VoiceMem revision owner, parallel canonical recall and
procedure preparation, final execution gate, separate post-session structured review,
authoritative relational definitions plus indexed examples. Model proposes/evaluates;
code enforces scope, source freshness, capability/grants and publication constraints.
Unknown capture/outcome/feedback stays unknown; a non-error tool response proves
neither request resolution nor satisfaction. Missing original reasoning stays absent.

Code evidence: C14G Voice projection currently unknown; C14H Chat projection links
actual finalized turn IDs, original calls, prior context, summaries and final answers,
but an open conversation is not a qualified closed session. C14D learning/C14E
activation/C15B retrieval are existing reusable components, not permission to bypass
their source gates. Complete qualification/publication/active consumer remain work.
