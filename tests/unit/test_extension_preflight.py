from datetime import UTC, datetime, timedelta

import pytest

from app.vault_runtime.extensions.models import ExtensionAudience, ExtensionKind
from app.vault_runtime.extensions.preflight import PreflightError, PreflightRegistry
from app.vault_runtime.system_agents.inventory import AgentKind


def _issue(registry: PreflightRegistry[str], now: datetime):
    return registry.issue(
        kind=ExtensionKind.SKILL, identity="demo", principal_user_id="user-a",
        workspace_id="workspace-a", candidate_hash="new", current_hash="old",
        audience=ExtensionAudience(frozenset({AgentKind.VOICE})), payload="payload", now=now,
    )


def test_preflight_is_one_use_scope_hash_and_replace_bound() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    registry: PreflightRegistry[str] = PreflightRegistry()
    record = _issue(registry, now)
    with pytest.raises(PreflightError, match="replacement"):
        registry.consume(record.token, principal_user_id="user-a", workspace_id="workspace-a", current_hash="old", replace=False, now=now)
    assert registry.consume(record.token, principal_user_id="user-a", workspace_id="workspace-a", current_hash="old", replace=True, now=now).payload == "payload"

    record = _issue(registry, now)
    with pytest.raises(PreflightError, match="another local scope"):
        registry.consume(record.token, principal_user_id="user-b", workspace_id="workspace-a", current_hash="old", replace=True, now=now)

    record = _issue(registry, now)
    with pytest.raises(PreflightError, match="changed"):
        registry.consume(record.token, principal_user_id="user-a", workspace_id="workspace-a", current_hash="different", replace=True, now=now)


def test_preflight_expires_and_valid_confirmation_returns_payload() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    registry: PreflightRegistry[str] = PreflightRegistry(lifetime=timedelta(minutes=1))
    record = _issue(registry, now)
    with pytest.raises(PreflightError, match="expired"):
        registry.consume(record.token, principal_user_id="user-a", workspace_id="workspace-a", current_hash="old", replace=True, now=now + timedelta(minutes=1))
    record = _issue(registry, now)
    consumed = registry.consume(record.token, principal_user_id="user-a", workspace_id="workspace-a", current_hash="old", replace=True, now=now)
    assert consumed.payload == "payload"


def test_extension_audience_allows_only_two_fixed_agent_values() -> None:
    assert ExtensionAudience.parse(["voice", "background"]).agents == frozenset(AgentKind)
    with pytest.raises(ValueError):
        ExtensionAudience.parse(["build"])
