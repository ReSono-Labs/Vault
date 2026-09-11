from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERMES = Path(os.environ.get("HERMES_DONOR_PATH", "/home/christian/.hermes/hermes-agent"))
sys.path.insert(0, str(HERMES))

from resono_vault_hermes import VaultMemoryProvider


class RecordingProvider(VaultMemoryProvider):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _request(self, path, payload):
        self.calls.append((path, payload))
        if path.endswith("search"):
            return {"items": [{"memoryId": "m1", "content": "Owner prefers concise reports."}]}
        return {"status": "accepted"}


def test_recall_tools_and_primary_turn_proposal(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_MEMORY_CREDENTIAL", "secret")
    provider = RecordingProvider()
    assert provider.is_available()
    provider.initialize("session-1", agent_context="primary")
    recalled = provider.prefetch("reports")
    assert "Owner prefers concise reports" in recalled
    assert any(path.endswith("startup") for path, _payload in provider.calls)
    provider.prefetch("reports again")
    assert sum(path.endswith("startup") for path, _payload in provider.calls) == 1
    assert provider.recall_status().count == 1
    assert json.loads(provider.handle_tool_call("vault_memory_get", {"memory_id": "m1"}))
    assert json.loads(provider.handle_tool_call("vault_memory_store", {
        "content": "Remember concise reports.", "evidence": "Direct user request",
    }))
    tool = json.loads(provider.handle_tool_call("vault_memory_forget", {"memory_id": "m1"}))
    assert tool == {"status": "accepted"}
    provider.sync_turn("Make it short", "Done", session_id="session-1")
    provider.shutdown()
    assert any(path.endswith("propose") for path, _payload in provider.calls)


def test_non_primary_context_never_proposes(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_MEMORY_CREDENTIAL", "secret")
    provider = RecordingProvider()
    provider.initialize("child", agent_context="subagent")
    provider.sync_turn("secret", "response", session_id="child")
    provider.shutdown()
    assert not any(path.endswith("propose") for path, _payload in provider.calls)
