from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import uuid4
from psycopg.types.json import Jsonb

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.voice.repository import VoiceAuthorizationError, VoiceSessionRepository


class ToolGrantError(RuntimeError):
    code = "tool_grant_denied"


class ToolInvocationConflictError(RuntimeError):
    code = "tool_invocation_conflict"


@dataclass(frozen=True, slots=True)
class InvocationClaim:
    invocation_id: str
    disposition: str
    recovered_result: ToolInvocationResult | None = None


def canonical_arguments_sha256(arguments: dict[str, object]) -> str:
    canonical = json.dumps(
        arguments, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


_SENSITIVE_ARGUMENT_PARTS = ("password", "token", "secret", "credential", "authorization", "api_key", "apikey", "body", "content", "attachment")


def redact_tool_arguments(value: object, *, depth: int = 0) -> object:
    if depth > 5: return "[truncated]"
    if isinstance(value, dict):
        return {str(key)[:120]: ("[redacted]" if any(part in str(key).casefold().replace("-", "_") for part in _SENSITIVE_ARGUMENT_PARTS) else redact_tool_arguments(item, depth=depth + 1)) for key, item in list(value.items())[:100]}
    if isinstance(value, list): return [redact_tool_arguments(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str): return value[:1000]
    return value if value is None or isinstance(value, (bool, int, float)) else str(value)[:1000]


class LocalToolAuthority:
    def __init__(
        self,
        *,
        database_url: str,
        connector: Callable[..., AbstractContextManager[Any]] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connector = connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg

        return psycopg.connect(self._database_url, connect_timeout=5)

    def set_grant(
        self,
        *,
        actor_user_id: str,
        workspace_id: str,
        tool_name: str,
        effect_class: str,
        voice_enabled: bool,
        background_enabled: bool,
        user_id: str | None = None,
    ) -> None:
        if effect_class not in {"read", "write", "delete"}:
            raise ValueError("unsupported tool effect")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1 FROM vault_private.local_workspace_memberships
                    WHERE workspace_id=%s AND user_id=%s AND membership_type='owner' AND status='active'
                    """,
                    (workspace_id, actor_user_id),
                )
                if cursor.fetchone() is None:
                    raise ToolGrantError("Workspace owner authority is required.")
                if user_id is not None:
                    cursor.execute(
                        """
                        SELECT 1 FROM vault_private.local_workspace_memberships
                        WHERE workspace_id=%s AND user_id=%s AND status='active'
                        """,
                        (workspace_id, user_id),
                    )
                    if cursor.fetchone() is None:
                        raise ToolGrantError("Grant target requires active workspace membership.")
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_voice_tool_grants
                      (grant_id,workspace_id,user_id,tool_name,effect_class,
                       voice_enabled,background_enabled,status,revoked_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'active',NULL)
                    ON CONFLICT (workspace_id,user_id,tool_name) DO UPDATE SET
                      effect_class=EXCLUDED.effect_class,
                      voice_enabled=EXCLUDED.voice_enabled,
                      background_enabled=EXCLUDED.background_enabled,
                      status='active',revoked_at=NULL
                    """,
                    (
                        str(uuid4()), workspace_id, user_id, tool_name, effect_class,
                        voice_enabled, background_enabled,
                    ),
                )

    def ensure_builtin_grants(
        self, *, user_id: str, workspace_id: str,
        definitions: tuple[ToolDefinition, ...],
    ) -> None:
        """Apply R1's built-in bootstrap policy without granting extensions."""
        builtins = tuple(item for item in definitions if item.tool_id.startswith("builtin."))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT 1 FROM vault_private.local_workspace_memberships
                       WHERE workspace_id=%s AND user_id=%s AND status='active'""",
                    (workspace_id, user_id),
                )
                if cursor.fetchone() is None:
                    raise ToolGrantError("Active workspace membership is required.")
                for definition in builtins:
                    cursor.execute(
                        """
                        INSERT INTO vault_private.vault_voice_tool_grants
                          (grant_id,workspace_id,user_id,tool_name,effect_class,
                           voice_enabled,background_enabled,status,revoked_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,'active',NULL)
                        ON CONFLICT (workspace_id,user_id,tool_name) DO NOTHING
                        """,
                        (
                            str(uuid4()), workspace_id, user_id, definition.name,
                            definition.effect_class,
                            AgentKind.VOICE in definition.audiences,
                            AgentKind.BACKGROUND in definition.audiences,
                        ),
                    )

    def revoke_grant(
        self, *, actor_user_id: str, workspace_id: str, tool_name: str, user_id: str | None = None
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1 FROM vault_private.local_workspace_memberships
                    WHERE workspace_id=%s AND user_id=%s AND membership_type='owner' AND status='active'
                    """,
                    (workspace_id, actor_user_id),
                )
                if cursor.fetchone() is None:
                    raise ToolGrantError("Workspace owner authority is required.")
                cursor.execute(
                    """
                    UPDATE vault_private.vault_voice_tool_grants
                    SET status='revoked',revoked_at=now(),voice_enabled=false,background_enabled=false
                    WHERE workspace_id=%s AND user_id IS NOT DISTINCT FROM %s AND tool_name=%s
                    """,
                    (workspace_id, user_id, tool_name),
                )

    def authorize(self, definition: ToolDefinition, context: ToolInvocationContext) -> bool:
        # Imported capability definitions are projected only into one user/workspace
        # and their handlers recheck the durable extension grant at invocation.
        # Do not require a second, unrelated built-in-tool grant for that same scope.
        if not definition.tool_id.startswith("builtin."):
            return (
                definition.scope_user_id == context.user_id
                and definition.scope_workspace_id == context.workspace_id
            )
        audience_column = "voice_enabled" if context.agent is AgentKind.VOICE else "background_enabled"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT 1
                    FROM vault_private.vault_voice_tool_grants g
                    JOIN vault_private.local_workspace_memberships m
                      ON m.workspace_id=g.workspace_id AND m.user_id=%s AND m.status='active'
                    JOIN vault_private.local_sessions s
                      ON s.session_id=%s AND s.user_id=%s AND s.active_workspace_id=g.workspace_id
                     AND s.status='active' AND s.expires_at>now()
                    WHERE g.workspace_id=%s AND g.tool_name=%s AND g.effect_class=%s
                      AND g.status='active' AND g.{audience_column}=true
                      AND (g.user_id IS NULL OR g.user_id=%s)
                    """,
                    (
                        context.user_id, context.local_session_id, context.user_id,
                        context.workspace_id, definition.name, definition.effect_class,
                        context.user_id,
                    ),
                )
                return cursor.fetchone() is not None

    def prepare_voice_invocation(
        self,
        *,
        context: ToolInvocationContext,
        definition: ToolDefinition,
        arguments: dict[str, object],
    ) -> InvocationClaim:
        if context.agent is not AgentKind.VOICE or not context.voice_session_id:
            raise ToolInvocationConflictError("Voice invocation requires the fixed Voice Agent session.")
        arguments_hash = canonical_arguments_sha256(arguments)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                VoiceSessionRepository._require_authority(
                    cursor, user_id=context.user_id, workspace_id=context.workspace_id,
                    local_session_id=context.local_session_id,
                )
                VoiceSessionRepository._session_cursor(
                    cursor, user_id=context.user_id, workspace_id=context.workspace_id,
                    local_session_id=context.local_session_id,
                    voice_session_id=context.voice_session_id, require_open=True,
                )
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_voice_tool_invocations
                      (invocation_id,voice_session_id,user_id,workspace_id,tool_call_id,
                       tool_name,effect_class,arguments_sha256,arguments_redacted,state)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'prepared')
                    ON CONFLICT (voice_session_id,tool_call_id) DO NOTHING
                    RETURNING invocation_id
                    """,
                    (
                        str(uuid4()), context.voice_session_id, context.user_id,
                        context.workspace_id, context.tool_call_id, definition.name,
                        definition.effect_class, arguments_hash,
                        Jsonb(redact_tool_arguments(arguments)),
                    ),
                )
                inserted = cursor.fetchone()
                if inserted is not None:
                    invocation_id = str(inserted[0])
                    cursor.execute(
                        """
                        UPDATE vault_private.vault_voice_tool_invocations
                        SET state='invoking',attempt_count=1,updated_at=now()
                        WHERE invocation_id=%s
                        """,
                        (invocation_id,),
                    )
                    return InvocationClaim(invocation_id, "acquired")
                cursor.execute(
                    """
                    SELECT invocation_id,tool_name,effect_class,arguments_sha256,state
                    FROM vault_private.vault_voice_tool_invocations
                    WHERE voice_session_id=%s AND tool_call_id=%s FOR UPDATE
                    """,
                    (context.voice_session_id, context.tool_call_id),
                )
                prior = cursor.fetchone()
                if prior[1:4] != (definition.name, definition.effect_class, arguments_hash):
                    raise ToolInvocationConflictError("Tool call identity was replayed with different input.")
                if prior[4] == "succeeded":
                    cursor.execute(
                        """
                        SELECT result_json FROM vault_private.vault_voice_tool_results
                        WHERE invocation_id=%s AND user_id=%s AND workspace_id=%s
                        """,
                        (prior[0], context.user_id, context.workspace_id),
                    )
                    result_row = cursor.fetchone()
                    if result_row is None:
                        raise ToolInvocationConflictError("Completed tool result is unavailable.")
                    data = result_row[0]
                    return InvocationClaim(
                        str(prior[0]), "succeeded",
                        ToolInvocationResult(
                            text=str(data["text"]), structured_content=data.get("structuredContent"),
                            is_error=bool(data.get("isError", False)),
                            provider_session_update=data.get("providerSessionUpdate"),
                        ),
                    )
                return InvocationClaim(str(prior[0]), str(prior[4]))

    def complete(
        self,
        *,
        claim: InvocationClaim,
        context: ToolInvocationContext,
        result: ToolInvocationResult,
    ) -> None:
        payload = {
            "text": result.text,
            "structuredContent": result.structured_content,
            "isError": result.is_error,
            "providerSessionUpdate": result.provider_session_update,
        }
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_voice_tool_results
                      (invocation_id,user_id,workspace_id,result_json)
                    VALUES (%s,%s,%s,%s::jsonb)
                    """,
                    (
                        claim.invocation_id, context.user_id, context.workspace_id,
                        json.dumps(payload, separators=(",", ":")),
                    ),
                )
                cursor.execute(
                    """
                    UPDATE vault_private.vault_voice_tool_invocations
                    SET state='succeeded',completed_at=now(),updated_at=now()
                    WHERE invocation_id=%s AND state='invoking'
                    """,
                    (claim.invocation_id,),
                )

    def fail(self, *, claim: InvocationClaim, effect_class: str, failure_code: str) -> None:
        state = "failed" if effect_class == "read" else "effect_unknown"
        completed = "now()" if state == "effect_unknown" else "NULL"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE vault_private.vault_voice_tool_invocations
                    SET state=%s,failure_code=%s,completed_at={completed},updated_at=now()
                    WHERE invocation_id=%s AND state='invoking'
                    """,
                    (state, failure_code[:120], claim.invocation_id),
                )


