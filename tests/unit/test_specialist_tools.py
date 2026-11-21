"""Specialists work with the coordinator's tools (owner, 2026-11-21)."""
from __future__ import annotations

from app.vault_runtime.background_agent.contracts import AutonomyProfile, RunLimits
from app.vault_runtime.background_agent.coordination_contracts import WorkerSpec
from app.vault_runtime.background_agent.coordinator import filter_helper_tool_names
from app.vault_runtime.background_agent.tool_supply import BackgroundToolGrant, BackgroundToolSupply
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationResult

AVAILABLE = frozenset({"web_search", "link_card_publish", "link_card_archive", "workspace_write_file",
                       "memory_lookup", "agent2agent_send", "a2a_collab_turn", "link_setup_install",
                       "link_chat_card_publish", "goal_start"})


def _spec(tools: tuple[str, ...]) -> WorkerSpec:
    return WorkerSpec(role_key="uap_daily_watch", purpose="Research", instructions="Research UAP news.",
                      tool_names=tools, resource_policy={}, limits=RunLimits())


def test_a_specialist_with_all_tools_gets_the_coordinators_tools_minus_the_exclusions() -> None:
    tools = set(filter_helper_tool_names(requested_tools=("*",), worker_spec=_spec(("*",)), available=AVAILABLE))
    assert tools == {"web_search", "link_card_publish", "link_card_archive", "workspace_write_file", "memory_lookup"}
    # An assignment without a list uses the specialist's tools, not none.
    assert set(filter_helper_tool_names(requested_tools=(), worker_spec=_spec(("*",)), available=AVAILABLE)) == tools


def test_restricted_lists_still_restrict_and_never_reach_agent_to_agent_sends() -> None:
    assert filter_helper_tool_names(requested_tools=(), worker_spec=_spec(("web_search",)),
                                    available=AVAILABLE) == ("web_search",)
    assert filter_helper_tool_names(requested_tools=("web_search", "agent2agent_send"), worker_spec=_spec(("*",)),
                                    available=AVAILABLE) == ("web_search",)
    # An explicit "no tools" assignment keeps meaning no tools.
    assert filter_helper_tool_names(requested_tools=("__none__",), worker_spec=_spec(("*",)),
                                    available=AVAILABLE) == ("__none__",)


def test_assigned_work_may_archive_a_home_card_but_no_other_delete() -> None:
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    for name, effect in (("link_card_archive", "delete"), ("workspace_delete_path", "delete"),
                         ("link_card_publish", "write"), ("web_search", "read")):
        catalog.register(ToolDefinition(
            tool_id=f"builtin.{name}.v1", name=name, description=name,
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda _context, _arguments: ToolInvocationResult("ok"),
            effect_class=effect, audiences=frozenset({AgentKind.BACKGROUND}),
        ))
    supply = BackgroundToolSupply(catalog=catalog, grant=BackgroundToolGrant(
        autonomy=AutonomyProfile.EXPANDED, explicit_names=frozenset(), max_calls=5,
        allowed_deletes=frozenset({"link_card_archive"})))
    assert {item["name"] for item in supply.definitions()} == {"link_card_archive", "link_card_publish", "web_search"}
    plain = BackgroundToolSupply(catalog=catalog, grant=BackgroundToolGrant(
        autonomy=AutonomyProfile.LIMITED, explicit_names=frozenset(), max_calls=5))
    assert {item["name"] for item in plain.definitions()} == {"web_search"}
