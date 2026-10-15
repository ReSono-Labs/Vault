# LMD-C01/r3 — Phase03 build evidence

Date: 2026-10-07. Result: PASS for bounded C01 implementation.
Review: INTERNAL SAME-CONTEXT SELF-REVIEW, not independent or owner acceptance.

## Evidence

Candidate identity: [implementation SHA-256 manifest](2026-10-07-LMD-C01-implementation.sha256).
Six implementation/test files only; excludes this evidence, manifest, contract
lifecycle metadata and project/changelog checkpoints. Frozen planning/source/READY
manifests were verified before runtime edits and remain historical input evidence,
not hashes of the resulting implementation. Planning input manifest also rechecked
after implementation: all OK. Expected source service and contract lifecycle changes
mean the historical source/READY manifest is not a post-build verification target.

Contract: [C01/r3](../contracts/2026-10-07-LMD-C01-memory-search-boundary-r3.md).
Requirements R01/R06/R31/R33, O2 bounded foundation; grounding r11/D24 and module r5.
Environment: Linux, Python 3.13.2, existing `.venv`; branch
`feature/live-memory-decisions`, baseline HEAD
`ea39a6f9da89a2999c4f7e14f686428d2088f480`. No dependency upgrade.

Required focused command:

```sh
.venv/bin/python -m pytest -q tests/unit/test_memory_search_boundary.py tests/unit/test_memory_search_boundary_callers.py tests/unit/test_memory_retrieval.py tests/unit/test_memory_contracts.py tests/unit/test_memory_evidence.py tests/unit/test_scoped_tool_catalog.py tests/unit/test_tool_catalog.py tests/unit/test_memory_adapter_package_contract.py
```

| Check / command | Expected | Actual / exit | Date |
| --- | --- | --- | --- |
| Three frozen build manifests, `sha256sum -c` before editing | All OK | All OK / 0 | 2026-10-07 |
| Required focused command above | Default parity and callers pass | 41 passed, 0.33s / 0 | 2026-10-07 |
| `.venv/bin/python -m pytest -q tests/unit` | Broader regression diagnostic | 310 passed, 4 failed, 13.99s / 1 | 2026-10-07 |
| Baseline-service reproduction below | Determine if broader failures require C01 | Same four failures, 0.88s / 1 | 2026-10-07 |
| `git diff --check` | No whitespace errors | No output / 0 | 2026-10-07 |
| `sha256sum -c docs/planning/2026-10-07-decisions-build-inputs.sha256` | Planning unchanged | All OK / 0 | 2026-10-07 |
| Full tracked service diff and all five new files, imports, status/allowlist | No expanded duties or unauthorized runtime paths | PASS | 2026-10-07 |

Initial focused run: 40 passed, one test fixture failed because actual
`register_memory_tools` is keyword-only. Corrected the new test invocation to
`catalog=catalog`; no existing code/test weakened. One correction then passing run.

Broader failures: mail tool audience in `test_builtin_capability_boundary`, existing
DocumentsPanel marker in `test_frontend_negative_inventory`, missing migration
workspace source in `test_mcp_package_migration`, existing workspace_files markers
in `test_runtime_negative_inventory`. All affected implementation/test files are
unchanged by C01. Reproduction loads HEAD MemoryService into its module in-process;
it does not overwrite working files, and is not a clean-checkout full-suite claim:

```sh
.venv/bin/python -c 'import subprocess; import app.vault_runtime.memory.service as service; import pytest; source = subprocess.check_output(["git", "show", "HEAD:app/vault_runtime/memory/service.py"], text=True); exec(compile(source, service.__file__, "exec"), service.__dict__); raise SystemExit(pytest.main(["-q", "tests/unit/test_builtin_capability_boundary.py::test_mail_tools_are_capabilities_of_only_the_fixed_voice_agent", "tests/unit/test_frontend_negative_inventory.py::test_browser_voice_runtime_has_no_cloud_or_non_system_agent_surface", "tests/unit/test_mcp_package_migration.py::test_mcp_package_migration_conflict_requires_confirmation", "tests/unit/test_runtime_negative_inventory.py::test_runtime_source_contains_no_prohibited_agent_registration_or_cloud_authority"]))'
```

## Actual structural and functional review

Material gate executed: preserve existing scoped retrieval/ranking or replace it
now? Authority C01/r3, D24 and actual service/tool/external/plugin owners.
Alternatives: inline a new engine, alter callers, or delegate existing engine behind
the optional protocol. Selected delegation; functional falsifier is changed ranking,
scope, payload, repair/failure behavior or duplicated policy. Tests compare real
MemoryRetriever and default service over scoped fixtures including exact/lexical/
semantic overlap, versions and limits 1/8/25, empty/no-match, denied membership.
Result CONTINUE/PASS only for replaceability foundation, not indexed/live search.

MemoryService owns embedding resolution and existing repair; backend flag gates
automatic repair only. Explicit embedder bypasses repair/factory; factory failure
retains lexical fallback; backend failure propagates. Default adapter delegates
unchanged retriever, returns its matches as a tuple, adds no ranking/SQL/writes.
Repeated read-only fixture invocation leaves records unchanged. RepairsFalse still
runs retrieval with original arguments. Actual registered memory_lookup and actual
external/plugin search handlers preserve JSON/tuple fields with injected backend.
Plugin authorization is a scoped fixture, not a new cryptographic authorization test.

Dependencies: service to lightweight backend contracts/adapter; adapter to existing
retriever/repository. No reverse MemoryService import, provider/Live/Decisions/tool
execution/storage/permission duties in backend. Existing search callers and public
search signature unchanged. No host composition edits. Only allowed existing runtime
file changed; three allowed new module files and two new test files. No deleted or
renamed source files. Existing owner documentation work preserved.

Unperformed: actual PostgreSQL/HNSW, provider requests, browser UI, live drafts,
conversation capture, session review/learning, historical audit, deployment. Mocked
scope tests do not establish database isolation. Full suite remains non-green.

## Current state

C01/r3 VERIFIED, not CLOSED. Runtime/test candidate frozen in separate manifest.
No schema/DB/provider/dependency/config/production or history changes. No commit.
Current owner work remains dirty and preserved; this slice must not be blanket-reset.
Rollback is limited to service delegation and unused new backend/test files.

Next authorized route: Phase03 C03A/r1 only, after restart and verification of its
frozen sources plus this C01 checkpoint. Stop after C01 in this phase. No requirement
to adopt GPT-Live or install a Decisions framework. The later live-provider adapter
contract owns SDK compatibility and API calls; neither is implemented here.