class VoiceToolRuntime:
    def __init__(self, *, catalog: ToolCatalog, authority: LocalToolAuthority, voice_modes=None) -> None:
        self._catalog = catalog
        self._authority = authority
        self._voice_modes = voice_modes

    def invoke(
        self, *, name: str, arguments: dict[str, object], context: ToolInvocationContext
    ) -> ToolInvocationResult:
        definitions = {item.name: item for item in self._catalog.definitions_for(
            AgentKind.VOICE, user_id=context.user_id, workspace_id=context.workspace_id,
        )}
        definition = definitions.get(name)
        if definition is None or not self._authority.authorize(definition, context):
            return ToolInvocationResult("Tool is not granted.", is_error=True)
        if self._voice_modes is not None and not self._voice_modes.allows(name, context):
            return ToolInvocationResult("Tool is not available in the current Voice profile.", is_error=True)
        claim = self._authority.prepare_voice_invocation(
            context=context, definition=definition, arguments=arguments
        )
        if claim.disposition == "succeeded" and claim.recovered_result is not None:
            return claim.recovered_result
        if claim.disposition != "acquired":
            return ToolInvocationResult("Tool call is already active or requires review.", is_error=True)
        try:
            result = self._catalog.invoke(name, arguments, context=context)
        except Exception as exc:
            self._authority.fail(
                claim=claim, effect_class=definition.effect_class,
                failure_code=type(exc).__name__.lower(),
            )
            raise
        self._authority.complete(claim=claim, context=context, result=result)
        return result

    def definitions(
        self, *, user_id: str, workspace_id: str,
    ) -> tuple[ToolDefinition, ...]:
        """Management projection of tools available in this exact local scope."""
        return self._catalog.definitions_for(
            AgentKind.VOICE, user_id=user_id, workspace_id=workspace_id,
        )
