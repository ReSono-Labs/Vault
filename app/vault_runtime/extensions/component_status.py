"""Per-component status of one install for the person asking (STD-DIAG).

Each part of a package reports one of: ``unsupported`` (skipped: a feature Vault does not
run), ``invalid`` (skipped: breaks the standard), ``connection_failed`` / ``auth_failed``
(the last tool check could not reach or sign in to the server), ``not_checked`` (tools not
discovered yet), ``not_granted`` (available, but not granted to this person) or ``ready``.
"""
from __future__ import annotations

from typing import Any

from app.vault_runtime.extensions.import_diagnostics import classify_diagnostic
from app.vault_runtime.extensions.mcp_accounts import McpAccounts, is_hosted
from app.vault_runtime.extensions.mcp_rules import connection_executable
from app.vault_runtime.extensions.models import ExtensionKind
from app.vault_runtime.extensions.repository import ExtensionRepository
from app.vault_runtime.system_agents.inventory import AgentKind


def component_status(*, repository: ExtensionRepository, accounts: McpAccounts | None, user_id: str,
                     workspace_id: str, extension_id: str) -> list[dict[str, Any]]:
    scope = {"workspace_id": workspace_id}
    record = repository.by_id(actor_user_id=user_id, extension_id=extension_id, **scope)
    items: list[dict[str, Any]] = []
    for diagnostic in record.configuration.get("importDiagnostics") or ():
        entry = classify_diagnostic(str(diagnostic))
        if entry["status"] in ("unsupported", "invalid"):
            items.append(entry)

    granted_skills: set[str] = set()
    for agent in AgentKind:
        for granted, capability, _effect in repository.granted_extensions(
                user_id=user_id, agent=agent, kind=record.kind, capability_prefix="", **scope):
            if granted.extension_id == extension_id:
                granted_skills.add(capability)
    if record.kind is ExtensionKind.SKILL:
        items.append({"component": f"skill:{record.identity}",
                      "status": "ready" if granted_skills else "not_granted"})
    for kind, name in repository.components(user_id=user_id, extension_id=extension_id, **scope):
        if kind == "skill":
            items.append({"component": f"skill:{name}",
                          "status": "ready" if f"skill:{name}" in granted_skills else "not_granted"})

    connections = (record,) if record.kind is ExtensionKind.MCP else (
        repository.managed_children(actor_user_id=user_id, plugin_id=extension_id, owner=False, **scope)
        if record.kind is ExtensionKind.PLUGIN else ())
    for connection in connections:
        name = f"mcp:{connection.identity.rsplit('/', 1)[-1]}"
        entry: dict[str, Any] = {"component": name, "extensionId": connection.extension_id}
        failure = connection.configuration.get("lastDiscoveryError")
        if not connection_executable(connection.configuration):
            entry["status"] = "unsupported"
        elif isinstance(failure, dict) and failure.get("status") in ("connection_failed", "auth_failed"):
            entry.update(status=failure["status"], reason=str(failure.get("reason", ""))[:300])
        elif repository.discovered_tool_count(user_id=user_id, extension_id=connection.extension_id, **scope) == 0:
            entry["status"] = "not_checked"
        elif not any(repository.granted_mcp_tools(user_id=user_id, agent=agent,
                                                  extension_id=connection.extension_id, **scope)
                     for agent in AgentKind):
            entry["status"] = "not_granted"
        else:
            entry["status"] = "ready"
        if connection_executable(connection.configuration):
            if is_hosted(connection.configuration):
                entry["account"] = "service"
            elif accounts is not None:
                entry["account"] = accounts.status(user_id=user_id, extension_id=connection.extension_id,
                                                   **scope)["account"]
        items.append(entry)
    return items
