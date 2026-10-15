# Feature 07 — procedural learning and standalone Decisions selector

Validation date: 2026-10-07. decision-learning-plan r4 and decisions-selector-plan r3 were read completely, including their exact storage and C17A/C17B split sections. This validates local code, not current provider access or production history.

Verdict: C17A's offline finite mapping/parser/no-op/validity boundary IS implemented. Learned procedural storage/reviewer, semantic candidate retrieval, capability resolution, activated routing and the live Decisions transport ARE NOT implemented. Existing factual memory type `decision` is not a procedural decision tree.

| Planned obligation | Actual evidence | Disposition |
|---|---|---|
| Provider-neutral immutable request/candidate mapping | decision_routing/contracts.py | Implemented C17A; consume its actual types, do not redefine |
| Finite choice projection, reserved fallback and validated answer/probabilities | decision_routing/selector.py | Implemented offline C17A |
| Cancel/deadline/current-token checks and no-op fallback | Same selector plus boundary tests | Implemented with caller-supplied validity; no live controller wiring |
| Dynamic scoped examples → collapse → authoritative version → structural eligibility | No decision definitions/examples repository or SQL retrieval caller | Not implemented; do not send whole catalog or invent global seven-route taxonomy |
| Real dimension-compatible SQL HNSW example retrieval | No decision example schema/index/query | Not implemented; authoritative definitions remain relational/JSONB, embeddings find candidates |
| Immutable generations/definitions/versions and source-linked observed/synthetic/counterexamples | No decision_learning package or vault_decision_* schema in app | Not implemented |
| Independent leased procedural review and idempotent proposal publication | No reviewer/job/caller | Not implemented; factual pipeline must stay independent |
| Reconstruct available-at-decision evidence separately from eventual outcome | No linked procedural evidence consumer | Not implemented; timestamps and eventual success cannot establish original rationale |
| Separate preparation, execution, tool report, request resolution and usefulness | Legacy raw results exist; succeeded can coexist with isError | New qualified projection/reviewer absent |
| Deduplicate replay/retries, semantic function and evidence identity | No procedural deduplication implementation | Not implemented; similar invoice/balance wording is not equivalent behavior |
| Publish inactive proposals initially; promotion separately authorized | No procedural publisher or activation endpoint | Not implemented; absence is not permission to auto-activate |
| Capability ID → current provider/schema/effect mapping | Existing ToolCatalog has tool identities and authority; no reviewed semantic CapabilityResolver | New mapping absent; reuse catalog/grants, do not infer interchangeable tools |
| Current slots, conditions, exclusions, capability and grant checks | Existing tool execution authority exists, not learned-route eligibility | Extend routing; never create a learned permission engine |
| Calibrated routing confidence distinct from similarity/provider probabilities | Pure selector returns observations; no calibrated activation policy | Not implemented/reserved; counts alone not calibrated success |
| Atomic scoped active pointer, concurrent rebuild, retirement and rollback | No generation/activation schema or runtime | Not implemented; preserve evidence and canonical memory when deleting derived generations |
| Source deletion/forget suppression invalidates examples and pending work | No procedural cleanup/epochs | Not implemented; historical replay policy unresolved |
| Context-aware parallel retrieval and final revalidation | No mounted live_memory/controller/candidate repository | Not implemented; C17A callback is a seam, not integrated behavior |
| Standalone Decisions SDK/client/account access and optional composition | No openai_decisions.py or production selector mount | C17B absent. API documentation existence is not installed transport/access proof |
| Provider token budget, deadlines, no hidden retry, protected credentials | Offline limits and fake transport exist; no live transport | Real adapter proof still required; no GPT-Live work |
| Historical read-only qualification and redacted coverage report | No authorized history inspection/report completed | Not performed; cannot claim old histories contain missing reasoning/call linkage |
| Wrong-route, hindsight, unnecessary success, unknown-effect and erased-source reviewer tests | Boundary parser tests only; no procedural reviewer fixtures | Not implemented |

Executed boundary/strict-JSON tests in this audit: **112 passed**. They prove the offline boundary, not retrieval, learning, provider access or execution. No SDK download/upgrade, paid call, private data read or active rule was created.

No duplication: reuse C17A contracts/parser, current ToolCatalog/LocalToolAuthority, C03A identity, canonical memory learning and existing source ledgers. C17B must add transport, not another selector framework. C14/C15 remain new procedural behavior, not replacement factual memory.
