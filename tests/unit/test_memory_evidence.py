import json

from app.vault_runtime.memory.evidence import bounded_tool_evidence


def test_tool_evidence_is_recursive_redacted_and_bounded() -> None:
    payload = bounded_tool_evidence(
        name="example", arguments={"token": "no", "nested": {"Password": "never"}},
        result={"safe": "x" * 20000, "api_key": "hidden"}, is_error=False,
    )
    assert len(payload) == 16384
    assert "no" not in payload and "never" not in payload and "hidden" not in payload
    assert "[REDACTED]" in payload


def test_small_tool_evidence_is_valid_json() -> None:
    payload = bounded_tool_evidence(name="x", arguments={}, result={"ok": True}, is_error=False)
    assert json.loads(payload)["result"] == {"ok": True}
