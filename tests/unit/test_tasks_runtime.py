from app.vault_runtime.builtin_plugins import BUILTIN_PLUGINS
from app.vault_runtime.tasks_tools import register_tasks_tools
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog


class _TasksRepo:
    def list(self, **kwargs):
        return []

    def get(self, **kwargs):
        return None


class _PluginState:
    def __init__(self):
        self.enabled_keys = set()

    def enabled(self, *, account_id, workspace_id, plugin_key):
        return plugin_key in self.enabled_keys


def test_tasks_tools_project_only_when_builtin_enabled():
    state = _PluginState()
    catalog = ToolCatalog(authorizer=lambda *_: True)
    register_tasks_tools(catalog=catalog, repository=_TasksRepo(), builtin_plugins=state)
    names = {item.name for item in catalog.definitions_for(AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1")}
    assert "tasks_list" not in names
    state.enabled_keys.add("tasks")
    names = {item.name for item in catalog.definitions_for(AgentKind.VOICE, user_id="user-1", workspace_id="workspace-1")}
    assert {"tasks_list", "tasks_read", "tasks_add", "tasks_confirm_action"} <= names


def test_tasks_builtin_plugin_is_catalogued():
    assert any(item.key == "tasks" for item in BUILTIN_PLUGINS)
