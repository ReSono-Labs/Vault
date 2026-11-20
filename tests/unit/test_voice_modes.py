from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.voice.modes import GOAL_INTAKE_MODE, PRIMARY_MODE, VoiceModeService, register_voice_mode_tool
from app.vault_runtime.tools.catalog import ToolCatalog


def test_voice_mode_switch_limits_hand_off_to_coordinator_intake() -> None:
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
    assert not modes.allows("coordinator_hand_off", context)
    switched = modes.switch("voice-1", GOAL_INTAKE_MODE)
    assert switched.structured_content["modeKey"] == GOAL_INTAKE_MODE
    assert modes.allows("coordinator_hand_off", context)
    assert not modes.allows("memory_lookup", context)
    modes.restore_primary("voice-1")
    assert modes.mode("voice-1") == PRIMARY_MODE




def test_gpt_live_client_offers_the_hand_off_without_intake() -> None:
    modes = VoiceModeService()
    modes.open_session("voice-2", primary_instructions="p", primary_tools=lambda: (), goal_intake_tools=lambda: ())
    context = ToolInvocationContext(
        agent=AgentKind.VOICE, user_id="u", workspace_id="w",
        tool_call_id="c", local_session_id="s", voice_session_id="voice-2",
    )
    assert not modes.allows("coordinator_hand_off", context)
    modes.allow_direct_hand_off("voice-2")
    assert modes.allows("coordinator_hand_off", context) and modes.allows("memory_lookup", context)
    assert not modes.allows("voice_mode_switch", context)
    modes.close_session("voice-2")
    assert not modes.allows("coordinator_hand_off", context)
