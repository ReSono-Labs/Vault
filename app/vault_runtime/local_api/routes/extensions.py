"""Extensions (skills, plugins, MCP) and built-in plugins."""
from __future__ import annotations

import base64
import binascii
from typing import Any, Mapping
from urllib.parse import SplitResult, parse_qs, urlencode

from app.vault_runtime.tools.strict_json import STRICT_JSON_MAX_BYTES
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.extensions.models import ExtensionAudience, ExtensionKind, ExtensionState
from app.vault_runtime.extensions.mcp_rules import merge_headers
from app.vault_runtime.extensions.vault_manifest import validate_settings
from app.vault_runtime.extensions.mcp_package_manifest import validate_mcp_package_settings
from app.vault_runtime.extensions.mcp_runtime import McpRuntimeError
from app.vault_runtime.extensions.mcp_accounts import CALLBACK_PATH, is_hosted
from app.vault_runtime.extensions.mcp_oauth import McpSignInError
from .common import (
    LocalApiResponse,
    _csrf_token,
    _json_object,
    _optional_text,
    _required_bool,
    _required_text,
    _session_token,
)


class ExtensionRoutes:
    """VaultLocalApiApp routes: extensions (skills, plugins, mcp) and built-in plugins."""

    def _route_extensions(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            if path == CALLBACK_PATH and method.upper() == "GET":
                return self._mcp_sign_in_callback(query=target_parts.query, headers=headers)
            return self._handle_extensions(
                method=method.upper(), path=path, headers=headers, body=body,
            )
        except Exception as exc:
            code = getattr(exc, "code", "extension_request_failed")
            if code == "extension_not_found":
                status = 404
            elif code == "extension_conflict":
                status = 409
            elif isinstance(exc, (ValueError, McpSignInError)):
                status = 400
            else:
                status = 403
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _mcp_sign_in_callback(self, *, query: str, headers: Mapping[str, str]) -> LocalApiResponse:
        """The browser returns here from the sign-in server. The session must be the person
        who started the sign-in; the state ties the code to that start."""
        values = parse_qs(query, keep_blank_values=True)
        first = lambda name: (values.get(name) or [None])[0]  # noqa: E731
        try:
            if self._identity_service is None or self._mcp_accounts is None:
                raise RuntimeError("MCP sign-in is unavailable.")
            principal = self._identity_service.authenticate(session_token=_session_token(headers))
            extension_id = self._mcp_accounts.complete_sign_in(
                user_id=principal.user_id, state=first("state") or "", code=first("code"),
                iss=first("iss"), error=first("error"),
            )
            target = "/browser-voice.html?" + urlencode({"mcpSignIn": "connected", "extension": extension_id})
        except Exception as exc:
            reason = getattr(exc, "code", "sign_in_failed")
            target = "/browser-voice.html?" + urlencode({"mcpSignIn": "failed", "reason": str(reason)[:64]})
        return LocalApiResponse(303, {"status": "redirect"}, (("Location", target),))

    def _mcp_account(self, *, method: str, principal: Any, extension_id: str,
                     payload: dict[str, Any] | None) -> LocalApiResponse:
        accounts = self._mcp_accounts
        if accounts is None:
            raise RuntimeError("MCP sign-in is unavailable.")
        scope = {"workspace_id": principal.workspace_id, "extension_id": extension_id}
        if method == "GET":
            return LocalApiResponse(200, accounts.status(user_id=principal.user_id, **scope))
        assert payload is not None
        action = _required_text(payload, "action")
        if action == "sign-in":
            return LocalApiResponse(200, accounts.start_sign_in(
                user_id=principal.user_id, redirect_uri=_required_text(payload, "redirectUri"), **scope))
        if action == "disconnect":
            accounts.disconnect(user_id=principal.user_id, **scope)
        elif action == "share":
            accounts.set_shared(actor_user_id=principal.user_id, shared=_required_bool(payload, "shared"), **scope)
        elif action == "share-grant":
            accounts.set_shared_grant(actor_user_id=principal.user_id, target_user_id=_required_text(payload, "userId"),
                                      granted=_required_bool(payload, "granted"), **scope)
        elif action == "client":
            return LocalApiResponse(200, accounts.set_manual_client(
                actor_user_id=principal.user_id, client_id=_required_text(payload, "clientId"),
                client_secret=_optional_text(payload, "clientSecret"), **scope))
        else:
            raise ValueError("Account action is invalid.")
        return LocalApiResponse(200, accounts.status(user_id=principal.user_id, **scope))

    def _handle_extensions(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity = self._identity_service
        repository = self._extensions
        imports = self._extension_imports
        if identity is None or repository is None:
            raise RuntimeError("Local extensions are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/extensions":
            return LocalApiResponse(200, {"items": [
                _extension_payload(item) for item in repository.list_installed(
                    actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                )
            ]})
        if method == "GET" and path.startswith("/extensions/") and path.endswith("/connections"):
            extension_id = path.removeprefix("/extensions/").removesuffix("/connections").strip("/")
            repository.by_id(
                actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                extension_id=extension_id, owner=True,
            )
            return LocalApiResponse(200, {"items": [
                _extension_payload(item) for item in repository.managed_children(
                    actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                    plugin_id=extension_id,
                )
            ]})
        if method == "GET" and path.startswith("/extensions/") and path.endswith("/grants"):
            extension_id = path.removeprefix("/extensions/").removesuffix("/grants").strip("/")
            repository.by_id(
                actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                extension_id=extension_id, owner=True,
            )
            return LocalApiResponse(200, {"items": list(repository.list_grants(
                actor_user_id=principal.user_id,
                target_user_id=principal.user_id,
                workspace_id=principal.workspace_id,
                extension_id=extension_id,
            ))})
        if method == "GET" and path.startswith("/extensions/") and path.endswith("/account"):
            extension_id = path.removeprefix("/extensions/").removesuffix("/account").strip("/")
            return self._mcp_account(method="GET", principal=principal, extension_id=extension_id, payload=None)
        if method == "GET" and path == "/extensions/runtime":
            # Owner-only (safe_mode checks device-owner scope): names blocked because
            # installs in different workspaces share name-keyed storage.
            return LocalApiResponse(200, {"safeMode": repository.safe_mode(
                actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
            ), "scope": "device", "storageConflicts": list(repository.storage_conflicts())})
        if method not in {"POST", "DELETE"}:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        max_json_bytes = STRICT_JSON_MAX_BYTES
        if path in {
            "/extensions/skills/preflight",
            "/extensions/plugins/preflight",
            "/extensions/mcp/preflight",
            "/extensions/mcp-packages/preflight",
        }:
            max_json_bytes = self._max_body_bytes
        payload = _json_object(body, max_bytes=max_json_bytes)
        if path in {
            "/extensions/skills/preflight", "/extensions/plugins/preflight",
            "/extensions/mcp/preflight", "/extensions/mcp-packages/preflight",
        }:
            if imports is None:
                raise RuntimeError("Local extension imports are unavailable.")
            if path == "/extensions/mcp-packages/preflight":
                document = _base64_bytes(payload, "archiveBase64")
                audience = ExtensionAudience.parse(payload.get("audience"))
                preview = imports.preflight_mcp_package(
                    document, _required_text(payload, "filename"), actor_user_id=principal.user_id,
                    workspace_id=principal.workspace_id, audience=audience,
                )
                return LocalApiResponse(200, _preflight_payload(preview))
            document = _base64_bytes(payload, "archiveBase64" if path != "/extensions/mcp/preflight" else "documentBase64")
            audience = ExtensionAudience.parse(payload.get("audience"))
            if path == "/extensions/skills/preflight":
                preview = imports.preflight_skill(
                    document, _required_text(payload, "filename"), actor_user_id=principal.user_id,
                    workspace_id=principal.workspace_id, audience=audience,
                )
                return LocalApiResponse(200, _preflight_payload(preview))
            if path == "/extensions/plugins/preflight":
                preview = imports.preflight_plugin(
                    document, _required_text(payload, "filename"), actor_user_id=principal.user_id,
                    workspace_id=principal.workspace_id, audience=audience,
                )
                return LocalApiResponse(200, _preflight_payload(preview))
            previews = imports.preflight_mcp(
                document, actor_user_id=principal.user_id,
                workspace_id=principal.workspace_id, audience=audience,
            )
            return LocalApiResponse(200, {"items": [_preflight_payload(item) for item in previews]})
        if path == "/extensions/folder-preflight":
            # Import from a folder the person was given under Settings -> Folders (not a host
            # file browser): resolved inside that folder, then snapshotted into quarantine.
            if imports is None or self._folders is None:
                raise RuntimeError("Folder import is unavailable.")
            source = self._folders.resolve_access_path(
                principal=principal, grant_id=_required_text(payload, "grantId"),
                path=_optional_text(payload, "path"),
            )
            preview = imports.preflight_folder(
                source, kind=_required_text(payload, "kind"), actor_user_id=principal.user_id,
                workspace_id=principal.workspace_id, audience=ExtensionAudience.parse(payload.get("audience")),
            )
            return LocalApiResponse(200, _preflight_payload(preview))
        if path == "/extensions/confirm":
            if imports is None:
                raise RuntimeError("Local extension imports are unavailable.")
            kind = _required_text(payload, "kind")
            arguments = dict(
                token=_required_text(payload, "token"), actor_user_id=principal.user_id,
                workspace_id=principal.workspace_id, replace=_required_bool(payload, "replace"),
            )
            if kind == "mcp-package":
                arguments["replace_migration"] = bool(payload.get("replaceMigration"))
                record = imports.confirm_mcp_package(**arguments)
            elif kind == "skill":
                record = imports.confirm_skill(**arguments)
            elif kind == "plugin":
                arguments["replace_migration"] = bool(payload.get("replaceMigration"))
                arguments["replace_workspace_import"] = bool(payload.get("replaceWorkspaceImport"))
                folder_id = payload.get("localShareFolderId")
                if folder_id is not None:
                    if not isinstance(folder_id, str) or not folder_id.strip():
                        raise ValueError("localShareFolderId must be a folder id.")
                    from app.vault_runtime.extensions.service import LocalShareRegistration
                    arguments["local_share"] = LocalShareRegistration(
                        folder_id=folder_id.strip(),
                        created_during_import=bool(payload.get("localShareCreatedDuringImport")),
                    )
                record = imports.confirm_plugin(**arguments)
            elif kind == "mcp":
                record = imports.confirm_mcp(**arguments)
            else:
                raise ValueError("Extension kind is invalid.")
            return LocalApiResponse(201, _extension_payload(record))
        if path == "/extensions/safe-mode":
            enabled = _required_bool(payload, "enabled")
            was_enabled = repository.safe_mode(
                actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
            )
            repository.set_safe_mode(
                actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                enabled=enabled,
            )
            # Safe mode is device-wide: it covers every workspace's extensions.
            if enabled:
                if self._mcp_lifecycle is not None:
                    self._mcp_lifecycle.enter_safe_mode()
                if imports is not None:
                    imports.enter_safe_mode()
            elif was_enabled and imports is not None:
                imports.leave_safe_mode()
            return LocalApiResponse(200, {"safeMode": enabled, "scope": "device"})
        if path.startswith("/extensions/"):
            suffix = path.removeprefix("/extensions/")
            extension_id, _, operation = suffix.partition("/")
            if not extension_id or operation not in {"state", "grants", "credentials", "settings", "discover", "account"}:
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
            if operation == "account":
                return self._mcp_account(method="POST", principal=principal, extension_id=extension_id, payload=payload)
            if operation == "state":
                current = repository.by_id(
                    actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                    extension_id=extension_id, owner=True,
                )
                managed_ids = tuple(child.extension_id for child in repository.managed_children(
                    actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                    plugin_id=extension_id,
                )) if current.kind is ExtensionKind.PLUGIN else ()
                state = ExtensionState(_required_text(payload, "state"))
                try:
                    record = imports.set_state(
                        actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                        extension_id=extension_id, state=state,
                    ) if imports is not None else repository.set_state(
                        actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                        extension_id=extension_id, state=state,
                    )
                except McpRuntimeError as exc:
                    return LocalApiResponse(409, {"error": {"code": "mcp_runtime_error", "message": str(exc)}})
                if state is not ExtensionState.ENABLED and self._mcp_lifecycle is not None:
                    self._mcp_lifecycle.remove_extension(extension_id)
                    for managed_id in managed_ids:
                        self._mcp_lifecycle.remove_extension(managed_id)
                return LocalApiResponse(200, _extension_payload(record))
            if operation == "grants":
                target_user_id = _required_text(payload, "targetUserId")
                grant_agent = AgentKind(_required_text(payload, "agentKind"))
                repository.set_grant(
                    actor_user_id=principal.user_id,
                    target_user_id=target_user_id,
                    workspace_id=principal.workspace_id, extension_id=extension_id,
                    agent=grant_agent,
                    capability_name=str(payload.get("capabilityName", "")),
                    enabled=_required_bool(payload, "enabled"),
                    effect_class=_optional_text(payload, "effectClass"),
                )
                if self._mcp_lifecycle is not None:
                    extension = repository.by_id(
                        actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                        extension_id=extension_id, owner=True,
                    )
                    if extension.kind is ExtensionKind.MCP:
                        self._mcp_lifecycle.project_scope(
                            user_id=target_user_id, workspace_id=principal.workspace_id,
                            agent=grant_agent, connection=extension,
                        )
                return LocalApiResponse(200, {"status": "grant_updated"})
            if operation == "discover":
                if self._mcp_lifecycle is None:
                    raise RuntimeError("Plugin tool discovery is unavailable.")
                extension = repository.by_id(
                    actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                    extension_id=extension_id, owner=True,
                )
                context = ToolInvocationContext(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                    agent=AgentKind.VOICE, tool_call_id=f"discover:{extension_id}",
                    local_session_id=principal.session_id,
                )
                names = self._mcp_lifecycle.discover(
                    actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                    connection=extension, client=self._mcp_lifecycle.client_for(extension, context),
                )
                return LocalApiResponse(200, {"items": list(names)})
            if operation == "settings":
                extension = repository.by_id(
                    actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                    extension_id=extension_id, owner=True,
                )
                schema = extension.configuration.get("configurationSchema")
                if extension.kind is ExtensionKind.PLUGIN:
                    if not isinstance(schema, dict):
                        raise ValueError("This Plugin does not have settings.")
                    settings, secret_headers = validate_settings(schema, payload.get("values"))
                    for header, value in list(secret_headers.items()):
                        if header.lower() == "authorization" and value and not value.lower().startswith("bearer "):
                            secret_headers[header] = f"Bearer {value}"
                elif extension.kind is ExtensionKind.MCP:
                    if extension.configuration.get("packageType") != "hosted" or not isinstance(schema, dict):
                        raise ValueError("This MCP package does not have settings.")
                    settings, secret_headers = validate_mcp_package_settings(schema, payload.get("values"))
                    for header, value in list(secret_headers.items()):
                        if header.lower() == "authorization" and value and not value.lower().startswith("bearer "):
                            secret_headers[header] = f"Bearer {value}"
                else:
                    raise ValueError("This extension does not have settings.")
                record = repository.update_configuration(
                    actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                    extension_id=extension_id,
                    configuration={**extension.configuration, "settings": settings},
                )
                if secret_headers:
                    if self._extension_secrets is None:
                        raise RuntimeError("Local extension credentials are unavailable.")
                    secret_targets: tuple[str, ...]
                    if extension.kind is ExtensionKind.PLUGIN:
                        children = repository.managed_children(
                            actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                            plugin_id=extension_id,
                        )
                        if not children:
                            raise ValueError("This plugin has no MCP connection to store the token on. Re-import the plugin or import mcp.json on the MCP tab.")
                        secret_targets = tuple(child.extension_id for child in children)
                    else:
                        secret_targets = (extension_id,)
                    for target_id in secret_targets:
                        self._store_credential_headers(principal, target_id, secret_headers)
                return LocalApiResponse(200, _extension_payload(record))
            if self._extension_secrets is None:
                raise RuntimeError("Local extension credentials are unavailable.")
            secret_headers = payload.get("headers")
            if not isinstance(secret_headers, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in secret_headers.items()
            ):
                raise ValueError("headers must map strings to strings")
            self._store_credential_headers(principal, extension_id, secret_headers, replace=True)
            return LocalApiResponse(200, {"status": "credentials_updated"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _store_credential_headers(self, principal: Any, extension_id: str, secret_headers: dict[str, str],
                                  *, replace: bool = False) -> None:
        """A hosted package's service secret (device owner), or the caller's own credential
        for a remote connection; other people never use it unless the owner shares it."""
        record = self._extensions.by_id(
            actor_user_id=principal.user_id, workspace_id=principal.workspace_id, extension_id=extension_id,
        )
        if is_hosted(record.configuration):
            if self._extension_secrets is None:
                raise RuntimeError("Local extension credentials are unavailable.")
            existing = {} if replace else dict(self._extension_secrets.resolve_headers(
                user_id=principal.user_id, workspace_id=principal.workspace_id, extension_id=extension_id,
            ))
            self._extension_secrets.set_headers(
                actor_user_id=principal.user_id, workspace_id=principal.workspace_id, extension_id=extension_id,
                # Case-insensitive: a newer "Authorization" replaces "authorization".
                headers=merge_headers(existing, secret_headers),
            )
            return
        if self._mcp_accounts is None:
            raise RuntimeError("Local extension credentials are unavailable.")
        self._mcp_accounts.set_personal_headers(
            user_id=principal.user_id, workspace_id=principal.workspace_id, extension_id=extension_id,
            headers=secret_headers,
        )

    def _route_builtin_plugins(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_builtin_plugins(method=method.upper(), path=path, headers=headers, body=body)
        except Exception as exc:
            return LocalApiResponse(400 if isinstance(exc, ValueError) else 403, {"error": {"code": "builtin_plugin_request_failed", "message": str(exc)}})

    def _handle_builtin_plugins(self, *, method: str, path: str, headers: Mapping[str, str], body: bytes) -> LocalApiResponse:
        identity, repository = self._identity_service, self._builtin_plugins
        if identity is None or repository is None:
            raise RuntimeError("Built-in plugins are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/builtin-plugins":
            return LocalApiResponse(200, {"items": repository.list(account_id=principal.user_id, workspace_id=principal.workspace_id)})
        key = path.removeprefix("/builtin-plugins/").strip("/")
        if method == "GET" and key:
            return LocalApiResponse(200, repository.get(account_id=principal.user_id, workspace_id=principal.workspace_id, plugin_key=key))
        if method == "POST" and key:
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            payload = _json_object(body)
            configuration = payload.get("configuration")
            if configuration is not None and not isinstance(configuration, dict):
                raise ValueError("Plugin settings are invalid.")
            enabled = payload.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                raise ValueError("Plugin status is invalid.")
            return LocalApiResponse(200, repository.update(account_id=principal.user_id, workspace_id=principal.workspace_id, plugin_key=key, enabled=enabled, configuration=configuration))
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})


def _base64_bytes(payload: Mapping[str, Any], key: str) -> bytes:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required.")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{key} must be valid base64.") from exc
    if not decoded:
        raise ValueError(f"{key} cannot be empty.")
    return decoded


def _preflight_payload(preview) -> dict[str, Any]:
    payload = {
        "token": preview.token, "kind": preview.kind.value,
        "identity": preview.identity, "candidateHash": preview.candidate_hash,
        "replacement": preview.current_hash is not None,
        "audience": sorted(item.value for item in preview.audience.agents),
        "expiresAt": preview.expires_at.isoformat(),
    }
    diagnostics = getattr(preview.payload, "diagnostics", ())
    if diagnostics:
        payload["diagnostics"] = list(diagnostics)
    review = getattr(preview.payload, "review", None)
    if review is not None:
        payload["packageReview"] = {
            "risk": review.risk,
            "findings": [{
                "severity": item.severity, "code": item.code,
                "path": item.path, "message": item.message,
            } for item in review.findings],
        }
    assessment = getattr(preview.payload, "migration_assessment", None)
    if assessment is not None and assessment.declared:
        payload["migration"] = {
            "onConflict": assessment.on_conflict,
            "requiresDecision": assessment.requires_decision,
            "databaseConflict": assessment.database.target if assessment.database else None,
            "workspaceConflict": assessment.workspace.target if assessment.workspace else None,
        }
    workspace_assessment = getattr(preview.payload, "workspace_import_assessment", None)
    if workspace_assessment is not None and workspace_assessment.declared:
        payload["workspaceImport"] = {
            "onConflict": workspace_assessment.on_conflict,
            "requiresDecision": workspace_assessment.requires_decision,
            "conflicts": [item.target for item in workspace_assessment.conflicts],
        }
    vault_manifest = getattr(getattr(preview, "payload", None), "vault_manifest", None)
    local_share = getattr(vault_manifest, "local_share", None)
    if local_share is not None:
        payload["localShare"] = {
            "mountName": local_share.mount_name,
            "permission": local_share.permission,
            "label": local_share.label,
            "required": local_share.required,
            "permissionChoices": ["read", "write"],
        }
    return payload


def _extension_payload(record) -> dict[str, Any]:
    configuration: dict[str, Any] = {}
    if record.kind in {ExtensionKind.PLUGIN, ExtensionKind.MCP}:
        configuration = {
            key: value for key, value in record.configuration.items()
            if key not in {"endpoint", "url"} or record.configuration.get("packageType") == "hosted"
        }
        if record.configuration.get("packageType") == "hosted":
            runtime_status = record.configuration.get("runtimeStatus")
            if isinstance(runtime_status, dict):
                configuration["runtimeStatus"] = runtime_status
        elif record.kind is ExtensionKind.PLUGIN and record.configuration.get("supervised"):
            runtime_status = record.configuration.get("runtimeStatus")
            if isinstance(runtime_status, dict):
                configuration["runtimeStatus"] = runtime_status
            configuration["supervised"] = True
        migration_status = record.configuration.get("migrationStatus")
        if isinstance(migration_status, dict):
            configuration["migrationStatus"] = migration_status
        workspace_import_status = record.configuration.get("workspaceImportStatus")
        if isinstance(workspace_import_status, dict):
            configuration["workspaceImportStatus"] = workspace_import_status
        if record.configuration.get("packageData"):
            configuration["packageData"] = True
        local_share = record.configuration.get("localShare")
        if isinstance(local_share, dict):
            configuration["localShare"] = local_share
    return {
        "extensionId": record.extension_id, "kind": record.kind.value,
        "identity": record.identity, "displayName": record.display_name,
        "version": record.version, "description": record.description,
        "contentHash": record.content_hash, "state": record.state.value,
        "workspaceId": record.workspace_id,
        "configuration": configuration,
    }
