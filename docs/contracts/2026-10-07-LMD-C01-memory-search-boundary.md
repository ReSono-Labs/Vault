# LMD-C01 — replaceable memory-search boundary

HISTORICAL r2, superseded by built r3. Do not build again despite old READY prose.

ID: LMD-C01. Revision: r2. Lifecycle: READY (review identity external to contract).
Phase: next Phase03 only; no code implemented during this contract's preparation.
Inputs: grounding LMD-G-2026-10-04-r11/D24; master LMD-PLANNING-INDEX-r7 plus Decisions amendment r2;
architecture LMD-MODULES-r4; storage LMD-STORAGE-r1 with r11 authority;
exact inputs bound by `docs/planning/2026-10-07-decisions-reviewed-plan.sha256`.
Source baseline hashes: `docs/planning/2026-10-07-decisions-review-source.sha256`.
Review: `docs/reviews/2026-10-07-decisions-plan-and-contract-review.md`.

## Outcome and scope

R01/R06/R31/R33; O2 bounded foundation. Existing memory callers can use a
replaceable read-only backend through the same MemoryService.search contract.
Default search is behavior-compatible, including actual MemoryRetriever ranking,
lexical fallback, limits, scoped arguments and explicit supplied-embedder behavior.
An injected backend can turn interactive vector repair off without suppressing
normal search. This is the minimum foundation for a separate SQL engine; it does
not deliver HNSW, live retrieval, speed improvement or complete-context analysis.

Prerequisites: inspected current MemoryService/MemoryRetriever/repository/callers,
existing Python environment and passing focused baseline. No live DB, OAuth,
retention/promotion/default-setting choice, Node/package install or paid API needed.
Future indexed-query contract requires its own actual isolated-Postgres evidence.
Acceptance owner Christian; implementer future maintainer; one bounded source slice.

## Ownership and paths

Existing owner MemoryService retains credential/embedding resolution, confirmation
and public caller compatibility. New memory_search owns SearchBackend interface and
legacy backend adapter. Existing MemoryRetriever remains unchanged implementation
of current ranking/cosine; no duplicated ranking/authorization/SQL.

Allowed existing runtime edit: `app/vault_runtime/memory/service.py` ONLY:
constructor optional injected backend, default adapter construction, and search
branch delegation/repair-policy check. confirm_action/ensure_vectors behavior and
embeddings_available logic remain unchanged. Do not reformat unrelated code.

Allowed new runtime files:
- `app/vault_runtime/memory_search/__init__.py` (minimal public exports).
- `app/vault_runtime/memory_search/contracts.py` (backend protocol only).
- `app/vault_runtime/memory_search/legacy.py` (MemoryRetriever adapter only).

Allowed new directory: `app/vault_runtime/memory_search/` only.
Allowed test files: `tests/unit/test_memory_search_boundary.py`;
`tests/unit/test_memory_search_boundary_callers.py`. Existing test files must not
be weakened; modify only to fix imports if demonstrably necessary and record it.
No new test directories. Evidence/status edits limited to this contract/review,
PROJECT-STATE, CHANGE-INDEX, CHANGELOG and separate C01 evidence artifact/manifest.

Forbidden: composition routing/flags, new SQL/index/schema/migration/backfill
workers, reviewer/pipeline/tools/grants/repository, API/server/frontend, Background,
Voice transport, live/decision/donor imports, dependencies/config/install, external
requests/data mutation, unrelated owner docs. Do not create the rest of planned
module tree. No `tools` access on read-only backend port.

## Interface to implement

Protocol `MemorySearchBackend`:

```python
repairs_vectors_during_query: bool

def retrieve(
    self, query: str, *, user_id: str, workspace_id: str,
    limit: int, embedder: QueryEmbedder | None,
) -> tuple[RetrievalMatch, ...]: ...
```

Allowed type dependencies: existing QueryEmbedder/RetrievalMatch and MemoryRepository
for legacy adapter. Imports memory_search→memory.retrieval/repository/models;
MemoryService→lightweight contracts/legacy. No search module import of MemoryService,
composition, voice, live_memory, decision_learning, donor or Background executor;
avoid import cycle. No new generic utility/service layer.

`LegacyMemorySearchBackend(memories=repository)` has
repairs_vectors_during_query=True; retrieve delegates existing MemoryRetriever
with passed embedder and returns tuple without re-ranking/relabeling payloads.

