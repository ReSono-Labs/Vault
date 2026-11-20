from __future__ import annotations

from types import SimpleNamespace

from app.vault_runtime.live_memory.tool_routing import UNAVAILABLE_REASON, ToolRoutingPreferences, ToolRoutingStatus


class Credentials:
    def __init__(self, has_key: bool) -> None:
        self.has_key = has_key
        self.calls = 0

    def has_api_key(self, principal, provider_key):
        self.calls += 1
        assert provider_key == "openai"
        return self.has_key


class Prefs(ToolRoutingPreferences):
    def __init__(self, credentials, stored=None):
        super().__init__(database_url="unused", credentials=credentials)
        self.stored = stored

    def _enabled(self, user_id, workspace_id):
        return True if self.stored is None else self.stored


PRINCIPAL = SimpleNamespace(user_id="u", workspace_id="w", session_id="s")


def test_routing_is_unavailable_without_an_openai_api_key() -> None:
    status = Prefs(Credentials(False)).status(PRINCIPAL)
    assert status.enabled and not status.available and not status.active
    assert status.payload() == {"enabled": True, "available": False, "reason": UNAVAILABLE_REASON}


def test_routing_follows_the_switch_and_caches_the_lookup() -> None:
    credentials = Credentials(True)
    prefs = Prefs(credentials, stored=False)
    assert prefs.status(PRINCIPAL) == ToolRoutingStatus(enabled=False, available=True)
    prefs.status(PRINCIPAL)
    assert credentials.calls == 1, "status is cached between live preparation calls"


def test_runtime_makes_no_decisions_call_when_routing_is_off_or_unavailable() -> None:
    import inspect

    from app.vault_runtime.live_memory.chat_runtime import ChatPreparationRuntime

    source = inspect.getsource(ChatPreparationRuntime._update)
    gate = source.index("self.tool_routing.status(principal)")
    call = source.index("DecisionSelector(")
    assert gate < call
    assert 'entry.tool_status = "unavailable"' in source and 'entry.tool_status = "off"' in source


def test_presentation_hint_skips_the_call_without_a_transport() -> None:
    import inspect

    from app.vault_runtime.conversation.runtime import ConversationRuntime

    assert "None if transport is None else predict(" in inspect.getsource(ConversationRuntime)
