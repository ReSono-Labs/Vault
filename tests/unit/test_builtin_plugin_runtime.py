import json

from app.vault_runtime.builtin_plugin_tools import register_builtin_plugin_tools
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext


class PluginState:
    def __init__(self):
        self.enabled_keys = set()
        self.configs = {
            "weather": {"primaryLocation": "Tampa"}, "news": {"defaultCategory": "top", "headlineCount": 3},
            "markets": {"watchlist": ["AAPL"]}, "local_events": {"homeLocation": "Tampa", "radiusMiles": 25, "interests": []},
        }

    def enabled(self, *, account_id, workspace_id, plugin_key):
        assert (account_id, workspace_id) == ("user-1", "workspace-1")
        return plugin_key in self.enabled_keys

    def get(self, *, account_id, workspace_id, plugin_key):
        return {"configuration": self.configs[plugin_key]}

    def update(self, *, account_id, workspace_id, plugin_key, configuration, **_kwargs):
        self.configs[plugin_key] = configuration
        return {"configuration": configuration}


class Credentials:
    pass


def context():
    return ToolInvocationContext(agent=AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1", tool_call_id="call-1", local_session_id="session-1", voice_session_id="voice-1")


def test_plugin_state_changes_the_exact_voice_tool_projection():
    state = PluginState()
    catalog = ToolCatalog(authorizer=lambda *_: True)
    register_builtin_plugin_tools(catalog=catalog, repository=state, credentials=Credentials())
    names = lambda: {item.name for item in catalog.definitions_for(AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1")}
    assert "weather_read" not in names()
    assert "markets_quote" not in names()
    state.enabled_keys.add("weather")
    assert "weather_read" in names()
    assert "news_read" not in names()
    state.enabled_keys.add("markets")
    assert {"markets_overview", "markets_search_symbol", "markets_quote", "markets_news"} <= names()
    state.enabled_keys.remove("weather")
    assert "weather_read" not in names()


def test_disabled_plugin_is_rejected_even_if_a_stale_session_calls_its_tool(monkeypatch):
    state = PluginState(); state.enabled_keys.add("markets")
    catalog = ToolCatalog(authorizer=lambda *_: True)
    register_builtin_plugin_tools(catalog=catalog, repository=state, credentials=Credentials())
    monkeypatch.setattr("app.vault_runtime.builtin_plugin_tools.run_web_search", lambda **kwargs: {"status":"completed","text":"grounded","results":[{"url":"https://example.com"}]})
    completed = catalog.invoke("markets_quote", {"symbol":"AAPL"}, context=context())
    assert not completed.is_error
    assert json.loads(completed.text)["status"] == "completed"
    state.enabled_keys.remove("markets")
    blocked = catalog.invoke("markets_quote", {"symbol":"AAPL"}, context=context())
    assert blocked.is_error
    assert blocked.text == "Tool is not granted."


def test_local_events_full_voice_tool_set_is_projected_only_when_enabled():
    state = PluginState(); catalog = ToolCatalog(authorizer=lambda *_: True)
    register_builtin_plugin_tools(catalog=catalog, repository=state, credentials=Credentials())
    state.enabled_keys.add("local_events")
    names = {item.name for item in catalog.definitions_for(AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1")}
    assert {"local_events_setup","local_events_search","local_events_save_event","local_events_add_source","local_events_remove_source","local_events_review_sources","local_events_feedback","local_events_add_to_calendar"} <= names
