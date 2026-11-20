from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
from typing import Any
from uuid import uuid4

from app.vault_runtime.extensions.filesystem import managed_mcp_identity
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.schema import ensure_extension_schema
from app.vault_runtime.system_agents.inventory import AgentKind


class ExtensionRepositoryError(RuntimeError):
    code = "extension_repository_error"


class ExtensionAuthorizationError(ExtensionRepositoryError):
    code = "extension_authorization_denied"


class ExtensionConflictError(ExtensionRepositoryError):
    code = "extension_conflict"


class ExtensionNotFoundError(ExtensionRepositoryError):
    code = "extension_not_found"


@dataclass(frozen=True, slots=True)
class ExtensionRecord:
    extension_id: str
    kind: ExtensionKind
    identity: str
    display_name: str
    version: str | None
    description: str | None
    content_hash: str
    state: ExtensionState
    installed_by_user_id: str
    workspace_id: str
    previous_content_hash: str | None
    configuration: dict[str, object]


class ExtensionRepository:
    def __init__(self, *, database_url: str, connector: Callable[..., AbstractContextManager[Any]] | None = None) -> None:
        self._database_url = database_url
        self._connector = connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ensure_extension_schema(cursor)

    @staticmethod
    def _require_scope(cursor: Any, *, user_id: str, workspace_id: str, owner: bool = False) -> None:
        cursor.execute(
            """
            SELECT u.is_device_owner, m.membership_type
            FROM vault_private.local_users u
            JOIN vault_private.local_workspace_memberships m ON m.user_id=u.user_id
            JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
            WHERE u.user_id=%s AND m.workspace_id=%s AND u.status='active'
              AND m.status='active' AND w.status='active'
            """,
            (user_id, workspace_id),
        )
        row = cursor.fetchone()
        if row is None or (owner and not bool(row[0])):
            raise ExtensionAuthorizationError("active local scope and device-owner authority are required")

    def get(self, *, user_id: str, workspace_id: str, kind: ExtensionKind, identity: str, owner: bool = False) -> ExtensionRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id, owner=owner)
                cursor.execute(
                    """
                    SELECT extension_id,kind,identity,display_name,version,description,content_hash,
                           state,installed_by_user_id,installed_in_workspace_id,previous_content_hash,
                           configuration_json
                    FROM vault_private.vault_extensions
                    WHERE installed_in_workspace_id=%s AND kind=%s AND identity=%s
                    """, (workspace_id, kind.value, identity),
                )
                row = cursor.fetchone()
                return _record(row) if row else None

    def get_active(
        self, *, user_id: str, workspace_id: str, kind: ExtensionKind, identity: str, owner: bool = False,
    ) -> ExtensionRecord | None:
        record = self.get(
            user_id=user_id, workspace_id=workspace_id, kind=kind, identity=identity, owner=owner,
        )
        if record is None or record.state is ExtensionState.REMOVED:
            return None
        return record

    def purge_removed(
        self, *, actor_user_id: str, workspace_id: str, kind: ExtensionKind, identity: str,
    ) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute(
                    """DELETE FROM vault_private.vault_extensions
                       WHERE installed_in_workspace_id=%s AND kind=%s AND identity=%s AND state='removed'""",
                    (workspace_id, kind.value, identity),
                )
                return cursor.rowcount > 0

    def identity_still_installed(
        self, *, workspace_id: str, identity: str, excluding_extension_id: str | None = None,
    ) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT 1 FROM vault_private.vault_extensions
                       WHERE installed_in_workspace_id=%s AND identity=%s AND state <> 'removed'
                         AND (%s::text IS NULL OR extension_id <> %s::text)
                       LIMIT 1""",
                    (workspace_id, identity, excluding_extension_id, excluding_extension_id),
                )
                return cursor.fetchone() is not None

    def list_installed(self, *, actor_user_id: str, workspace_id: str) -> tuple[ExtensionRecord, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute(
                    """SELECT extension_id,kind,identity,display_name,version,description,content_hash,
                              state,installed_by_user_id,installed_in_workspace_id,previous_content_hash,
                              configuration_json
                       FROM vault_private.vault_extensions
                       WHERE installed_in_workspace_id=%s AND state <> 'removed'
                         AND NOT (configuration_json ? 'managedByPluginId')
                       ORDER BY kind,identity""", (workspace_id,),
                )
                return tuple(_record(row) for row in cursor.fetchall())

    def list_enabled_hosted_mcps(self) -> tuple[ExtensionRecord, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT extension_id,kind,identity,display_name,version,description,content_hash,
                              state,installed_by_user_id,installed_in_workspace_id,previous_content_hash,
                              configuration_json
                       FROM vault_private.vault_extensions
                       WHERE kind='mcp' AND state='enabled'
                         AND configuration_json->>'packageType'='hosted'
                       ORDER BY identity""",
                )
                return tuple(_record(row) for row in cursor.fetchall())

    def list_enabled_supervised_runtimes(self) -> tuple[ExtensionRecord, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT extension_id,kind,identity,display_name,version,description,content_hash,
                              state,installed_by_user_id,installed_in_workspace_id,previous_content_hash,
                              configuration_json
                       FROM vault_private.vault_extensions
                       WHERE state='enabled'
                         AND (
                           (kind='mcp' AND configuration_json->>'packageType'='hosted')
                           OR (kind='plugin' AND configuration_json->>'supervised'='true')
                         )
                       ORDER BY kind,identity""",
                )
                return tuple(_record(row) for row in cursor.fetchall())

    def managed_children(
        self, *, actor_user_id: str, workspace_id: str, plugin_id: str,
    ) -> tuple[ExtensionRecord, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute(
                    """SELECT extension_id,kind,identity,display_name,version,description,content_hash,
                              state,installed_by_user_id,installed_in_workspace_id,previous_content_hash,
                              configuration_json
                       FROM vault_private.vault_extensions
                       WHERE installed_in_workspace_id=%s AND state <> 'removed'
                         AND configuration_json->>'managedByPluginId'=%s
                       ORDER BY identity""",
                    (workspace_id, plugin_id),
                )
                return tuple(_record(row) for row in cursor.fetchall())

    def reconcile_managed_mcp(
        self, *, actor_user_id: str, workspace_id: str, plugin: ExtensionRecord,
        servers: tuple[tuple[str, str, dict[str, object]], ...],
    ) -> tuple[ExtensionRecord, ...]:
        """Make embedded MCP connections durable and owned by their parent Plugin."""
        if plugin.kind is not ExtensionKind.PLUGIN:
            raise ValueError("managed MCP parent must be a Plugin")
        desired: set[str] = set()
        result: list[ExtensionRecord] = []
        for name, content_hash, configuration in servers:
            identity = managed_mcp_identity(plugin_identity=plugin.identity, server_name=name)
            desired.add(identity)
            result.append(self.install(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                kind=ExtensionKind.MCP, identity=identity,
                display_name=name, version=plugin.version,
                description=f"Tool connection provided by {plugin.display_name}",
                content_hash=content_hash,
                configuration={**configuration, "managedByPluginId": plugin.extension_id,
                               "managedByPluginName": plugin.display_name},
            ))
        for child in self.managed_children(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            plugin_id=plugin.extension_id,
        ):
            if child.identity not in desired:
                self.set_state(
                    actor_user_id=actor_user_id, workspace_id=workspace_id,
                    extension_id=child.extension_id, state=ExtensionState.REMOVED,
                )
        return tuple(result)

    def set_managed_state(
        self, *, actor_user_id: str, workspace_id: str, plugin_id: str,
        state: ExtensionState,
    ) -> tuple[ExtensionRecord, ...]:
        children = self.managed_children(
            actor_user_id=actor_user_id, workspace_id=workspace_id, plugin_id=plugin_id,
        )
        return tuple(self.set_state(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            extension_id=child.extension_id, state=state,
        ) for child in children)

    def update_configuration(
        self, *, actor_user_id: str, workspace_id: str, extension_id: str,
        configuration: dict[str, object],
    ) -> ExtensionRecord:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute(
                    """UPDATE vault_private.vault_extensions
                       SET configuration_json=%s::jsonb,updated_at=now()
                       WHERE extension_id=%s AND installed_in_workspace_id=%s
                         AND kind IN ('plugin','mcp') AND state <> 'removed'
                       RETURNING extension_id,kind,identity,display_name,version,description,content_hash,
                                 state,installed_by_user_id,installed_in_workspace_id,previous_content_hash,
                                 configuration_json""",
                    (json.dumps(configuration, separators=(",", ":")), extension_id, workspace_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ExtensionNotFoundError("Plugin is unavailable")
                self._event(cursor, extension_id, workspace_id, actor_user_id, "settings_changed", {})
                return _record(row)

    def record_plugin_activity(
        self, *, actor_user_id: str, workspace_id: str, plugin_id: str, message: str,
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id)
                cursor.execute(
                    "SELECT 1 FROM vault_private.vault_extensions WHERE extension_id=%s AND installed_in_workspace_id=%s AND kind='plugin' AND state='enabled'",
                    (plugin_id, workspace_id),
                )
                if cursor.fetchone() is None:
                    raise ExtensionNotFoundError("Plugin is unavailable")
                self._event(cursor, plugin_id, workspace_id, actor_user_id, "activity", {"message": message})

    def by_id(self, *, actor_user_id: str, workspace_id: str, extension_id: str, owner: bool = False) -> ExtensionRecord:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=owner)
                cursor.execute(
                    """SELECT extension_id,kind,identity,display_name,version,description,content_hash,
                              state,installed_by_user_id,installed_in_workspace_id,previous_content_hash,
                              configuration_json
                       FROM vault_private.vault_extensions
                       WHERE extension_id=%s AND installed_in_workspace_id=%s""",
                    (extension_id,workspace_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ExtensionNotFoundError("extension is unavailable")
                return _record(row)

    def install(
        self, *, actor_user_id: str, workspace_id: str, kind: ExtensionKind,
        identity: str, display_name: str, version: str | None, description: str | None,
        content_hash: str, configuration: dict[str, object],
        components: tuple[tuple[str, str, str], ...] = (),
    ) -> ExtensionRecord:
        extension_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute(
                    """SELECT extension_id,content_hash FROM vault_private.vault_extensions
                       WHERE installed_in_workspace_id=%s AND kind=%s AND identity=%s FOR UPDATE""",
                    (workspace_id, kind.value, identity),
                )
                prior = cursor.fetchone()
                if prior:
                    extension_id = str(prior[0])
                try:
                    cursor.execute(
                        """
                        INSERT INTO vault_private.vault_extensions
                          (extension_id,kind,identity,display_name,version,description,content_hash,state,
                           installed_by_user_id,installed_in_workspace_id,previous_content_hash,configuration_json)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,'enabled',%s,%s,%s,%s::jsonb)
                        ON CONFLICT (installed_in_workspace_id,kind,identity) DO UPDATE SET
                          display_name=EXCLUDED.display_name,version=EXCLUDED.version,
                          description=EXCLUDED.description,previous_content_hash=vault_extensions.content_hash,
                          content_hash=EXCLUDED.content_hash,state='enabled',installed_by_user_id=EXCLUDED.installed_by_user_id,
                          configuration_json=EXCLUDED.configuration_json,removed_at=NULL,updated_at=now()
                        RETURNING extension_id,kind,identity,display_name,version,description,content_hash,
                                  state,installed_by_user_id,installed_in_workspace_id,previous_content_hash,configuration_json
                        """,
                        (extension_id,kind.value,identity,display_name,version,description,content_hash,
                         actor_user_id,workspace_id,str(prior[1]) if prior else None,
                         json.dumps(configuration, separators=(",", ":"))),
                    )
                    result = _record(cursor.fetchone())
                    cursor.execute("DELETE FROM vault_private.vault_extension_components WHERE extension_id=%s", (extension_id,))
                    for component_kind, component_name, component_hash in components:
                        cursor.execute(
                            """INSERT INTO vault_private.vault_extension_components
                               (component_id,extension_id,workspace_id,component_kind,component_name,component_hash)
                               VALUES (%s,%s,%s,%s,%s,%s)""",
                            (str(uuid4()),extension_id,workspace_id,component_kind,component_name,component_hash),
                        )
                    self._event(cursor, extension_id, workspace_id, actor_user_id, "installed" if not prior else "replaced", {"contentHash": content_hash})
                    return result
                except Exception as exc:
                    if getattr(exc, "sqlstate", None) == "23505":
                        raise ExtensionConflictError("extension component ownership collides") from exc
                    raise

    def set_state(self, *, actor_user_id: str, workspace_id: str, extension_id: str, state: ExtensionState) -> ExtensionRecord:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute(
                    """
                    UPDATE vault_private.vault_extensions SET state=%s,updated_at=now(),
                      removed_at=CASE WHEN %s='removed' THEN now() ELSE NULL END
                    WHERE extension_id=%s AND installed_in_workspace_id=%s
                    RETURNING extension_id,kind,identity,display_name,version,description,content_hash,
                              state,installed_by_user_id,installed_in_workspace_id,previous_content_hash,configuration_json
                    """, (state.value,state.value,extension_id,workspace_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ExtensionNotFoundError("extension is unavailable")
                if state is ExtensionState.REMOVED:
                    cursor.execute("DELETE FROM vault_private.vault_extension_grants WHERE extension_id=%s", (extension_id,))
                    cursor.execute("DELETE FROM vault_private.vault_extension_components WHERE extension_id=%s", (extension_id,))
                    cursor.execute("DELETE FROM vault_private.vault_mcp_tools WHERE extension_id=%s", (extension_id,))
                    cursor.execute("DELETE FROM vault_private.vault_extension_secrets WHERE extension_id=%s", (extension_id,))
                elif state is not ExtensionState.ENABLED:
                    cursor.execute("UPDATE vault_private.vault_extension_grants SET enabled=false,updated_at=now() WHERE extension_id=%s", (extension_id,))
                self._event(cursor, extension_id, workspace_id, actor_user_id, state.value, {})
                return _record(row)

    def set_grant(
        self, *, actor_user_id: str, target_user_id: str, workspace_id: str,
        extension_id: str, agent: AgentKind, capability_name: str = "",
        enabled: bool, effect_class: str | None = None,
    ) -> None:
        if effect_class not in {None, "read", "write", "delete"}:
            raise ValueError("invalid capability effect")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                self._require_scope(cursor, user_id=target_user_id, workspace_id=workspace_id)
                cursor.execute("SELECT 1 FROM vault_private.vault_extensions WHERE extension_id=%s AND installed_in_workspace_id=%s AND state='enabled'", (extension_id,workspace_id))
                if cursor.fetchone() is None:
                    raise ExtensionNotFoundError("enabled extension is unavailable")
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_extension_grants
                      (grant_id,extension_id,user_id,workspace_id,agent_kind,capability_name,enabled,effect_class,granted_by_user_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (extension_id,user_id,workspace_id,agent_kind,capability_name)
                    DO UPDATE SET enabled=EXCLUDED.enabled,effect_class=EXCLUDED.effect_class,
                                  granted_by_user_id=EXCLUDED.granted_by_user_id,updated_at=now()
                    """, (str(uuid4()),extension_id,target_user_id,workspace_id,agent.value,
                            capability_name,enabled,effect_class,actor_user_id),
                )
                self._event(cursor, extension_id, workspace_id, actor_user_id, "grant_changed", {"targetUserId": target_user_id, "agentKind": agent.value, "capabilityName": capability_name, "enabled": enabled})

    def list_grants(
        self, *, actor_user_id: str, target_user_id: str, workspace_id: str, extension_id: str,
    ) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                self._require_scope(cursor, user_id=target_user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT capability_name, agent_kind, enabled, effect_class
                    FROM vault_private.vault_extension_grants
                    WHERE extension_id=%s AND user_id=%s AND workspace_id=%s
                    ORDER BY capability_name, agent_kind
                    """,
                    (extension_id, target_user_id, workspace_id),
                )
                return tuple(
                    {
                        "capabilityName": str(row[0]),
                        "agentKind": str(row[1]),
                        "enabled": bool(row[2]),
                        "effectClass": str(row[3]) if row[3] is not None else None,
                    }
                    for row in cursor.fetchall()
                )

    def granted(self, *, user_id: str, workspace_id: str, extension_id: str, agent: AgentKind, capability_name: str = "") -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT 1 FROM vault_private.vault_extension_grants g
                    JOIN vault_private.vault_extensions e ON e.extension_id=g.extension_id
                    JOIN vault_private.vault_extension_runtime_settings s ON s.setting_key='third_party_extensions'
                    WHERE g.extension_id=%s AND g.user_id=%s AND g.workspace_id=%s
                      AND g.agent_kind=%s AND g.capability_name=%s AND g.enabled=true
                      AND e.state='enabled' AND s.enabled=true
                    """, (extension_id,user_id,workspace_id,agent.value,capability_name),
                )
                return cursor.fetchone() is not None

    def set_safe_mode(self, *, actor_user_id: str, workspace_id: str, enabled: bool) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute("UPDATE vault_private.vault_extension_runtime_settings SET enabled=%s,changed_by_user_id=%s,updated_at=now() WHERE setting_key='third_party_extensions'", (not enabled,actor_user_id))
                self._event(cursor, None, workspace_id, actor_user_id, "safe_mode_changed", {"enabled": enabled})

    def safe_mode(self, *, actor_user_id: str, workspace_id: str) -> bool:
        """Return the durable owner-controlled extension gate, never a UI guess."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(
                    cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True,
                )
                cursor.execute(
                    "SELECT enabled FROM vault_private.vault_extension_runtime_settings "
                    "WHERE setting_key='third_party_extensions'"
                )
                row = cursor.fetchone()
                return row is None or not bool(row[0])

    def granted_extensions(
        self, *, user_id: str, workspace_id: str, agent: AgentKind,
        kind: ExtensionKind, capability_prefix: str = "",
    ) -> tuple[tuple[ExtensionRecord, str, str | None], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT e.extension_id,e.kind,e.identity,e.display_name,e.version,e.description,
                           e.content_hash,e.state,e.installed_by_user_id,e.installed_in_workspace_id,
                           e.previous_content_hash,e.configuration_json,g.capability_name,g.effect_class
                    FROM vault_private.vault_extension_grants g
                    JOIN vault_private.vault_extensions e ON e.extension_id=g.extension_id
                    JOIN vault_private.vault_extension_runtime_settings s ON s.setting_key='third_party_extensions'
                    WHERE g.user_id=%s AND g.workspace_id=%s AND g.agent_kind=%s AND g.enabled=true
                      AND e.kind=%s AND e.state='enabled' AND s.enabled=true
                      AND g.capability_name LIKE %s
                    ORDER BY e.identity,g.capability_name
                    """, (user_id,workspace_id,agent.value,kind.value,f"{capability_prefix}%"),
                )
                return tuple((_record(row[:12]),str(row[12]),row[13]) for row in cursor.fetchall())

    def replace_mcp_tools(
        self, *, actor_user_id: str, workspace_id: str, extension_id: str,
        tools: tuple[tuple[str, str | None, str, dict[str, object], dict[str, object] | None, str], ...],
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute("SELECT 1 FROM vault_private.vault_extensions WHERE extension_id=%s AND installed_in_workspace_id=%s AND kind='mcp' AND state='enabled' FOR UPDATE", (extension_id,workspace_id))
                if cursor.fetchone() is None:
                    raise ExtensionNotFoundError("enabled MCP connection is unavailable")
                cursor.execute("DELETE FROM vault_private.vault_mcp_tools WHERE extension_id=%s", (extension_id,))
                for name,title,description,input_schema,output_schema,discovery_hash in tools:
                    cursor.execute(
                        """INSERT INTO vault_private.vault_mcp_tools
                           (extension_id,tool_name,title,description,input_schema_json,output_schema_json,discovery_hash)
                           VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)""",
                        (extension_id,name,title,description,json.dumps(input_schema,separators=(",", ":")),
                         json.dumps(output_schema,separators=(",", ":")) if output_schema is not None else None,
                         discovery_hash),
                    )
                self._event(cursor, extension_id, workspace_id, actor_user_id, "mcp_discovered", {"toolCount": len(tools)})

    def granted_mcp_tools(
        self, *, user_id: str, workspace_id: str, agent: AgentKind, extension_id: str,
    ) -> tuple[tuple[str, str, dict[str, object], dict[str, object] | None, str], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT t.tool_name,t.description,t.input_schema_json,t.output_schema_json,g.effect_class
                    FROM vault_private.vault_mcp_tools t
                    JOIN vault_private.vault_extensions e ON e.extension_id=t.extension_id
                    JOIN vault_private.vault_extension_grants g
                      ON g.extension_id=e.extension_id AND g.capability_name=t.tool_name
                    JOIN vault_private.vault_extension_runtime_settings s ON s.setting_key='third_party_extensions'
                    WHERE e.extension_id=%s AND e.installed_in_workspace_id=%s AND e.state='enabled'
                      AND g.user_id=%s AND g.workspace_id=%s AND g.agent_kind=%s AND g.enabled=true
                      AND g.effect_class IS NOT NULL AND s.enabled=true
                    ORDER BY t.tool_name
                    """, (extension_id,workspace_id,user_id,workspace_id,agent.value),
                )
                return tuple((str(row[0]),str(row[1]),row[2],row[3],str(row[4])) for row in cursor.fetchall())

    @staticmethod
    def _event(cursor: Any, extension_id: str | None, workspace_id: str, actor_user_id: str, event_type: str, detail: dict[str, object]) -> None:
        cursor.execute("INSERT INTO vault_private.vault_extension_events (event_id,extension_id,workspace_id,actor_user_id,event_type,detail_json) VALUES (%s,%s,%s,%s,%s,%s::jsonb)", (str(uuid4()),extension_id,workspace_id,actor_user_id,event_type,json.dumps(detail,separators=(",", ":"))))

    def record_event(
        self, *, actor_user_id: str, workspace_id: str, extension_id: str,
        event_type: str, detail: dict[str, object],
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                self._event(cursor, extension_id, workspace_id, actor_user_id, event_type, detail)
            connection.commit()


def _record(row: Any) -> ExtensionRecord:
    configuration = row[11] if isinstance(row[11], dict) else json.loads(row[11])
    return ExtensionRecord(str(row[0]),ExtensionKind(str(row[1])),str(row[2]),str(row[3]),row[4],row[5],str(row[6]),ExtensionState(str(row[7])),str(row[8]),str(row[9]),row[10],configuration)