MemoryService constructor adds keyword-only
`search_backend: MemorySearchBackend | None = None`. None constructs legacy adapter.
Existing constructor calls need no edits. `search` keeps signature unchanged:
resolve explicit embedder first; when absent and factory present, call ensure_vectors
ONLY if backend.repairs_vectors_during_query; resolve factory with existing lexical
fallback behavior; delegate backend with same authenticated scope/query/limit and
embedder. Explicit supplied embedder still bypasses repair/factory exactly as today.
Backend failure is not silently converted into successful empty result; propagate,
except current embedding-factory failure retains existing no-embedder fallback.
Authorization remains existing backend/repository obligation, not this protocol's
new invention. New backend enabled later must enforce SQL scope independently.

## Material gate and discretion

Question: can this foundation proceed while provider/DB policies remain unresolved?
Authority D24/R01 and actual callers. Alternatives wait for entire system, directly
rewrite existing engine, small compatibility seam. Selected seam allows future
independent query implementation while preserving present user behavior. Falsifier:
custom backend path changes default scope/repair/ranking or bypasses existing
repositories. Dependents indexed-query/final memory ports; result CONTINUE only
for specified boundary. It does not settle any unresolved production choice.

Permitted discretion: naming private fields/test fixtures, minimal docstrings,
ordinary type imports. Revision required for signature/result/model/schema changes,
caller changes outside allowlist, error-policy changes, new dependency or migration.

## Tests that reject plausible wrong implementations

- Real legacy retriever over scoped test repository: identical IDs/order/scores/
  method labels/content version for lexical+exact+semantic overlap to direct
  MemoryRetriever, limits1/8/25 and empty/no-match. Compare to existing behavior,
  not self-generated fake expected ranking.
- Default factory branch: repair called with original scope; factory resolution
  failure still lexical fallback; explicit embedder invokes neither factory nor
  repair; no factory yields no repair. Ensure no new embedding provider requests.
- Inject backend with repairs=False: search still runs once with exact scope/input/
  limit/eligible embedder; ensure_vectors NOT called. With repairs=True, same
  legacy repair rule. Counterexample rejecting this test: skip all retrieval when
  repair disabled, or repair before policy check.
- No implicit scope substitution: fake repository denies inactive membership or
  returns only scoped fixture; service preserves scope and propagates denied
  repository access as existing path does. Test direct legacy parity, not claim
  this mocked policy proves PostgreSQL isolation.
- Existing callers (memory lookup tool and external/plugin adapter service
  interfaces) retain required tuple/match fields/JSON shape. Exercise actual tool
  handler with registered catalog and injected backend; verify default normal
  lookup never depends on future Live Memory setting/package.
- Backend exception propagates; no fabricated semantic vector or score; repeated
  invocation doesn't mutate canonical evidence/records via adapter.
- Structural review of complete diff/new files rejects inline SQL/ranking in
  MemoryService and imports violating direction. Ports alone aren't enough:
  actual default service must delegate to adapter.

Checks during Phase03:

```sh
.venv/bin/python -m pytest -q tests/unit/test_memory_search_boundary.py tests/unit/test_memory_search_boundary_callers.py tests/unit/test_memory_retrieval.py tests/unit/test_memory_contracts.py tests/unit/test_memory_evidence.py tests/unit/test_scoped_tool_catalog.py tests/unit/test_tool_catalog.py tests/unit/test_memory_adapter_package_contract.py

git diff --check
```

Expected all focused cases pass, unchanged old callers/default retrieval outcomes.
Review actual full diff/untracked files against allowlist. This slice changes no
UI/schema/provider: no destructive DB fixture or browser test required. If evidence
shows broader caller changes necessary, return to Phase02 rather than expand paths.

## Stop, rollback, checkpoint and completion

Stop if import cycle, default parity failure, scope change, extra host duty/new
runtime file, unbounded repair policy or missing source/input hash. After two failed
correction attempts on same issue, preserve work/findings and stop per protocol.
Rollback only this slice: restore service constructor/delegation, remove these
unused new module/test files. Never discard pre-existing owner docs/unrelated work.
No DB cleanup/actions replay needed. Save exact implementation SHA manifest and
checks in `docs/reviews/2026-10-07-LMD-C01-build-evidence.md`; record exclusions and
remaining lack of indexed/operating evidence. Mark VERIFIED only after exact
implementation review/checks; CLOSED waits applicable owner/integration acceptance.
Phase03 implements only C01 and stops; next indexed contract written in Phase02.
