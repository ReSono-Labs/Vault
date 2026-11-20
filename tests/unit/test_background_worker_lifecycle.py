from dataclasses import replace

import pytest

from app.vault_runtime.background_agent.coordination_contracts import WorkScope
from app.vault_runtime.background_agent.contracts import AutonomyProfile
from app.vault_runtime.background_agent.tool_supply import BackgroundToolSupply, BackgroundToolGrant, ToolBudgetExceeded
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


def scope():
    return WorkScope("user", "workspace", "work", 1, None, None, "grant")


def test_tool_context_does_not_mix_delegation_with_voice_or_another_owner():
    with pytest.raises(ValueError):
        ToolInvocationContext(agent=AgentKind.VOICE, user_id="user", workspace_id="workspace",
            tool_call_id="call", local_session_id=None, background_scope=scope())
    with pytest.raises(ValueError):
        ToolInvocationContext(agent=AgentKind.BACKGROUND, user_id="other", workspace_id="workspace",
            tool_call_id="call", local_session_id=None, background_scope=scope())


def test_delegated_catalog_is_closed_without_background_authorizer():
    catalog = ToolCatalog(authorizer=lambda *_: True)
    called = []
    catalog.register(ToolDefinition(tool_id="builtin.read.v1", name="read", description="Read",
        input_schema={"type": "object"}, handler=lambda *_: (called.append(True) or ToolInvocationResult("ok"))))
    ctx = ToolInvocationContext(agent=AgentKind.BACKGROUND, user_id="user", workspace_id="workspace",
        tool_call_id="call", local_session_id=None, background_scope=scope())
    assert catalog.invoke("read", {}, context=ctx).is_error
    assert called == []


def test_restored_budget_and_work_affinity_are_enforced():
    class Authority:
        def allowed_tool_names(self, _scope):
            return frozenset({"read"})

    catalog = ToolCatalog(authorizer=lambda *_: True, background_authorizer=lambda *_: True)
    catalog.register(ToolDefinition(tool_id="builtin.read.v1", name="read", description="Read",
        input_schema={"type": "object"}, handler=lambda *_: ToolInvocationResult("ok")))
    supply = BackgroundToolSupply(catalog=catalog,
        grant=BackgroundToolGrant(AutonomyProfile.LIMITED, frozenset(), 2), user_id="user", workspace_id="workspace",
        calls_used=1, background_scope=scope(), authority=Authority())
    ctx = ToolInvocationContext(agent=AgentKind.BACKGROUND, user_id="user", workspace_id="workspace",
        tool_call_id="call", local_session_id=None, background_scope=scope())
    assert supply.invoke("read", {}, context=replace(ctx, background_scope=replace(scope(), work_id="other"))).is_error
    assert supply.invoke("read", {}, context=ctx).text == "ok"
    with pytest.raises(ToolBudgetExceeded):
        supply.invoke("read", {}, context=ctx)
