from app.vault_runtime.system_agents.inventory import AgentKind, SYSTEM_AGENT_INVENTORY


def test_system_agent_inventory_is_exactly_voice_and_background() -> None:
    assert tuple(item.kind for item in SYSTEM_AGENT_INVENTORY) == (
        AgentKind.VOICE, AgentKind.BACKGROUND,
    )
    assert sum(item.interactive for item in SYSTEM_AGENT_INVENTORY) == 1


def test_agent_kind_rejects_every_non_system_identity() -> None:
    prohibited = (
        "build", "foundry", "hub", "specialist", "coordinator", "developer",
        "marketplace", "package", "generated", "research", "communications",
    )
    for value in prohibited:
        try:
            AgentKind(value)
        except ValueError:
            continue
        raise AssertionError(f"prohibited agent kind accepted: {value}")
