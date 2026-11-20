"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations

import importlib.util

from app.vault_runtime.background_agent.contracts import BackgroundRunRequest


def modules():
    names = ["coordination_contracts", "coordination_repository"]
    result = []
    for name in names:
        path = f"app.vault_runtime.background_agent.{name}"
        assert importlib.util.find_spec(path) is not None, f"Missing coordination component: {name}"
        result.append(importlib.import_module(path))
    return result


def prepare(context, run_id="run-1"):
    module, repository = modules()
    url, owner, _other, _runs = context
    repo = repository.CoordinationRepository(database_url=url)
    repo.ensure_schema()
    scope = module.OwnerScope(owner.user_id, owner.workspace_id)
    request = BackgroundRunRequest(
        run_id=run_id, objective="Prepare a brief", instruction_profile="default",
        success_criteria=("Brief checked",), result_schema={"type": "object"},
        original_request="Prepare a brief", verification_method="Check evidence",
        completion_conditions=("Brief checked",),
    )
    return module, repo, scope, module.WorkRequest(request, None, owner.session_id, {})
