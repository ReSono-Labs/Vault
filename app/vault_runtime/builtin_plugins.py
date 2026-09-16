"""Workspace-scoped built-in plugins ported from the Voice capability catalog."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from psycopg.types.json import Jsonb


@dataclass(frozen=True, slots=True)
class BuiltinPluginSpec:
    key: str
    name: str
    description: str
    defaults: dict[str, Any]


BUILTIN_PLUGINS = (
    BuiltinPluginSpec("markets", "Markets", "Get market updates, stock quotes, company news, and help finding ticker symbols.", {"watchlist": []}),
    BuiltinPluginSpec("weather", "Weather", "Get current conditions and a quick forecast for your saved locations.", {"primaryLocation": "", "savedLocations": []}),
    BuiltinPluginSpec("news", "News", "Hear current headlines for the topics you care about.", {"defaultCategory": "top", "headlineCount": 5}),
    BuiltinPluginSpec("local_events", "Local Events", "Find nearby events, save favorites, and add an event to your calendar.", {"homeLocation": "", "radiusMiles": 25, "interests": []}),
    BuiltinPluginSpec("agent_mail", "Agent Mail", "Give your assistant a separate mailbox for reading and sending approved messages.", {}),
    BuiltinPluginSpec("tasks", "Tasks", "Keep a simple local task list your assistant can read and update through Voice.", {}),
    BuiltinPluginSpec("agent2agent", "Agent2Agent", "Let Voice and the Background Agent talk to other A2A agents, and let other agents call the Background Agent when inbound is enabled.", {}),
    BuiltinPluginSpec("agent2agent_collab", "Collab", "Internal collab donor; follows Agent2Agent. Not a user-facing built-in.", {}),
)
_BY_KEY = {item.key: item for item in BUILTIN_PLUGINS}
HIDDEN_BUILTIN_KEYS = frozenset({"agent2agent_collab"})
USER_VISIBLE_BUILTINS = tuple(item for item in BUILTIN_PLUGINS if item.key not in HIDDEN_BUILTIN_KEYS)


class BuiltinPluginRepository:
    def __init__(self, *, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self):
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vault_private.vault_builtin_plugins (
                  account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
                  workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
                  plugin_key text NOT NULL,
                  enabled boolean NOT NULL DEFAULT false,
                  configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
                  updated_at timestamptz NOT NULL DEFAULT now(),
                  PRIMARY KEY (account_id, workspace_id, plugin_key)
                )
            """)

    @staticmethod
    def _scope(cursor, account_id: str, workspace_id: str) -> None:
        cursor.execute("""SELECT 1 FROM vault_private.local_workspace_memberships
            WHERE user_id=%s AND workspace_id=%s AND status='active'""", (account_id, workspace_id))
        if cursor.fetchone() is None:
            raise PermissionError("Plugin access was not authorized for this workspace.")

    def list(self, *, account_id: str, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            self._scope(cursor, account_id, workspace_id)
            cursor.execute("SELECT plugin_key,enabled,configuration,updated_at FROM vault_private.vault_builtin_plugins WHERE account_id=%s AND workspace_id=%s", (account_id, workspace_id))
            rows = {row[0]: row for row in cursor.fetchall()}
        return [self._payload(spec, rows.get(spec.key)) for spec in USER_VISIBLE_BUILTINS]

    def get(self, *, account_id: str, workspace_id: str, plugin_key: str) -> dict[str, Any]:
        spec = self._spec(plugin_key)
        with self._connect() as connection, connection.cursor() as cursor:
            self._scope(cursor, account_id, workspace_id)
            cursor.execute("SELECT plugin_key,enabled,configuration,updated_at FROM vault_private.vault_builtin_plugins WHERE account_id=%s AND workspace_id=%s AND plugin_key=%s", (account_id, workspace_id, plugin_key))
            row = cursor.fetchone()
        return self._payload(spec, row)

    def update(self, *, account_id: str, workspace_id: str, plugin_key: str, enabled: bool | None = None, configuration: dict[str, Any] | None = None) -> dict[str, Any]:
        if plugin_key in HIDDEN_BUILTIN_KEYS:
            raise ValueError("That built-in plugin is not available.")
        spec = self._spec(plugin_key)
        current = self.get(account_id=account_id, workspace_id=workspace_id, plugin_key=plugin_key)
        next_enabled = current["enabled"] if enabled is None else bool(enabled)
        next_configuration = current["configuration"] if configuration is None else _validate_config(spec.key, configuration)
        with self._connect() as connection, connection.cursor() as cursor:
            self._scope(cursor, account_id, workspace_id)
            cursor.execute("""INSERT INTO vault_private.vault_builtin_plugins(account_id,workspace_id,plugin_key,enabled,configuration)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT(account_id,workspace_id,plugin_key) DO UPDATE SET enabled=EXCLUDED.enabled,configuration=EXCLUDED.configuration,updated_at=now()
                RETURNING plugin_key,enabled,configuration,updated_at""", (account_id, workspace_id, plugin_key, next_enabled, Jsonb(next_configuration)))
            row = cursor.fetchone()
            if plugin_key == "agent2agent":
                cursor.execute("""INSERT INTO vault_private.vault_builtin_plugins(account_id,workspace_id,plugin_key,enabled,configuration)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT(account_id,workspace_id,plugin_key) DO UPDATE SET enabled=EXCLUDED.enabled,updated_at=now()""",
                    (account_id, workspace_id, "agent2agent_collab", next_enabled, Jsonb({})))
        return self._payload(spec, row)

    def enabled(self, *, account_id: str, workspace_id: str, plugin_key: str) -> bool:
        return bool(self.get(account_id=account_id, workspace_id=workspace_id, plugin_key=plugin_key)["enabled"])

    @staticmethod
    def _spec(key: str) -> BuiltinPluginSpec:
        try: return _BY_KEY[key]
        except KeyError as exc: raise ValueError("That built-in plugin is not available.") from exc

    @staticmethod
    def _payload(spec: BuiltinPluginSpec, row) -> dict[str, Any]:
        stored = row[2] if row and isinstance(row[2], dict) else {}
        config = {**spec.defaults, **stored}
        return {"key": spec.key, "name": spec.name, "description": spec.description, "enabled": bool(row[1]) if row else False, "configuration": config, "builtIn": True, "canDelete": False, "updatedAt": row[3].isoformat() if row else None}


def _text(value: object, *, maximum: int) -> str:
    result = " ".join(str(value or "").split())
    if len(result) > maximum: raise ValueError("One of the saved values is too long.")
    return result


def _strings(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list): return []
    result = []
    for item in value:
        cleaned = _text(item, maximum=120)
        if cleaned and cleaned not in result: result.append(cleaned)
    return result[:limit]


def _validate_config(key: str, value: dict[str, Any]) -> dict[str, Any]:
    if key == "weather": return {"primaryLocation": _text(value.get("primaryLocation"), maximum=120), "savedLocations": _strings(value.get("savedLocations"), limit=12)}
    if key == "news":
        category = _text(value.get("defaultCategory"), maximum=40).lower() or "top"
        if category not in {"top","world","business","technology","science","health","sports","entertainment"}: raise ValueError("Choose one of the available news topics.")
        return {"defaultCategory": category, "headlineCount": max(1, min(int(value.get("headlineCount") or 5), 10))}
    if key == "markets": return {"watchlist": [item.upper() for item in _strings(value.get("watchlist"), limit=20)]}
    if key == "local_events": return {"homeLocation": _text(value.get("homeLocation"), maximum=120), "radiusMiles": max(1, min(int(value.get("radiusMiles") or 25), 100)), "interests": _strings(value.get("interests"), limit=12), "savedEvents": list(value.get("savedEvents", []))[:50] if isinstance(value.get("savedEvents"), list) else [], "sources": list(value.get("sources", []))[:25] if isinstance(value.get("sources"), list) else [], "feedback": list(value.get("feedback", []))[:100] if isinstance(value.get("feedback"), list) else []}
    if key == "agent_mail": return {}
    if key == "tasks": return {}
    if key == "agent2agent": return {}
    if key == "agent2agent_collab": return {}
    return json.loads(json.dumps(value))
