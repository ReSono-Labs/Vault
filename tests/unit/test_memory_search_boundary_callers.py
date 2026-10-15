import json
from datetime import datetime, timezone

import pytest

from app.vault_runtime.external_memory.models import ExternalMemoryIdentity
from app.vault_runtime.external_memory.service import ExternalMemoryService
from app.vault_runtime.extensions.plugin_services import PluginCapability, PluginVaultServices
from app.vault_runtime.memory.models import MemoryRecord
from app.vault_runtime.memory.retrieval import RetrievalMatch
from app.vault_runtime.memory.service import MemoryService
from app.vault_runtime.memory.tools import register_memory_tools
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext


class ReadBackend:
    repairs_vectors_during_query = False

    def __init__(self):
        now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        self.result = (RetrievalMatch(MemoryRecord(
            "m", "w", "u", "private", "u", "project", "fact", "key", "content",
            "user_asserted", "high", "normal", "active", 3, now, now,
        ), 0.75, ("semantic",)),)
        self.calls = []

    def retrieve(self, query, **kwargs):
        assert (kwargs["user_id"], kwargs["workspace_id"]) == ("u", "w")
        self.calls.append((query, kwargs))
        return self.result


def forbidden_finalize(*args):
    pytest.fail("search must not finalize or mutate memory")


def test_actual_registered_memory_lookup_json_and_scope():
    backend = ReadBackend()
    service = MemoryService(repository=object(), search_backend=backend)
    catalog = ToolCatalog(authorizer=lambda definition, context: True)
    register_memory_tools(catalog=catalog, repository=object(), service=service)
    result = catalog.invoke("memory_lookup", {"query": " invoice ", "limit": 8},
                            context=ToolInvocationContext(
                                agent=AgentKind.VOICE, user_id="u", workspace_id="w",
                                tool_call_id="call", local_session_id="session",
                            ))
    expected = {"items": [{
        "memoryId": "m", "domain": "project", "memoryType": "fact", "memoryKey": "key",
        "content": "content", "confidence": "high", "sensitivity": "normal",
        "visibility": "private", "score": 0.75, "matchMethods": ["semantic"],
    }], "embeddingsAvailable": False}
    assert not result.is_error
    assert result.structured_content == expected
    assert json.loads(result.text) == expected
    assert backend.calls == [("invoice", dict(user_id="u", workspace_id="w", limit=8, embedder=None))]


def test_external_search_credential_scope_and_tuple_payload():
    class Integrations:
        def authorize(self, **kwargs):
            assert kwargs == dict(credential="credential", operation="search", request_id="request")
            return ExternalMemoryIdentity("integration", "w", "u", "test", "test", ("search",))

    backend = ReadBackend()
    external = ExternalMemoryService(
        integrations=Integrations(), memories=object(),
        memory_service=MemoryService(repository=object(), search_backend=backend),
        finalize=forbidden_finalize,
    )
    result = external.search(credential="credential", request_id="request", query=" invoice ", limit=25)
    assert result is backend.result
    assert result[0].memory.current_version == 3
    assert backend.calls == [("invoice", dict(user_id="u", workspace_id="w", limit=25, embedder=None))]


def test_plugin_search_authorized_capability_scope_and_json():
    class ScopedPluginServices(PluginVaultServices):
        # Test the real call handler with a scoped auth fixture, not crypto authorization.
        def authorize(self, token, *, invocation_id, service):
            assert (token, invocation_id, service) == ("token", "invocation", "memory.search")
            return PluginCapability("plugin", "u", "w", invocation_id, frozenset({service}))

    backend = ReadBackend()
    plugin = ScopedPluginServices(
        repository=object(), key=object(), memories=object(),
        memory_service=MemoryService(repository=object(), search_backend=backend),
        finalize=forbidden_finalize, service_url="http://fixture.invalid",
    )
    status, result = plugin.call(token="token", invocation_id="invocation", service="memory.search",
                                 payload={"query": " invoice "})
    assert status == 200
    assert result == {"items": [{"memoryId": "m", "content": "content", "domain": "project",
                                "type": "fact", "confidence": "high", "score": 0.75,
                                "matchMethods": ["semantic"]}]}
    assert backend.calls == [("invoice", dict(user_id="u", workspace_id="w", limit=5, embedder=None))]
