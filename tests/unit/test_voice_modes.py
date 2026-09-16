from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.voice.modes import GOAL_INTAKE_MODE, PRIMARY_MODE, VoiceModeService, register_voice_mode_tool
from app.vault_runtime.tools.catalog import ToolCatalog


def test_voice_mode_switch_limits_goal_start_to_intake() -> None:
    modes = VoiceModeService()
    catalog = ToolCatalog(authorizer=lambda _d, _c: True)
    register_voice_mode_tool(catalog, modes)
    modes.open_session(
        "voice-1",
        primary_instructions="primary",
        primary_tools=lambda: (),
        goal_intake_tools=lambda: (),
    )
    context = ToolInvocationContext(
        agent=AgentKind.VOICE, user_id="u", workspace_id="w",
        tool_call_id="c", local_session_id="s", voice_session_id="voice-1",
    )
    assert modes.allows("memory_lookup", context)
    assert not modes.allows("goal_start", context)
    switched = modes.switch("voice-1", GOAL_INTAKE_MODE)
    assert switched.structured_content["modeKey"] == GOAL_INTAKE_MODE
    assert modes.allows("goal_start", context)
    assert not modes.allows("memory_lookup", context)
    modes.restore_primary("voice-1")
    assert modes.mode("voice-1") == PRIMARY_MODE


def test_goal_start_hands_background_all_visible_tools() -> None:
    from app.vault_runtime.background_agent.contracts import AutonomyProfile
    from app.vault_runtime.voice.goal_tools import register_goal_tools

    captured: dict[str, object] = {}

    class _Service:
        def submit(self, **kwargs):
            captured.update(kwargs)
            request = kwargs["request"]
            return type("Run", (), {"request": request, "state": type("S", (), {"value": "queued"})()})()

    catalog = ToolCatalog(authorizer=lambda _d, _c: True)
    modes = VoiceModeService()
    register_goal_tools(catalog, _Service(), modes)  # type: ignore[arg-type]
    modes.open_session("voice-1", primary_instructions="p", primary_tools=lambda: (), goal_intake_tools=lambda: ())
    modes.switch("voice-1", GOAL_INTAKE_MODE)
    result = catalog.invoke(
        "goal_start", {"goal": "Write a summary", "rules": ["Stay local"]},
        context=ToolInvocationContext(
            agent=AgentKind.VOICE, user_id="u", workspace_id="w",
            tool_call_id="c", local_session_id="s", voice_session_id="voice-1",
        ),
    )
    assert not result.is_error
    request = captured["request"]
    assert request.requested_tool_names == ()
    assert request.autonomy is AutonomyProfile.EXPANDED
    assert request.objective == "Write a summary"
