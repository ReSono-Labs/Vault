from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import httpx
import logging
from http.cookies import SimpleCookie
from hmac import compare_digest
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.parse import parse_qs, quote, urlsplit
from uuid import uuid4

from app.vault_runtime.local_identity.models import LocalPrincipal, LocalSessionTokens
from app.vault_runtime.local_identity.repository import LocalIdentityError
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.tools.strict_json import STRICT_JSON_MAX_BYTES, StrictJSONError, parse_json_object_bytes
from app.vault_runtime.background_agent.contracts import (
    AutonomyProfile,
    BackgroundRunRequest,
    ExecutionRecipe,
    RunLimits,
)
from app.vault_runtime.background_agent.repository import BackgroundRunRepository
from app.vault_runtime.background_agent.service import BackgroundAgentService
from app.vault_runtime.system_agents.inventory import SYSTEM_AGENT_INVENTORY
from app.vault_runtime.voice.provider import ProviderCredential, VoiceSessionCoordinator
from app.vault_runtime.voice.repository import VoiceSessionRepository
from app.vault_runtime.voice.tools import VoiceToolRuntime
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.voice.credentials import VoiceProviderCredentialStore
from app.vault_runtime.voice.oauth import ProviderOAuthService
from app.vault_runtime.voice.greeting import connect_greeting_event
from app.vault_runtime.voice.openai_realtime import uses_subscription_live_transport
from app.vault_runtime.email_runtime import LocalEmailRuntime
from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.session_tools.brokers.contacts import contacts_tool_result
from app.vault_runtime.calendar_runtime import LocalCalendarRuntime
from app.vault_runtime.extensions.models import ExtensionAudience, ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRepository
from app.vault_runtime.extensions.secrets import ExtensionSecretStore
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.extensions.mcp_lifecycle import McpLifecycle
from app.vault_runtime.extensions.vault_manifest import validate_settings
from app.vault_runtime.extensions.mcp_package_manifest import validate_mcp_package_settings
from app.vault_runtime.extensions.mcp_runtime import McpRuntimeError
from app.vault_runtime.extensions.plugin_services import PluginVaultServices
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.memory.voice_learning import VoiceMemoryLearning
from app.vault_runtime.memory.openai_reviewer import MemoryReviewProviderError
from app.vault_runtime.external_memory.repository import (
    ExternalMemoryRepository,
)
from app.vault_runtime.external_memory.service import ExternalMemoryService
from app.vault_runtime.host_filesystem.repository import HostFilesystemRepository
from app.vault_runtime.host_filesystem.service import HostFilesystemService
from app.vault_runtime.link_companion.repository import (
    LinkCompanionAuthorizationError,
    LinkCompanionRepository,
)
from app.vault_runtime.agent_network.service import A2AService
from app.vault_runtime.agent_network.tools import agent2agent_option_on
from app.vault_runtime.help_assistant import HelpAssistant, HelpAssistantError
from app.vault_runtime.builtin_plugins import BuiltinPluginRepository
from app.vault_runtime.workspace_files.errors import WorkspaceFileError
from app.vault_runtime.workspace_files.manager import WorkspaceFileUpload
from app.vault_runtime.workspace_files.multipart import parse_multipart_form
from app.vault_runtime.workspace_files.service import WorkspaceFileService
from app.vault_runtime.tasks.repository import TaskRepository, task_view
from app.vault_runtime.notifications.repository import NotificationRepository
from app.vault_runtime.live_memory.preferences import (
    LiveMemoryPreference, LiveMemoryPreferenceRepository, PreferenceConflictError,
)


class VaultLocalApiHealthStore(Protocol):
    def health(self) -> dict[str, Any]: ...


class ProviderCredentialResolver(Protocol):
    def __call__(self, principal: LocalPrincipal, provider_key: str) -> ProviderCredential: ...


@dataclass(frozen=True, slots=True)
class LocalApiResponse:
    status_code: int
    payload: dict[str, Any]
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None
    content_type: str | None = None
    stream: Iterable[bytes] | None = None


class VaultLocalApiApp:
    """Phase-bounded extraction of the Voice Vault local API foundation."""

    def __init__(
        self, *, store: VaultLocalApiHealthStore, token: str, max_body_bytes: int = 1_048_576,
        identity_service: LocalIdentityService | None = None,
        voice_coordinator: VoiceSessionCoordinator | None = None,
        voice_sessions: VoiceSessionRepository | None = None,
        provider_credential_resolver: ProviderCredentialResolver | None = None,
        background_service: BackgroundAgentService | None = None,
        background_runs: BackgroundRunRepository | None = None,
        extension_imports: ExtensionImportService | None = None,
        extensions: ExtensionRepository | None = None,
        extension_secrets: ExtensionSecretStore | None = None,
        mcp_lifecycle: McpLifecycle | None = None,
        voice_provider_credentials: VoiceProviderCredentialStore | None = None,
        provider_oauth: ProviderOAuthService | None = None,
        email_runtime: LocalEmailRuntime | None = None,
        personal_data: PersonalDataRepository | None = None,
        calendar_runtime: LocalCalendarRuntime | None = None,
        voice_learning: VoiceMemoryLearning | None = None,
        voice_tools: VoiceToolRuntime | None = None,
        external_memory_integrations: ExternalMemoryRepository | None = None,
        external_memory: ExternalMemoryService | None = None,
        host_filesystem_integrations: HostFilesystemRepository | None = None,
        host_filesystem: HostFilesystemService | None = None,
        link_companion: LinkCompanionRepository | None = None,
        a2a_service: A2AService | None = None,
        help_assistant: HelpAssistant | None = None,
        builtin_plugins: BuiltinPluginRepository | None = None,
        plugin_services: PluginVaultServices | None = None,
        workspace_files: WorkspaceFileService | None = None,
        tasks: TaskRepository | None = None,
        notifications: NotificationRepository | None = None,
        live_memory_preferences: LiveMemoryPreferenceRepository | None = None,
        live_memory_invalidator: Callable[[LiveMemoryPreference], None] | None = None,
        decision_review=None,
        conversation_runtime=None,
    ) -> None:
        self._store = store
        self._token = token
        self._max_body_bytes = max(1024, max_body_bytes)
        self._identity_service = identity_service
        self._voice_coordinator = voice_coordinator
        self._voice_sessions = voice_sessions
        self._provider_credential_resolver = provider_credential_resolver
        self._background_service = background_service
        self._background_runs = background_runs
        self._extension_imports = extension_imports
        self._extensions = extensions
        self._extension_secrets = extension_secrets
        self._mcp_lifecycle = mcp_lifecycle
        self._voice_provider_credentials = voice_provider_credentials
        self._provider_oauth = provider_oauth
        self._email_runtime = email_runtime
        self._personal_data = personal_data
        self._calendar_runtime = calendar_runtime
        self._voice_learning = voice_learning
        self._voice_tools = voice_tools
        self._external_memory_integrations = external_memory_integrations
        self._external_memory = external_memory
        self._host_filesystem_integrations = host_filesystem_integrations
        self._host_filesystem = host_filesystem
        self._link_companion = link_companion
        self._a2a_service = a2a_service
        self._help_assistant = help_assistant
        self._builtin_plugins = builtin_plugins
        self._plugin_services = plugin_services
        self._workspace_files = workspace_files
        self._tasks = tasks
        self._notifications = notifications
        self._live_memory_preferences = live_memory_preferences
        self._live_memory_invalidator = live_memory_invalidator
        self._decision_review = decision_review
        self._conversation_runtime = conversation_runtime

    def close(self) -> None:
        """Release owned runtime workers without changing durable local state."""
        if self._conversation_runtime is not None:
            self._conversation_runtime.close()
        if self._background_service is not None:
            self._background_service.stop()
        if self._a2a_service is not None:
            self._a2a_service.stop()

    def handle(
        self, *, method: str, target: str, headers: Mapping[str, str], body: bytes = b""
    ) -> LocalApiResponse:
        target_parts = urlsplit(target)
        path = target_parts.path
        if method.upper() == "GET" and path == "/health":
            return self._health()
        if path=="/conversations" or path.startswith("/conversations/"):
            from app.vault_runtime.conversation.api import handle_conversation_api
            from app.vault_runtime.conversation.contracts import AuthorizationError,ConflictError,InputError,NotFoundError
            no_store = (("Cache-Control","no-store"),)
            try:
                if self._identity_service is None or self._conversation_runtime is None:
                    return LocalApiResponse(503,{"error":{"code":"conversation_unavailable"}},no_store)
                principal = self._identity_service.authenticate(session_token=_session_token(headers))
                if method.upper()!="GET":
                    self._identity_service.require_csrf(principal=principal,csrf_token=_csrf_token(headers))
                return handle_conversation_api(self._conversation_runtime,principal,method=method.upper(),path=path,
                    query=target_parts.query,headers=headers,payload=_json_object(body,
                        max_bytes=min(self._max_body_bytes,7_100_000) if method.upper()=="POST" and path.endswith("/attachments")
                        else STRICT_JSON_MAX_BYTES) if body else {})
            except (LocalIdentityError,AuthorizationError) as exc:
                return LocalApiResponse(403,{"error":{"code":"conversation_authority_required","message":str(exc)}},no_store)
            except (InputError,ValueError,TypeError):
                return LocalApiResponse(400,{"error":{"code":"invalid_conversation_request"}},no_store)
            except NotFoundError:
                return LocalApiResponse(404,{"error":{"code":"conversation_not_found"}},no_store)
            except ConflictError as exc:
                return LocalApiResponse(409,{"error":{"code":"conversation_conflict","message":str(exc)}},no_store)
            except Exception:
                return LocalApiResponse(503,{"error":{"code":"conversation_unavailable"}},no_store)
        if path == "/live-memory":
            try:
                return self._handle_live_memory(
                    method=method.upper(), headers=headers, body=body,
                )
            except (LocalIdentityError, PreferenceConflictError, ValueError) as exc:
                code = getattr(exc, "code", "invalid_request")
                status = (409 if isinstance(exc, PreferenceConflictError) else
                          400 if isinstance(exc, ValueError) else
                          401 if code in {"invalid_credentials", "local_session_invalid"} else 403)
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}},
                                        (("Cache-Control", "no-store"),))
        if path.startswith("/plugin-services/v1/"):
            try:
                return self._handle_plugin_services(
                    method=method.upper(), path=path, headers=headers, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "plugin_service_request_failed")
                return LocalApiResponse(
                    400 if isinstance(exc, ValueError) else 403,
                    {"error": {"code": code, "message": str(exc)}},
                    (("Cache-Control", "no-store"),),
                )
        if method.upper() == "GET" and path == "/identity/setup/start" and self._identity_service is not None:
            try:
                secure_cookies = _request_uses_secure_cookies(headers)
                values = parse_qs(target_parts.query, keep_blank_values=True).get("credential", [])
                setup_credential = values[0].strip() if len(values) == 1 else ""
                self._identity_service.validate_setup_credential(setup_credential)
                return LocalApiResponse(303, {"status": "ready"}, (
                    ("Set-Cookie", f"resono_setup_resume={setup_credential}; Path=/; HttpOnly; SameSite=Strict{_secure_cookie_suffix(secure_cookies)}"),
                    # Carry the already validated one-time proof into the local
                    # onboarding document. Some mobile browsers do not retain a
                    # Set-Cookie response across a certificate-interstitial/303
                    # transition. The UI removes this query immediately after
                    # the owner credential is consumed.
                    ("Location", f"/browser-voice.html?setup=fresh&bootstrap={quote(setup_credential, safe='')}"),
                    ("Cache-Control", "no-store"),
                ))
            except (LocalIdentityError, ValueError) as exc:
                code = getattr(exc, "code", "invalid_request")
                return LocalApiResponse(403, {"error": {"code": code, "message": str(exc)}}, (("Cache-Control", "no-store"),))
        if self._identity_service is not None and path.startswith(("/identity/", "/me", "/workspaces", "/local-users")):
            try:
                return self._handle_local_identity(
                    method=method.upper(), path=path, headers=headers, body=body
                )
            except (LocalIdentityError, ValueError) as exc:
                code = getattr(exc, "code", "invalid_request")
                status = 401 if code in {"invalid_credentials", "local_session_invalid"} else 403
                if code in {"local_identity_conflict", "local_user_limit_reached"}:
                    status = 409
                if isinstance(exc, ValueError):
                    status = 400
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith(("/system-agents", "/tools", "/voice/", "/background/")):
            try:
                return self._handle_runtime(
                    method=method.upper(), path=path, query=target_parts.query,
                    headers=headers, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "runtime_request_failed")
                status = 502 if isinstance(exc, MemoryReviewProviderError) else 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/agent2agent"):
            try:
                return self._handle_agent2agent(method=method.upper(), path=path, headers=headers, body=body)
            except Exception as exc:
                code = getattr(exc, "code", "a2a_request_failed")
                return LocalApiResponse(400 if isinstance(exc, ValueError) else 502, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/extensions"):
            try:
                return self._handle_extensions(
                    method=method.upper(), path=path, headers=headers, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "extension_request_failed")
                if code == "extension_not_found":
                    status = 404
                elif code == "extension_conflict":
                    status = 409
                elif isinstance(exc, ValueError):
                    status = 400
                else:
                    status = 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/builtin-plugins"):
            try:
                return self._handle_builtin_plugins(method=method.upper(), path=path, headers=headers, body=body)
            except Exception as exc:
                return LocalApiResponse(400 if isinstance(exc, ValueError) else 403, {"error": {"code": "builtin_plugin_request_failed", "message": str(exc)}})
        if path.startswith("/external-memory/pairing/"):
            try:
                return self._handle_external_memory_pairing(
                    method=method.upper(), path=path, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "external_memory_pairing_failed")
                status = 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/external-memory/integrations"):
            try:
                return self._handle_external_memory_integrations(
                    method=method.upper(), path=path, headers=headers, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "external_memory_request_failed")
                status = 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if path in ("/link-companion/pairing/start", "/link-companion/pairing/status", "/link-companion/agent-network/apply"):
            try:
                return self._handle_link_companion_pairing(
                    method=method.upper(), path=path, body=body,
                )
            except LinkCompanionAuthorizationError as exc:
                return LocalApiResponse(403, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception as exc:
                code = getattr(exc, "code", "link_companion_pairing_failed")
                status = 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/link-companion"):
            try:
                return self._handle_link_companion(
                    method=method.upper(), path=path, headers=headers, body=body,
                )
            except LinkCompanionAuthorizationError as exc:
                return LocalApiResponse(403, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception as exc:
                code = getattr(exc, "code", "link_companion_request_failed")
                status = 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if path.startswith("/host-filesystem/pairing/"):
            try:
                return self._handle_host_filesystem_pairing(
                    method=method.upper(), path=path, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "host_filesystem_pairing_failed")
                status = 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/host-filesystem/"):
            try:
                return self._handle_host_filesystem(
                    method=method.upper(), path=path, headers=headers, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "host_filesystem_request_failed")
                status = 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if path.startswith("/external-memory/v1/"):
            try:
                return self._handle_external_memory(
                    method=method.upper(), path=path, headers=headers, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "external_memory_request_failed")
                status = 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/providers/"):
            try:
                return self._handle_providers(
                    method=method.upper(), path=path, query=target_parts.query,
                    headers=headers, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "provider_request_failed")
                return LocalApiResponse(
                    400 if isinstance(exc, ValueError) else 403,
                    {"error": {"code": code, "message": str(exc)}},
                )
        if self._identity_service is not None and path.startswith("/help/"):
            try:
                return self._handle_help(
                    method=method.upper(), path=path, headers=headers, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "help_request_failed")
                status = 502 if isinstance(exc, (HelpAssistantError, httpx.HTTPError)) else 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/notifications"):
            try:
                return self._handle_notifications(method=method.upper(), path=path, headers=headers, body=body)
            except ValueError as exc:
                return LocalApiResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
            except PermissionError as exc:
                return LocalApiResponse(403, {"error": {"code": "forbidden", "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/tasks"):
            try:
                return self._handle_tasks(method=method.upper(), path=path, headers=headers)
            except ValueError as exc:
                return LocalApiResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
            except PermissionError as exc:
                return LocalApiResponse(403, {"error": {"code": "forbidden", "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/workspace-files"):
            try:
                return self._handle_workspace_files(
                    method=method.upper(), path=path, query=target_parts.query,
                    headers=headers, body=body,
                )
            except WorkspaceFileError as exc:
                status = 404 if exc.code == "not_found" else 409 if exc.code == "conflict" else 403 if exc.code == "forbidden" else 400
                return LocalApiResponse(status, {"error": {"code": exc.code, "message": str(exc)}})
            except ValueError as exc:
                return LocalApiResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
            except Exception as exc:
                from app.vault_runtime.local_identity.repository import LocalSessionError

                if isinstance(exc, LocalSessionError):
                    return LocalApiResponse(401, {"error": {"code": "unauthorized", "message": str(exc)}})
                logging.getLogger(__name__).exception("workspace-files request failed")
                return LocalApiResponse(500, {"error": {"code": "workspace_request_failed", "message": "Workspace request failed."}})
        if self._identity_service is not None and path.startswith("/mail/"):
            try:
                return self._handle_mail(
                    method=method.upper(), path=path, headers=headers, body=body,
                )
            except Exception as exc:
                code = getattr(exc, "code", "mail_request_failed")
                status = 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/contacts"):
            try:
                return self._handle_contacts(method=method.upper(), path=path, headers=headers, body=body)
            except Exception as exc:
                code = getattr(exc, "code", "contacts_request_failed")
                return LocalApiResponse(400 if isinstance(exc, ValueError) else 403,
                                        {"error": {"code": code, "message": str(exc)}})
        if self._identity_service is not None and path.startswith("/calendar"):
            try:
                return self._handle_calendar(method=method.upper(), path=path, headers=headers, body=body)
            except Exception as exc:
                code = getattr(exc, "code", "calendar_request_failed")
                status = 404 if isinstance(exc, LookupError) else 400 if isinstance(exc, ValueError) else 403
                return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})
        return LocalApiResponse(
            status_code=404,
            payload={"error": {"code": "not_found", "message": "Not found."}},
        )

    def _handle_live_memory(self, *, method: str, headers: Mapping[str, str],
                            body: bytes) -> LocalApiResponse:
        no_store = (("Cache-Control", "no-store"),)
        identity, preferences = self._identity_service, self._live_memory_preferences
        if identity is None or preferences is None:
            return LocalApiResponse(503, {"error": {"code": "live_memory_unavailable"}}, no_store)
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET":
            preference = preferences.get(principal)
        elif method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            payload = _json_object(body)
            if set(payload) != {"enabled", "expectedEpoch"}:
                raise ValueError("Expected only enabled and expectedEpoch.")
            preference = preferences.set(principal, enabled=payload["enabled"],
                                         expected_epoch=payload["expectedEpoch"])
            if self._live_memory_invalidator is not None:
                try:
                    self._live_memory_invalidator(preference)
                except Exception:
                    return LocalApiResponse(503, {"error": {"code": "live_memory_invalidation_failed"},
                        "enabled": preference.enabled, "epoch": preference.epoch}, no_store)
        else:
            return LocalApiResponse(404, {"error": {"code": "not_found"}}, no_store)
        return LocalApiResponse(200, {"enabled": preference.enabled, "epoch": preference.epoch}, no_store)

    def _handle_help(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity, assistant = self._identity_service, self._help_assistant
        if identity is None or assistant is None:
            raise RuntimeError("Vault Help is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method != "POST" or path != "/help/ask":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        raw_history = payload.get("history", [])
        if not isinstance(raw_history, list) or len(raw_history) > 8:
            raise ValueError("Help conversation history is invalid.")
        history: list[dict[str, str]] = []
        for item in raw_history:
            if not isinstance(item, dict) or not isinstance(item.get("role"), str) or not isinstance(item.get("content"), str):
                raise ValueError("Help conversation history is invalid.")
            history.append({"role": item["role"], "content": item["content"]})
        return LocalApiResponse(200, assistant.ask(
            principal,
            message=_required_text(payload, "message"),
            history=tuple(history),
            allow_web=bool(payload.get("searchWeb", False)),
        ))

    def _handle_contacts(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity, store = self._identity_service, self._personal_data
        if identity is None or store is None:
            raise RuntimeError("Local Contacts is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/contacts":
            items = store.list_private_records(
                account_id=principal.user_id, workspace_id=principal.workspace_id,
                source_table="contacts_entries", limit=250,
            )
            return LocalApiResponse(200, {"items": items})
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        operation = path.removeprefix("/contacts/")
        tool_name = {
            "search": "contacts_search", "prepare": "contacts_prepare_save",
            "confirm": "contacts_confirm_pending",
        }.get(operation)
        if tool_name is None:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        result = contacts_tool_result(
            store=store, account_id=principal.user_id, workspace_id=principal.workspace_id,
            voice_realtime_session_id="web-management", tool_call_id=str(uuid4()),
            tool_name=tool_name, arguments=payload,
        )
        return LocalApiResponse(200, result)

    def _handle_calendar(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity, runtime = self._identity_service, self._calendar_runtime
        if identity is None or runtime is None:
            raise RuntimeError("Local Calendar is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/calendar/accounts":
            return LocalApiResponse(200, {"items": runtime.accounts(principal)})
        if method == "GET" and path == "/calendar/events":
            return LocalApiResponse(200, {"items": runtime.events(principal)})
        if method not in {"POST", "DELETE"}:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if method == "POST" and path == "/calendar/accounts":
            payload = _json_object(body)
            return LocalApiResponse(201, runtime.connect(
                principal, payload, validate=bool(payload.get("validateConnection", True)),
            ))
        suffix = path.removeprefix("/calendar/accounts/")
        calendar_account_id, _, operation = suffix.partition("/")
        if method == "POST" and calendar_account_id and operation == "sync":
            return LocalApiResponse(200, runtime.sync(principal, calendar_account_id))
        if method == "DELETE" and calendar_account_id and not operation:
            runtime.remove(principal, calendar_account_id)
            return LocalApiResponse(200, {"status": "removed"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_providers(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity = self._identity_service
        credentials = self._voice_provider_credentials
        if identity is None or credentials is None:
            raise RuntimeError("Local Voice provider management is unavailable.")
        oauth = self._provider_oauth
        if path == "/providers/gemini/oauth/callback" and method == "GET":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            values = parse_qs(query, keep_blank_values=True)
            state = values.get("state", [""])[0]
            code = values.get("code", [""])[0]
            oauth.complete_gemini(state=state, code=code)
            return LocalApiResponse(303, {"status": "connected"}, (("Location", "/browser-voice.html?providerOAuth=gemini"),))
        principal = identity.authenticate(session_token=_session_token(headers))
        if path == "/providers/openai/oauth/start" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.start_openai(principal))
        if path == "/providers/openai/oauth/poll" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.poll_openai(principal, _required_text(_json_object(body), "authSessionId")))
        if path == "/providers/gemini/oauth/start" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.start_gemini(principal, _required_text(_json_object(body), "redirectUri")))
        if path == "/providers/xai/oauth/start" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.start_xai(principal))
        if path == "/providers/xai/oauth/poll" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.poll_xai(principal, _required_text(_json_object(body), "authSessionId")))
        if self._voice_coordinator is None:
            raise RuntimeError("AI provider registry is unavailable.")
        descriptors = {item.provider_key: item for item in self._voice_coordinator.provider_descriptors()}
        if path == "/providers/catalog" and method == "GET":
            selected = credentials.selected_provider(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
            )
            return LocalApiResponse(200, {"selectedProviderKey": selected, "items": [
                {
                    **(
                        item_status := credentials.status(
                            principal, item.provider_key,
                            default_model_key=item.default_voice_model,
                            default_voice=item.default_voice,
                            default_background_model_key=item.default_text_model,
                        )
                    ),
                    "displayName": item.display_name,
                    "connectionMode": item.connection_mode,
                    "protocol": item.protocol,
                    "voices": list(item.voices),
                    "voiceModels": list(item.voice_models),
                    "textModels": list(item.text_models),
                    "negotiatedDataChannel": uses_subscription_live_transport(
                        auth_method=str(item_status.get("authMethod") or "api_key"),
                        model_key=str(item_status.get("modelKey") or item.default_voice_model),
                    ),
                    "dataChannelId": (
                        0
                        if uses_subscription_live_transport(
                            auth_method=str(item_status.get("authMethod") or "api_key"),
                            model_key=str(item_status.get("modelKey") or item.default_voice_model),
                        )
                        else None
                    ),
                    "selected": selected == item.provider_key,
                }
                for item in descriptors.values()
            ]})
        parts = path.removeprefix("/providers/").split("/")
        provider_key = parts[0] if parts else ""
        descriptor = descriptors.get(provider_key)
        if descriptor is None:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        if len(parts) == 2 and parts[1] == "auth-method" and method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            credentials.select_auth_method(
                principal, provider_key=provider_key,
                auth_method=_required_text(_json_object(body), "authMethod"),
            )
            return LocalApiResponse(200, credentials.status(
                principal, provider_key, default_model_key=descriptor.default_voice_model,
                default_voice=descriptor.default_voice,
                default_background_model_key=descriptor.default_text_model,
            ))
        if len(parts) == 2 and parts[1] == "oauth" and method == "DELETE":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            credentials.remove_oauth(principal, provider_key)
            return LocalApiResponse(200, credentials.status(
                principal, provider_key, default_model_key=descriptor.default_voice_model,
                default_voice=descriptor.default_voice,
                default_background_model_key=descriptor.default_text_model,
            ))
        if len(parts) == 2 and parts[1] == "select" and method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            credentials.select_provider(principal, provider_key)
            return LocalApiResponse(200, {"selectedProviderKey": provider_key})
        if len(parts) >= 3 and parts[1] == "users":
            target_user_id = parts[2]
            if not target_user_id or "/" in target_user_id:
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
            if method == "GET":
                return LocalApiResponse(200, credentials.account_access_status(principal, target_user_id, provider_key))
            if method == "POST":
                identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
                payload = _json_object(body)
                credentials.set_account_access(
                    principal, target_user_id=target_user_id,
                    provider_key=provider_key,
                    access_mode=_required_text(payload, "accessMode"),
                    api_key=_optional_text(payload, "apiKey"),
                    model_key=_optional_text(payload, "modelKey") or descriptor.default_voice_model,
                    background_model_key=_optional_text(payload, "backgroundModelKey") or descriptor.default_text_model,
                    voice=_optional_text(payload, "voice") or descriptor.default_voice,
                )
                return LocalApiResponse(200, credentials.account_access_status(principal, target_user_id, provider_key))
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        if len(parts) != 1:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        if method == "GET":
            return LocalApiResponse(200, credentials.status(
                principal, provider_key, default_model_key=descriptor.default_voice_model,
                default_voice=descriptor.default_voice,
                default_background_model_key=descriptor.default_text_model,
            ))
        if method == "DELETE":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            credentials.remove(principal, provider_key)
            return LocalApiResponse(200, {"status": "removed"})
        if method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            payload = _json_object(body)
            model_key = _required_text(payload, "modelKey")
            # Audio persona is an internal provider detail, not a user-facing model setting.
            voice = descriptor.default_voice
            background_model_key = (
                _optional_text(payload, "backgroundModelKey") or descriptor.default_text_model
            )
            api_key = _optional_text(payload, "apiKey")
            if api_key:
                credentials.set(
                    principal, provider_key=provider_key, api_key=api_key,
                    model_key=model_key, voice=voice, background_model_key=background_model_key,
                )
            else:
                credentials.update_preferences(
                    principal, provider_key=provider_key, model_key=model_key,
                    voice=voice, background_model_key=background_model_key,
                )
            return LocalApiResponse(200, credentials.status(
                principal, provider_key, default_model_key=descriptor.default_voice_model,
                default_voice=descriptor.default_voice,
                default_background_model_key=descriptor.default_text_model,
            ))
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_mail(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity = self._identity_service
        runtime = self._email_runtime
        if identity is None or runtime is None:
            raise RuntimeError("Local Mail is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        payload = _json_object(body) if method == "POST" else {}
        if method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        with runtime.service(principal) as mail:
            if path == "/mail/agent-accounts" and method == "GET":
                return LocalApiResponse(200, {"items": mail.list_mailboxes(account_id=principal.user_id, workspace_id=principal.workspace_id, mailbox_role="agent_mail")})
            if path == "/mail/agent-accounts" and method == "POST":
                record = mail.connect_mailbox(account_id=principal.user_id, workspace_id=principal.workspace_id, mailbox_role="agent_mail", credentials_payload=_required_object(payload, "credentials"), display_name=_optional_text(payload, "displayName"), validate_connection=_required_bool(payload, "validateConnection"))
                return LocalApiResponse(201, record)
            if path == "/mail/accounts" and method == "GET":
                return LocalApiResponse(200, {"items": mail.list_mailboxes(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_role="normal_email",
                )})
            if path == "/mail/accounts" and method == "POST":
                record = mail.connect_mailbox(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_role="normal_email", credentials_payload=_required_object(payload, "credentials"),
                    display_name=_optional_text(payload, "displayName"),
                    validate_connection=_required_bool(payload, "validateConnection"),
                )
                return LocalApiResponse(201, record)
            prefix = "/mail/accounts/"
            if not path.startswith(prefix):
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
            mailbox_id, _, operation = path.removeprefix(prefix).partition("/")
            if not mailbox_id or not operation:
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
            if method == "GET" and operation == "folders":
                return LocalApiResponse(200, {"items": mail.list_folders(
                    account_id=principal.user_id, workspace_id=principal.workspace_id, mailbox_id=mailbox_id,
                )})
            if method == "GET" and operation == "messages":
                return LocalApiResponse(200, {"items": mail.list_messages(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, limit=50,
                )})
            if method == "GET" and operation.startswith("messages/"):
                message_id = operation.removeprefix("messages/")
                item = mail.read_message(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, message_id=message_id,
                )
                return LocalApiResponse(200 if item else 404, {"item": item})
            if method == "POST" and operation == "sync":
                return LocalApiResponse(200, mail.sync_mailbox(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, trigger_kind="manual",
                ).as_dict())
            if method == "POST" and operation == "send/prepare":
                recipients = payload.get("to")
                if not isinstance(recipients, list) or any(not isinstance(item, str) for item in recipients):
                    raise ValueError("to must be a list of recipients")
                return LocalApiResponse(201, mail.prepare_send(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, idempotency_key=_required_text(payload, "idempotencyKey"),
                    to_recipients=recipients, subject=_required_text(payload, "subject"),
                    body=_required_text(payload, "body"),
                ))
            if method == "POST" and operation == "send/confirm":
                return LocalApiResponse(200, mail.confirm_send(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, pending_request_id=_required_text(payload, "pendingRequestId"),
                    approve=_required_bool(payload, "approve"),
                ))
            if method == "POST" and operation == "lifecycle":
                item = mail.set_mailbox_lifecycle(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, lifecycle_status=_required_text(payload, "status"),
                )
                return LocalApiResponse(200 if item else 404, {"item": item})
            if method == "POST" and operation == "remove":
                item = mail.permanently_remove_mailbox_local(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, confirmation_text=_required_text(payload, "confirmationText"),
                )
                return LocalApiResponse(200 if item else 404, {"item": item})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _health(self) -> LocalApiResponse:
        return LocalApiResponse(status_code=200, payload={"status": "ok", "store": self._store.health()})

    def _handle_local_identity(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes
    ) -> LocalApiResponse:
        service = self._identity_service
        if service is None:
            raise RuntimeError("Local identity service is unavailable.")
        if method == "GET" and path == "/identity/status":
            return LocalApiResponse(200, {"setupComplete": service.setup_complete()})
        payload = _json_object(body) if method == "POST" else {}
        secure_cookies = _request_uses_secure_cookies(headers)
        if method == "POST" and path == "/identity/setup-session":
            setup_credential = _required_text(payload, "setupCredential")
            service.validate_setup_credential(setup_credential)
            return LocalApiResponse(200, {"status": "ready"}, (
                ("Set-Cookie", f"resono_setup_resume={setup_credential}; Path=/; HttpOnly; SameSite=Strict{_secure_cookie_suffix(secure_cookies)}"),
            ))
        if method == "POST" and path == "/identity/onboard":
            tokens, username, recovery_password = service.bootstrap_owner_minimal(
                setup_credential=_required_text(payload, "setupCredential"),
                display_name=_required_text(payload, "displayName"),
                experience_style=_required_text(payload, "experienceStyle"),
            )
            response = _session_response(tokens, status_code=201, secure=secure_cookies)
            return LocalApiResponse(
                response.status_code,
                {**response.payload, "recovery": {
                    "username": username, "generatedPassword": recovery_password,
                    "mustStoreNow": True,
                }},
                response.headers,
            )
        if method == "POST" and path == "/identity/register":
            setup_credential = _optional_text(payload, "setupCredential") or _cookie_value(headers, "resono_setup_resume")
            tokens = service.bootstrap_owner(
                setup_credential=setup_credential,
                username=_required_text(payload, "username"),
                password=_required_text(payload, "password"),
                display_name=_required_text(payload, "displayName"),
                experience_style=_required_text(payload, "experienceStyle"),
            )
            response = _session_response(tokens, status_code=201, secure=secure_cookies)
            return LocalApiResponse(response.status_code, response.payload, (*response.headers,
                ("Set-Cookie", f"resono_setup_resume=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{_secure_cookie_suffix(secure_cookies)}"),
            ))
        if method == "POST" and path == "/identity/login":
            tokens = service.login(
                username=_required_text(payload, "username"),
                password=_required_text(payload, "password"),
            )
            return _session_response(tokens, secure=secure_cookies)
        if method == "POST" and path == "/identity/activate":
            return _session_response(service.activate_user(
                setup_credential=_required_text(payload, "setupCredential"),
                new_password=_required_text(payload, "newPassword"),
            ), secure=secure_cookies)
        session_token = _session_token(headers)
        if method == "POST" and path == "/identity/token/refresh":
            return _session_response(service.refresh(
                session_token=session_token, csrf_token=_csrf_token(headers)
            ), secure=secure_cookies)
        principal = service.authenticate(session_token=session_token, allow_restricted=True)
        restricted_paths = {"/me", "/identity/password", "/identity/logout"}
        if principal.must_change_password and path not in restricted_paths:
            from app.vault_runtime.local_identity.service import LocalPasswordChangeRequiredError
            raise LocalPasswordChangeRequiredError("Password change is required before using Vault.")
        if method == "GET" and path == "/me":
            return LocalApiResponse(200, {"user": _principal_payload(principal)})
        if method == "POST" and path == "/identity/logout":
            service.logout(session_token=session_token, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, {"status": "logged_out"}, _clear_session_cookie_headers(secure=secure_cookies))
        if method == "POST" and path == "/local-users":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            provisioned = service.provision_user(
                actor=principal, username=_required_text(payload, "username"),
                password=_optional_text(payload, "password"),
                password_mode=_optional_text(payload, "passwordMode") or "temporary_password",
                age_group=_required_text(payload, "ageGroup"),
                display_name=_required_text(payload, "displayName"),
                experience_style=_required_text(payload, "experienceStyle"),
            )
            return LocalApiResponse(201, {
                "userId": provisioned.user_id, "workspaceId": provisioned.workspace_id,
                "passwordMode": provisioned.password_mode,
                "setupCredential": provisioned.setup_credential,
            })
        if method == "GET" and path == "/local-users":
            return LocalApiResponse(200, {"items": service.list_users(actor=principal)})
        local_user_operation = _local_user_operation(path)
        if method == "POST" and local_user_operation is not None:
            user_id, operation = local_user_operation
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            if operation == "password-reset":
                setup_credential = service.reset_user_password(
                    actor=principal, user_id=user_id,
                    new_password=_optional_text(payload, "newPassword"),
                    password_mode=_optional_text(payload, "passwordMode") or "temporary_password",
                )
                return LocalApiResponse(200, {
                    "status": "password_reset", "setupCredential": setup_credential,
                })
            if operation == "remove":
                service.remove_user(actor=principal, user_id=user_id)
                return LocalApiResponse(200, {"status": "account_removed"})
        if method == "POST" and path == "/identity/password":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            service.change_password(
                principal=principal, current_password=_required_text(payload, "currentPassword"),
                new_password=_required_text(payload, "newPassword"),
            )
            return LocalApiResponse(200, {"status": "password_changed"})
        if method == "GET" and path == "/workspaces":
            workspaces = service.list_workspaces(principal=principal)
            return LocalApiResponse(200, {"items": [
                {"workspaceId": item.workspace_id, "displayName": item.display_name,
                 "ownerUserId": item.owner_user_id, "membershipType": item.membership_type}
                for item in workspaces
            ]})
        if method == "POST" and path == "/workspaces":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            workspace_id = service.create_workspace(
                principal=principal, display_name=_required_text(payload, "displayName")
            )
            return LocalApiResponse(201, {"workspaceId": workspace_id})
        if method == "POST" and path == "/workspaces/select":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            service.switch_workspace(
                principal=principal, workspace_id=_required_text(payload, "workspaceId")
            )
            return LocalApiResponse(200, {"user": _principal_payload(
                service.authenticate(session_token=session_token)
            )})
        if method == "POST" and path == "/workspaces/members":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            service.add_member(
                principal=principal, workspace_id=_required_text(payload, "workspaceId"),
                username=_required_text(payload, "username"),
            )
            return LocalApiResponse(200, {"status": "member_added"})
        if method == "POST" and path == "/workspaces/members/revoke":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            service.revoke_member(
                principal=principal, workspace_id=_required_text(payload, "workspaceId"),
                username=_required_text(payload, "username"),
            )
            return LocalApiResponse(200, {"status": "member_revoked"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

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
        if method == "GET" and path == "/extensions/runtime":
            return LocalApiResponse(200, {"safeMode": repository.safe_mode(
                actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
            )})
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
                mount_id = payload.get("localShareMountId")
                mount_name = payload.get("localShareMountName")
                mount_permission = payload.get("localSharePermission")
                if mount_id or mount_name or mount_permission:
                    if not isinstance(mount_id, str) or not mount_id.strip():
                        raise ValueError("localShareMountId is required when linking a folder.")
                    if not isinstance(mount_name, str) or not mount_name.strip():
                        raise ValueError("localShareMountName is required when linking a folder.")
                    if mount_permission not in {"read", "write"}:
                        raise ValueError("localSharePermission must be read or write.")
                    from app.vault_runtime.extensions.service import LocalShareRegistration
                    arguments["local_share"] = LocalShareRegistration(
                        mount_id=mount_id.strip(),
                        mount_name=mount_name.strip(),
                        permission=str(mount_permission),
                    )
                record = imports.confirm_plugin(**arguments)
            elif kind == "mcp":
                record = imports.confirm_mcp(**arguments)
            else:
                raise ValueError("Extension kind is invalid.")
            return LocalApiResponse(201, _extension_payload(record))
        if path == "/extensions/safe-mode":
            enabled = _required_bool(payload, "enabled")
            repository.set_safe_mode(
                actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                enabled=enabled,
            )
            if enabled and self._mcp_lifecycle is not None:
                self._mcp_lifecycle.enter_safe_mode()
            return LocalApiResponse(200, {"safeMode": enabled})
        if path.startswith("/extensions/"):
            suffix = path.removeprefix("/extensions/")
            extension_id, _, operation = suffix.partition("/")
            if not extension_id or operation not in {"state", "grants", "credentials", "settings", "discover"}:
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
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
                        existing_headers = dict(self._extension_secrets.resolve_headers(
                            user_id=principal.user_id, workspace_id=principal.workspace_id,
                            extension_id=target_id,
                        ))
                        self._extension_secrets.set_headers(
                            actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                            extension_id=target_id,
                            headers=existing_headers | secret_headers,
                        )
                return LocalApiResponse(200, _extension_payload(record))
            if self._extension_secrets is None:
                raise RuntimeError("Local extension credentials are unavailable.")
            secret_headers = payload.get("headers")
            if not isinstance(secret_headers, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in secret_headers.items()
            ):
                raise ValueError("headers must map strings to strings")
            self._extension_secrets.set_headers(
                actor_user_id=principal.user_id, workspace_id=principal.workspace_id,
                extension_id=extension_id, headers=secret_headers,
            )
            return LocalApiResponse(200, {"status": "credentials_updated"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

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

    def _handle_agent2agent(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity, service = self._identity_service, self._a2a_service
        if identity is None or service is None:
            raise RuntimeError("Agent2Agent is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "POST" and path == "/agent2agent/connections":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            if not agent2agent_option_on(self._builtin_plugins, principal.user_id, principal.workspace_id):
                raise ValueError("Agent2Agent is turned off.")
            payload = _json_object(body)
            item = service.connect(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                display_name=_required_text(payload, "displayName"),
                card_url=_required_text(payload, "cardUrl"),
                token=str(payload.get("token") or ""),
            )
            return LocalApiResponse(201, {"connectionId": item.connection_id, "displayName": item.display_name,
                "cardUrl": item.card_url, "enabled": item.enabled, "agentCard": item.agent_card})
        repository = service.repository
        if method == "GET" and path == "/agent2agent/connections":
            return LocalApiResponse(200, {"items": [{
                "connectionId": item.connection_id, "displayName": item.display_name,
                "cardUrl": item.card_url, "enabled": item.enabled,
                "agentCard": item.agent_card,
            } for item in repository.list(user_id=principal.user_id, workspace_id=principal.workspace_id)]})
        if method == "GET" and path == "/agent2agent/notifications":
            return LocalApiResponse(200, {"items": list(repository.notifications(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
            ))})
        if method == "GET" and path == "/agent2agent/listen":
            if not agent2agent_option_on(self._builtin_plugins, principal.user_id, principal.workspace_id):
                raise ValueError("Agent2Agent is turned off.")
            return LocalApiResponse(200, service.listen_info(user_id=principal.user_id, workspace_id=principal.workspace_id))
        if method == "DELETE" and path.startswith("/agent2agent/connections/"):
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            repository.remove(user_id=principal.user_id, workspace_id=principal.workspace_id,
                              connection_id=path.removeprefix("/agent2agent/connections/").strip("/"))
            return LocalApiResponse(200, {"status": "removed"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_external_memory_integrations(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity = self._identity_service
        repository = self._external_memory_integrations
        if identity is None or repository is None:
            raise RuntimeError("External memory integrations are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/external-memory/integrations":
            return LocalApiResponse(200, {"items": [
                _external_integration_payload(item) for item in repository.list(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                )
            ]})
        if method == "GET" and path.startswith("/external-memory/integrations/pairing/"):
            code = path.removeprefix("/external-memory/integrations/pairing/")
            return LocalApiResponse(200, repository.pairing_by_code(pairing_code=code))
        if method not in {"POST", "DELETE"}:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        if path.startswith("/external-memory/integrations/pairing/") and path.endswith("/approve"):
            pairing_id = path.removeprefix("/external-memory/integrations/pairing/").removesuffix("/approve").strip("/")
            integration = repository.approve_pairing(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                pairing_id=pairing_id,
            )
            return LocalApiResponse(200, _external_integration_payload(integration))
        if path == "/external-memory/integrations":
            grants = tuple(sorted(set(_text_tuple(payload, "grants", required=True))))
            if any(grant not in {"search", "propose", "correct", "forget"} for grant in grants):
                raise ValueError("grants may contain only search, propose, correct and forget")
            enrollment = repository.enroll(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                display_name=_required_text(payload, "displayName")[:128],
                adapter_kind=_required_text(payload, "adapterKind")[:64], grants=grants,
            )
            result = _external_integration_payload(enrollment.integration)
            result["credential"] = enrollment.credential
            return LocalApiResponse(201, result, (("Cache-Control", "no-store"),))
        suffix = path.removeprefix("/external-memory/integrations/")
        integration_id, _, operation = suffix.partition("/")
        if method == "DELETE" and integration_id and not operation:
            repository.remove_revoked(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                integration_id=integration_id,
            )
            return LocalApiResponse(200, {"status": "removed"})
        if integration_id and operation == "revoke":
            repository.revoke(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                integration_id=integration_id,
            )
            return LocalApiResponse(200, {"status": "revoked"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_link_companion_pairing(
        self, *, method: str, path: str, body: bytes,
    ) -> LocalApiResponse:
        repository = self._link_companion
        if repository is None:
            raise RuntimeError("Link Companion pairing is unavailable.")
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        payload = _json_object(body)
        if path == "/link-companion/pairing/start":
            result = repository.start_pairing(
                display_name=_required_text(payload, "displayName")[:128],
                poll_token=_required_text(payload, "pollToken"),
            )
            return LocalApiResponse(201, result, (("Cache-Control", "no-store"),))
        if path == "/link-companion/pairing/status":
            status = repository.pairing_status(
                pairing_id=_required_text(payload, "pairingId"),
                poll_token=_required_text(payload, "pollToken"),
            )
            return LocalApiResponse(200, {"status": status}, (("Cache-Control", "no-store"),))
        if path == "/link-companion/agent-network/apply":
            if repository.current_link() is None:
                raise LinkCompanionAuthorizationError("Link Companion is not paired.")
            service = self._a2a_service
            if service is None:
                raise RuntimeError("Agent2Agent is unavailable.")
            inbound = payload.get("inbound")
            outbound = payload.get("outbound")
            if not isinstance(inbound, list) or not isinstance(outbound, list):
                raise ValueError("inbound and outbound must be lists")
            result = service.apply_link_snapshot(
                inbound=[item for item in inbound if isinstance(item, dict)],
                outbound=[item for item in outbound if isinstance(item, dict)],
            )
            return LocalApiResponse(200, result, (("Cache-Control", "no-store"),))
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_link_companion(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        repository = self._link_companion
        identity = self._identity_service
        if repository is None or identity is None:
            raise RuntimeError("Link Companion is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/link-companion":
            current = repository.current_link()
            return LocalApiResponse(200, current or {"status": "not_paired"})
        if method == "GET" and path.startswith("/link-companion/pairing/"):
            code = path.removeprefix("/link-companion/pairing/").strip("/")
            return LocalApiResponse(200, repository.pairing_by_code(pairing_code=code))
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if not principal.is_device_owner:
            raise LinkCompanionAuthorizationError("Only the Vault owner can confirm Link Companion.")
        if path.startswith("/link-companion/pairing/") and path.endswith("/approve"):
            pairing_id = path.removeprefix("/link-companion/pairing/").removesuffix("/approve").strip("/")
            return LocalApiResponse(200, repository.approve_pairing(pairing_id=pairing_id))
        if path == "/link-companion/unpair":
            repository.unpair()
            if self._a2a_service is not None:
                self._a2a_service.clear_link_snapshot()
            return LocalApiResponse(200, {"status": "unpaired"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_external_memory_pairing(
        self, *, method: str, path: str, body: bytes,
    ) -> LocalApiResponse:
        repository = self._external_memory_integrations
        if repository is None:
            raise RuntimeError("External memory integrations are unavailable.")
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        payload = _json_object(body)
        if path == "/external-memory/pairing/start":
            grants = tuple(sorted(set(_text_tuple(payload, "grants", required=True))))
            if any(grant not in {"search", "propose", "correct", "forget"} for grant in grants):
                raise ValueError("grants may contain only search, propose, correct and forget")
            result = repository.start_pairing(
                display_name=_required_text(payload, "displayName")[:128],
                adapter_kind=_required_text(payload, "adapterKind")[:64], grants=grants,
                poll_token=_required_text(payload, "pollToken"),
                runtime_token_hash=_required_text(payload, "runtimeTokenHash"),
            )
            return LocalApiResponse(201, result, (("Cache-Control", "no-store"),))
        if path == "/external-memory/pairing/status":
            status = repository.pairing_status(
                pairing_id=_required_text(payload, "pairingId"),
                poll_token=_required_text(payload, "pollToken"),
            )
            return LocalApiResponse(200, {"status": status}, (("Cache-Control", "no-store"),))
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_host_filesystem_pairing(
        self, *, method: str, path: str, body: bytes,
    ) -> LocalApiResponse:
        service = self._host_filesystem
        if service is None:
            raise RuntimeError("Host filesystem service is unavailable.")
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        payload = _json_object(body)
        if path == "/host-filesystem/pairing/start":
            result = service.start_pairing(
                display_name=_required_text(payload, "displayName")[:128],
                adapter_kind=_required_text(payload, "adapterKind")[:64],
                poll_token=_required_text(payload, "pollToken"),
                runtime_token_hash=_required_text(payload, "runtimeTokenHash"),
                outbound_credential=_optional_text(payload, "outboundCredential"),
            )
            return LocalApiResponse(201, result, (("Cache-Control", "no-store"),))
        if path == "/host-filesystem/pairing/status":
            status = service.pairing_status(
                pairing_id=_required_text(payload, "pairingId"),
                poll_token=_required_text(payload, "pollToken"),
            )
            return LocalApiResponse(200, {"status": status}, (("Cache-Control", "no-store"),))
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_host_filesystem(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        service = self._host_filesystem
        identity = self._identity_service
        if service is None or identity is None:
            raise RuntimeError("Host filesystem service is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/host-filesystem/settings":
            settings = service.settings(principal=principal)
            return LocalApiResponse(200, {
                "enabled": settings.enabled,
                "helperBaseUrl": settings.helper_base_url,
            })
        if method == "GET" and path == "/host-filesystem/integrations":
            return LocalApiResponse(200, {"items": service.list_integrations(principal=principal)})
        if method == "GET" and path == "/host-filesystem/mounts":
            return LocalApiResponse(200, {"items": service.list_mounts(principal=principal)})
        if method == "GET" and path.startswith("/host-filesystem/integrations/pairing/"):
            code = path.removeprefix("/host-filesystem/integrations/pairing/")
            return LocalApiResponse(200, service.pairing_by_code(pairing_code=code))
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        if path == "/host-filesystem/settings":
            enabled = _required_bool(payload, "enabled")
            if enabled and not service.settings(principal=principal).enabled:
                current_password = _optional_text(payload, "currentPassword")
                if not current_password:
                    return LocalApiResponse(400, {
                        "error": {
                            "code": "password_required",
                            "message": "Enter your current password to turn on computer folders.",
                        },
                    })
                try:
                    self._identity_service.verify_current_password(
                        principal=principal,
                        current_password=current_password,
                    )
                except Exception as exc:
                    code = getattr(exc, "code", "invalid_password")
                    message = str(exc) if str(exc) else "Current password is invalid."
                    return LocalApiResponse(400, {"error": {"code": code, "message": message}})
            settings = service.save_settings(
                principal=principal,
                enabled=enabled,
                helper_base_url=_optional_text(payload, "helperBaseUrl"),
            )
            return LocalApiResponse(200, {
                "enabled": settings.enabled,
                "helperBaseUrl": settings.helper_base_url,
            })
        if path.startswith("/host-filesystem/integrations/pairing/") and path.endswith("/approve"):
            pairing_id = path.removeprefix("/host-filesystem/integrations/pairing/").removesuffix("/approve").strip("/")
            integration = service.approve_pairing(principal=principal, pairing_id=pairing_id)
            return LocalApiResponse(200, integration)
        if path == "/host-filesystem/mounts":
            item = service.register_mount(
                principal=principal,
                mount_id=_required_text(payload, "mountId"),
                mount_name=_required_text(payload, "mountName"),
                permission=_required_text(payload, "permission"),
                host_path=str(payload.get("hostPath") or "").strip(),
                source=_optional_text(payload, "source") or "browser",
            )
            return LocalApiResponse(201, item)
        if path.startswith("/host-filesystem/mounts/") and path.endswith("/revoke"):
            mount_id = path.removeprefix("/host-filesystem/mounts/").removesuffix("/revoke").strip("/")
            service.revoke_mount(principal=principal, mount_id=mount_id)
            return LocalApiResponse(200, {"status": "revoked"})
        if path.startswith("/host-filesystem/integrations/") and path.endswith("/revoke"):
            integration_id = path.removeprefix("/host-filesystem/integrations/").removesuffix("/revoke").strip("/")
            service.revoke_integration(principal=principal, integration_id=integration_id)
            return LocalApiResponse(200, {"status": "revoked"})
        if path.startswith("/host-filesystem/integrations/") and path.endswith("/remove"):
            integration_id = path.removeprefix("/host-filesystem/integrations/").removesuffix("/remove").strip("/")
            service.remove_integration(principal=principal, integration_id=integration_id)
            return LocalApiResponse(200, {"status": "removed"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_external_memory(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        service = self._external_memory
        if service is None:
            raise RuntimeError("External memory service is unavailable.")
        if method == "GET" and path == "/external-memory/v1/health":
            return LocalApiResponse(200, {
                "status": "ok", "contractVersion": "1",
                "operations": ["startup", "search", "get", "propose", "correct", "forget", "disconnect"],
            })
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        credential = _bearer_token(headers)
        payload = _json_object(body)
        request_id = _required_text(payload, "requestId")
        if path == "/external-memory/v1/disconnect":
            repository = self._external_memory_integrations
            if repository is None:
                raise RuntimeError("External memory integrations are unavailable.")
            repository.disconnect_credential(credential=credential)
            return LocalApiResponse(200, {"requestId": request_id, "status": "revoked"})
        if path == "/external-memory/v1/startup":
            memories = service.startup(
                credential=credential, request_id=request_id, limit=payload.get("limit", 8),
            )
            return LocalApiResponse(200, {
                "items": [_external_memory_record_payload(item) for item in memories],
            })
        if path == "/external-memory/v1/search":
            matches = service.search(
                credential=credential, request_id=request_id,
                query=_required_text(payload, "query"), limit=payload.get("limit", 8),
            )
            return LocalApiResponse(200, {"items": [_external_memory_match_payload(item) for item in matches]})
        if path == "/external-memory/v1/get":
            memory = service.get(
                credential=credential, request_id=request_id,
                memory_id=_required_text(payload, "memoryId"),
            )
            return LocalApiResponse(200, _external_memory_record_payload(memory))
        if path == "/external-memory/v1/propose":
            evidence = payload.get("evidence", "")
            if not isinstance(evidence, str):
                raise ValueError("evidence must be a string")
            proposal = service.propose(
                credential=credential, request_id=request_id,
                content=_required_text(payload, "content"),
                evidence=evidence,
            )
            result = proposal.result
            return LocalApiResponse(202, {
                "requestId": proposal.request_id, "status": "reviewed",
                "memoryCount": result.memory_count, "alreadyCompleted": result.already_completed,
            })
        if path in {"/external-memory/v1/request-correction", "/external-memory/v1/request-forget"}:
            action_kind = "correct" if path.endswith("correction") else "forget"
            new_content = payload.get("newContent")
            if new_content is not None and not isinstance(new_content, str):
                raise ValueError("newContent must be a string")
            result = service.apply_action(
                credential=credential, request_id=request_id, action_kind=action_kind,
                memory_id=_required_text(payload, "memoryId"), proposed_content=new_content,
            )
            return LocalApiResponse(200, {
                "requestId": request_id, "status": "applied", "result": result,
            })
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_plugin_services(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        service = self._plugin_services
        if service is None:
            raise RuntimeError("Plugin services are unavailable.")
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        names = {
            "/plugin-services/v1/memory/search": "memory.search",
            "/plugin-services/v1/memory/propose": "memory.propose",
            "/plugin-services/v1/context/locale": "context.locale",
            "/plugin-services/v1/activity/report": "activity.report",
        }
        name = names.get(path)
        if name is None:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        invocation_id = (_header(headers, "x-vault-invocation-id") or "").strip()
        if not invocation_id or len(invocation_id) > 256:
            raise ValueError("Vault invocation identifier is required")
        status, payload = service.call(
            token=_bearer_token(headers), invocation_id=invocation_id,
            service=name, payload=_json_object(body),
        )
        return LocalApiResponse(status, payload, (("Cache-Control", "no-store"),))

    def _handle_runtime(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes
    ) -> LocalApiResponse:
        identity = self._identity_service
        if identity is None:
            raise RuntimeError("Local identity service is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/system-agents":
            return LocalApiResponse(200, {"items": [
                {
                    "kind": item.kind.value, "displayName": item.display_name,
                    "interactive": item.interactive,
                }
                for item in SYSTEM_AGENT_INVENTORY
            ]})
        if method == "GET" and path == "/tools":
            if self._voice_tools is None:
                raise RuntimeError("Local tools are unavailable.")
            return LocalApiResponse(200, {"items": [
                {
                    "name": item.name,
                    "description": item.description,
                    "effectClass": item.effect_class,
                    "audiences": sorted(agent.value for agent in item.audiences),
                    "builtIn": item.tool_id.startswith("builtin."),
                    "category": _tool_category(item.tool_id, item.name),
                }
                for item in self._voice_tools.definitions(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                )
            ]})
        if method == "POST" and path == "/voice/sessions":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            payload = _json_object(body, max_bytes=self._max_body_bytes)
            if self._voice_coordinator is None or self._provider_credential_resolver is None:
                raise RuntimeError("Local Voice provider is unavailable.")
            provider_key = _required_text(payload, "providerKey")
            if self._mcp_lifecycle is not None:
                self._mcp_lifecycle.restore_scope(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                    agent=AgentKind.VOICE,
                )
            credential = self._provider_credential_resolver(principal, provider_key)
            started = self._voice_coordinator.start(
                principal=principal,
                provider_key=provider_key,
                model_key=_required_text(payload, "modelKey"),
                connection_mode=_required_text(payload, "connectionMode"),
                credential=credential,
                voice=_optional_text(payload, "voice"),
                offer_sdp=_optional_webrtc_sdp(payload, "offerSdp"),
            )
            return LocalApiResponse(201, {
                "voiceRealtimeSessionId": started.session.voice_session_id,
                "providerKey": started.provider.provider_key,
                "modelKey": started.provider.model_key,
                "connectionMode": started.provider.connection_mode,
                "clientSecret": started.provider.client_secret,
                "expiresAt": started.provider.expires_at,
                "sdpAnswer": started.provider.sdp_answer,
                "sessionUpdate": started.provider.session_update_event,
                "protocol": started.provider.protocol,
                "websocketUrl": started.provider.websocket_url,
                "websocketProtocol": started.provider.websocket_protocol,
                "inputSampleRate": started.provider.input_sample_rate,
                "outputSampleRate": started.provider.output_sample_rate,
                "connectGreetingEvent": connect_greeting_event(started.context.display_name),
                "liveTranscription": started.live_transcription,
            })
        payload = _json_object(body) if method == "POST" else {}
        if method in {"POST", "DELETE"}:
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if path.startswith("/voice/sessions/") and "/preparation" in path:
            from app.vault_runtime.live_memory.voice_host import PREFIX
            session_id,suffix=path.removeprefix("/voice/sessions/").split("/preparation",1)
            runtime=self._conversation_runtime
            preparation=runtime.preparation if runtime is not None else None
            if preparation is None or self._voice_sessions is None:
                return LocalApiResponse(503,{"error":{"code":"voice_preparation_unavailable"}})
            self._voice_sessions.session(user_id=principal.user_id,workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,voice_session_id=session_id,require_open=True)
            source_id=PREFIX+session_id
            if method=="GET" and suffix=="":
                params=parse_qs(query)
                return LocalApiResponse(200,preparation.status(principal,source_id,
                    _required_text({"utteranceId":params.get("utteranceId",[""])[0]},"utteranceId"),
                    int(params.get("revision",["0"])[0])),(("Cache-Control","no-store"),))
            if method=="POST" and suffix=="/transcription":
                credential=self._provider_credential_resolver(principal,"openai",capability="live_transcription")
                result=self._voice_coordinator.start_transcription(principal=principal,
                    voice_session_id=session_id,credential=credential)
                return LocalApiResponse(201,{"clientSecret":result.client_secret},(("Cache-Control","no-store"),))
            if method=="POST" and suffix=="/delivered":
                return LocalApiResponse(200,preparation.delivered(principal,source_id,
                    _required_text(payload,"utteranceId"),_required_nonnegative_int(payload,"memoryCount"),
                    _required_nonnegative_int(payload,"toolCount") if "toolCount" in payload else 0))
            if method=="POST" and suffix=="":
                return LocalApiResponse(202,preparation.update(principal,source_id,payload),(("Cache-Control","no-store"),))
            if method=="DELETE" and suffix=="":
                return LocalApiResponse(200,preparation.discard(principal,source_id))
            return LocalApiResponse(404,{"error":{"code":"not_found"}})
        if method == "GET" and path == "/voice/plan":
            if self._provider_credential_resolver is None:
                raise RuntimeError("Local Voice provider is unavailable.")
            params = parse_qs(query, keep_blank_values=True)
            provider_key = _required_query(params, "providerKey")
            model_key = _required_query(params, "modelKey")
            credential = self._provider_credential_resolver(principal, provider_key)
            subscription_live = uses_subscription_live_transport(
                auth_method=credential.auth_method,
                model_key=model_key,
            )
            return LocalApiResponse(200, {
                "transport": "openai-realtime",
                "negotiatedDataChannel": subscription_live,
                "dataChannelId": 0 if subscription_live else None,
            })
        if method == "GET" and path.startswith("/voice/sessions/") and path.endswith("/decision-review"):
            if self._decision_review is None:
                return LocalApiResponse(503,{"error":{"code":"decision_review_disabled","message":"Procedural review is disabled."}})
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/decision-review").strip("/")
            return LocalApiResponse(200,self._decision_review.status(principal=principal,voice_session_id=voice_session_id),
                                    (("Cache-Control","no-store"),))
        if method == "POST" and path.startswith("/voice/sessions/") and path.endswith("/close"):
            if self._voice_sessions is None:
                raise RuntimeError("Local Voice sessions are unavailable.")
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/close").strip("/")
            if self._conversation_runtime is not None and self._conversation_runtime.preparation is not None:
                from app.vault_runtime.live_memory.voice_host import PREFIX
                current=self._voice_sessions.session(user_id=principal.user_id,workspace_id=principal.workspace_id,
                    local_session_id=principal.session_id,voice_session_id=voice_session_id)
                if current.status in {"starting","transport_open"}:
                    self._conversation_runtime.preparation.discard(principal,PREFIX+voice_session_id)
            session = self._voice_sessions.close_session(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id, voice_session_id=voice_session_id,
                transcript_capture_failures=payload.get("transcriptCaptureFailures"),
            )
            if self._voice_coordinator is not None:
                self._voice_coordinator.close_modes(voice_session_id)
            response: dict[str, Any] = {
                "voiceRealtimeSessionId": session.voice_session_id, "status": session.status,
            }
            capture_state = self._voice_sessions.capture_state(user_id=principal.user_id,workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,voice_session_id=voice_session_id)
            response["captureState"] = capture_state
            if capture_state=="incomplete":
                response.update(learning="deferred_incomplete_capture",decisionReview={"state":"blocked_incomplete_capture"})
                return LocalApiResponse(200,response)
            if self._voice_learning is not None and self._conversation_runtime is not None:
                self._conversation_runtime.queue_voice_review(principal=principal,voice_session_id=voice_session_id)
                response.update(learning="queued")
                return LocalApiResponse(200,response)
            if self._voice_learning is not None:
                finalized = (self._conversation_runtime.finalize_voice(principal=principal,voice_session_id=voice_session_id)
                    if self._conversation_runtime is not None else self._voice_learning.finalize(
                        principal=principal,voice_session_id=voice_session_id))
                response.update({
                    "learning": "completed" if finalized is not None else "skipped_empty",
                    "memoryCount": finalized.memory_count if finalized is not None else 0,
                    "embeddedCount": finalized.embedded_count if finalized is not None else 0,
                    "embeddingsAvailable": finalized.embeddings_available if finalized is not None else False,
                })
                if finalized is not None and finalized.decision_review is not None:
                    response["decisionReview"] = finalized.decision_review
            return LocalApiResponse(200, response)
        if method == "POST" and path.startswith("/voice/sessions/") and path.endswith("/events"):
            if self._voice_learning is None:
                raise RuntimeError("Local Voice learning is unavailable.")
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/events").strip("/")
            event = self._voice_learning.capture(
                principal=principal, voice_session_id=voice_session_id,
                provider_event_id=_required_text(payload, "providerEventId"),
                event_type=_required_text(payload, "eventType"),
                role=_required_text(payload, "role"),
                transcript_text=_required_text(payload, "transcriptText") if "transcriptText" in payload else None,
                transcript_entry_index=_required_nonnegative_int(payload, "transcriptEntryIndex") if "transcriptEntryIndex" in payload else None,
                payload=payload.get("providerPayload", {}),
            )
            return LocalApiResponse(201 if event.accepted else 200, {
                "accepted": event.accepted, "providerEventId": event.provider_event_id,
            })
        if method == "POST" and path.startswith("/voice/sessions/") and path.endswith("/tools/call"):
            if self._voice_tools is None or self._voice_sessions is None:
                raise RuntimeError("Local Voice tools are unavailable.")
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/tools/call").strip("/")
            self._voice_sessions.session(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id, voice_session_id=voice_session_id,
                require_open=True,
            )
            arguments = payload.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            utterance_id = payload.get("userUtteranceId")
            if utterance_id is not None and (not isinstance(utterance_id, int) or utterance_id < 0):
                raise ValueError("userUtteranceId must be a non-negative integer")
            from app.vault_runtime.voice.tools import VoiceToolCallPending
            context = ToolInvocationContext(
                agent=AgentKind.VOICE, user_id=principal.user_id,
                workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,
                voice_session_id=voice_session_id,
                tool_call_id=_required_text(payload, "toolCallId"),
                user_utterance=_optional_text(payload, "userUtterance"),
                user_utterance_id=utterance_id,
            )
            try:
                result = self._voice_tools.invoke(name=_required_text(payload, "name"),
                                                  arguments=arguments, context=context)
            except VoiceToolCallPending:
                return LocalApiResponse(202, {"pending": True}, (("Cache-Control", "no-store"),))
            return LocalApiResponse(200, result.mcp_result())
        if method == "POST" and path.startswith("/voice/sessions/") and path.endswith("/finalize"):
            if self._voice_learning is None or self._voice_sessions is None:
                raise RuntimeError("Local Voice learning is unavailable.")
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/finalize").strip("/")
            self._voice_sessions.session(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id, voice_session_id=voice_session_id,
                require_open=False,
            )
            if self._voice_sessions.capture_state(user_id=principal.user_id,workspace_id=principal.workspace_id,
                    local_session_id=principal.session_id,voice_session_id=voice_session_id)=="incomplete":
                return LocalApiResponse(409,{"error":{"code":"capture_incomplete",
                    "message":"Transcript capture was incomplete; review is blocked."}})
            finalized = (self._conversation_runtime.finalize_voice(principal=principal,voice_session_id=voice_session_id)
                if self._conversation_runtime is not None else self._voice_learning.finalize(
                    principal=principal,voice_session_id=voice_session_id))
            if finalized is None:
                return LocalApiResponse(409, {
                    "error": {"code": "nothing_to_review", "message": "Session has no transcript to review."},
                })
            response = {
                "voiceRealtimeSessionId": voice_session_id,
                "learning": "already_completed" if finalized.already_completed else "completed",
                "memoryCount": finalized.memory_count,
                "embeddedCount": finalized.embedded_count,
                "embeddingsAvailable": finalized.embeddings_available,
                "summary": finalized.summary,
            }
            if finalized.decision_review is not None:
                response["decisionReview"] = finalized.decision_review
            return LocalApiResponse(200,response)
        if method == "GET" and path == "/background/runs":
            if self._background_runs is None:
                raise RuntimeError("Background Agent runs are unavailable.")
            items = self._background_runs.list_in_workspace(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,
            )
            return LocalApiResponse(200, {"items": [
                _background_run_payload(
                    item,
                    events=self._background_runs.list_events(
                        user_id=principal.user_id, workspace_id=principal.workspace_id,
                        local_session_id=principal.session_id, run_id=item.request.run_id,
                        authorize=False,
                    ),
                )
                for item in items
            ]})
        if method == "POST" and path == "/background/runs":
            if self._background_service is None:
                raise RuntimeError("Background Agent is unavailable.")
            request = _background_request(payload)
            run = self._background_service.submit(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id, request=request,
            )
            return LocalApiResponse(202, _background_run_payload(run))
        if path.startswith("/background/runs/"):
            if self._background_runs is None:
                raise RuntimeError("Background Agent runs are unavailable.")
            suffix = path.removeprefix("/background/runs/")
            cancel = suffix.endswith("/cancel")
            run_id = suffix.removesuffix("/cancel").strip("/")
            if method == "GET" and not cancel:
                run = self._background_runs.get_in_workspace(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                    local_session_id=principal.session_id, run_id=run_id,
                )
                events = self._background_runs.list_events(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                    local_session_id=principal.session_id, run_id=run_id, authorize=False,
                )
                return LocalApiResponse(200, _background_run_payload(run, events=events))
            if method == "POST" and cancel:
                run = self._background_runs.request_cancellation_in_workspace(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                    local_session_id=principal.session_id, run_id=run_id,
                )
                return LocalApiResponse(200, _background_run_payload(run))
            if method == "DELETE" and not cancel:
                from app.vault_runtime.background_agent.repository import BackgroundRunConflictError
                try:
                    self._background_runs.delete_in_workspace(
                        user_id=principal.user_id, workspace_id=principal.workspace_id,
                        local_session_id=principal.session_id, run_id=run_id,
                    )
                except BackgroundRunConflictError as exc:
                    return LocalApiResponse(409, {"error": {"code": "run_not_terminal", "message": str(exc)}})
                return LocalApiResponse(200, {"runId": run_id, "deleted": True})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_tasks(self, *, method: str, path: str, headers: Mapping[str, str]) -> LocalApiResponse:
        repository = self._tasks
        identity = self._identity_service
        if repository is None or identity is None:
            raise RuntimeError("Tasks are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/tasks/active":
            items = repository.list_active(user_id=principal.user_id, workspace_id=principal.workspace_id)
            return LocalApiResponse(200, {"tasks": [task_view(item) for item in items]})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_notifications(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        repository = self._notifications
        identity = self._identity_service
        if repository is None or identity is None:
            raise RuntimeError("Notifications are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method in {"POST", "DELETE"}:
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if method == "GET" and path == "/notifications":
            items = repository.list_active(user_id=principal.user_id, workspace_id=principal.workspace_id)
            return LocalApiResponse(200, {"items": items, "unreadCount": len(items)})
        if method == "POST" and path == "/notifications/clear":
            count = repository.dismiss_all(user_id=principal.user_id, workspace_id=principal.workspace_id)
            return LocalApiResponse(200, {"status": "cleared", "clearedCount": count})
        if method == "POST" and path.startswith("/notifications/") and path.endswith("/clear"):
            notification_id = path.removeprefix("/notifications/").removesuffix("/clear").strip("/")
            if not notification_id:
                raise ValueError("Notification id is required.")
            cleared = repository.dismiss(
                user_id=principal.user_id, workspace_id=principal.workspace_id, notification_id=notification_id,
            )
            if not cleared:
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Notification was not found."}})
            return LocalApiResponse(200, {"status": "cleared", "notificationId": notification_id})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_workspace_files(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        service = self._workspace_files
        identity = self._identity_service
        if service is None or identity is None:
            raise RuntimeError("Workspace files are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        params = parse_qs(query, keep_blank_values=True)
        share_id = _query_param(params, "shareId")
        if method == "GET" and path == "/workspace-files":
            directory = _query_param(params, "directory")
            listing = service.list_directory(principal=principal, directory=directory, share_id=share_id)
            return LocalApiResponse(200, listing.to_dict())
        if method == "GET" and path == "/workspace-files/read":
            file_key = _required_query(params, "fileKey")
            read_back = service.read_file(principal=principal, file_key=file_key, share_id=share_id)
            return LocalApiResponse(200, read_back.to_dict())
        if method == "GET" and path == "/workspace-files/download":
            file_key = _required_query(params, "fileKey")
            filename, media_type, content = service.read_file_bytes(
                principal=principal, file_key=file_key, share_id=share_id,
            )
            safe_filename = filename.replace('"', "")
            return LocalApiResponse(
                200, {}, body=content, content_type=media_type,
                headers=(("Content-Disposition", f'attachment; filename="{safe_filename}"'),),
            )
        if method == "GET" and path == "/workspace-files/shares":
            folder_path = _required_query(params, "folderPath")
            items = service.list_shares(principal=principal, folder_path=folder_path)
            return LocalApiResponse(200, {"items": [item.to_dict() for item in items]})
        if method in {"POST", "PUT", "DELETE"}:
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if method == "PUT" and path == "/workspace-files/files":
            payload = _json_object(body)
            result = service.save_file(
                principal=principal,
                file_key=_required_text(payload, "fileKey"),
                content_markdown=_required_text(payload, "contentMarkdown"),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(200, result.to_dict())
        if method == "POST" and path == "/workspace-files/text":
            payload = _json_object(body)
            result = service.write_text_file(
                principal=principal,
                file_key=_required_text(payload, "fileKey"),
                content_markdown=str(payload.get("contentMarkdown") or ""),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(201, result.to_dict())
        if method == "POST" and path == "/workspace-files/directories":
            payload = _json_object(body)
            result = service.create_directory(
                principal=principal,
                directory=_required_text(payload, "directory"),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(201, result.to_dict())
        if method == "POST" and path == "/workspace-files/move":
            payload = _json_object(body)
            result = service.move_path(
                principal=principal,
                source_path=_required_text(payload, "sourcePath"),
                destination_path=_required_text(payload, "destinationPath"),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(200, result.to_dict())
        if method == "POST" and path == "/workspace-files/delete":
            payload = _json_object(body)
            result = service.delete_path(
                principal=principal,
                path=_required_text(payload, "path"),
                recursive=_required_bool(payload, "recursive"),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(200, result.to_dict())
        if method == "POST" and path == "/workspace-files/upload":
            content_type = headers.get("Content-Type") or headers.get("content-type") or ""
            if "multipart/form-data" not in content_type.lower():
                raise ValueError("Workspace upload requires multipart form data.")
            fields, files = parse_multipart_form(body, content_type)
            uploads = [
                WorkspaceFileUpload(filename=filename, content=content)
                for field_name, filename, content in files
                if field_name == "files"
            ]
            result = service.upload_files(
                principal=principal,
                directory=fields.get("directory") or None,
                uploads=uploads,
                share_id=share_id or fields.get("shareId"),
            )
            return LocalApiResponse(201, result.to_dict())
        if method == "POST" and path == "/workspace-files/shares":
            payload = _json_object(body)
            item = service.save_share(
                principal=principal,
                folder_path=_required_text(payload, "folderPath"),
                grantee_user_id=_required_text(payload, "granteeUserId"),
                permission=_required_text(payload, "permission"),
            )
            return LocalApiResponse(200, item.to_dict())
        if method == "POST" and path.startswith("/workspace-files/shares/") and path.endswith("/revoke"):
            share_id_value = path.removeprefix("/workspace-files/shares/").removesuffix("/revoke").strip("/")
            service.revoke_share(principal=principal, share_id=share_id_value)
            return LocalApiResponse(200, {"status": "revoked"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})


def _query_param(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key, [])
    return values[0] if len(values) == 1 and values[0] else None


def _required_query(params: dict[str, list[str]], key: str) -> str:
    value = _query_param(params, key)
    if not value:
        raise ValueError(f"{key} is required.")
    return value


def _json_object(body: bytes, *, max_bytes: int = STRICT_JSON_MAX_BYTES) -> dict[str, Any]:
    try:
        return parse_json_object_bytes(body or b"{}", max_bytes=max_bytes)
    except StrictJSONError as exc:
        if exc.reason == "raw_size":
            raise ValueError(
                "Request body exceeds the upload size limit for this endpoint.",
            ) from exc
        raise ValueError("Request body must be a JSON object.") from exc


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required.")
    return value


def _optional_webrtc_sdp(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    text = value.lstrip("\ufeff")
    if not text.lstrip(" \t").startswith("v=0"):
        return None
    return text


def _optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _local_user_operation(path: str) -> tuple[str, str] | None:
    parts = path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "local-users" or parts[2] not in {"password-reset", "remove"}:
        return None
    user_id = parts[1].strip()
    return (user_id, parts[2]) if user_id else None


def _required_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean.")
    return value


def _required_nonnegative_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer.")
    return value


def _required_object(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object.")
    return value


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


def _external_integration_payload(record) -> dict[str, Any]:
    return {
        "integrationId": record.integration_id,
        "displayName": record.display_name,
        "adapterKind": record.adapter_kind,
        "grants": list(record.grants),
        "status": record.status,
        "createdAt": record.created_at.isoformat(),
        "revokedAt": record.revoked_at.isoformat() if record.revoked_at else None,
    }


def _external_memory_match_payload(match) -> dict[str, Any]:
    memory = match.memory
    payload = _external_memory_record_payload(memory)
    payload.update({
        "score": match.score,
        "matchMethods": list(match.match_methods),
    })
    return payload


def _external_memory_record_payload(memory) -> dict[str, Any]:
    return {
        "memoryId": memory.memory_id,
        "subjectId": memory.subject_id,
        "domain": memory.domain,
        "memoryType": memory.memory_type,
        "memoryKey": memory.memory_key,
        "content": memory.content_text,
        "sourceAuthority": memory.source_authority,
        "confidence": memory.confidence,
        "sensitivity": memory.sensitivity,
        "visibility": memory.visibility,
    }


def _text_tuple(payload: Mapping[str, Any], key: str, *, required: bool = False) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None and not required:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings.")
    result = tuple(item.strip() for item in value if item.strip())
    if required and not result:
        raise ValueError(f"{key} is required.")
    return result


def _background_request(payload: Mapping[str, Any]) -> BackgroundRunRequest:
    result_schema = payload.get("resultSchema")
    if not isinstance(result_schema, dict):
        raise ValueError("resultSchema is required.")
    limits_raw = payload.get("limits")
    limits = RunLimits(**limits_raw) if isinstance(limits_raw, dict) else RunLimits()
    return BackgroundRunRequest(
        run_id=str(uuid4()), objective=_required_text(payload, "objective"),
        instruction_profile=_required_text(payload, "instructionProfile"),
        success_criteria=_text_tuple(payload, "successCriteria", required=True),
        result_schema=result_schema,
        recipe=ExecutionRecipe(str(payload.get("recipe", ExecutionRecipe.SELF_REVIEW.value))),
        autonomy=AutonomyProfile(str(payload.get("autonomy", AutonomyProfile.LIMITED.value))),
        limits=limits, goal_type=str(payload.get("goalType", "general")),
        context_summary=str(payload.get("contextSummary", "")),
        expected_result=str(payload.get("expectedResult", "")),
        scope=str(payload.get("scope", "")), exclusions=_text_tuple(payload, "exclusions"),
        source_requirements=str(payload.get("sourceRequirements", "")),
        workspace_destination=_optional_text(payload, "workspaceDestination"),
        original_request=_required_text(payload, "originalRequest"),
        verification_method=_required_text(payload, "verificationMethod"),
        completion_conditions=_text_tuple(payload, "completionConditions", required=True),
        stop_conditions=_text_tuple(payload, "stopConditions"),
        requested_tool_names=_text_tuple(payload, "requestedToolNames"),
    )


def _background_run_payload(run, events=()) -> dict[str, Any]:
    from app.vault_runtime.background_agent.progress import explain_failure, project_progress
    progress = project_progress(run.state, run.request.recipe, events)
    reasoning_entries = [
        {
            "type": item.event_type,
            "createdAt": item.created_at.isoformat(),
            "detail": item.detail,
        }
        for item in events
        if item.event_type in {"reasoning_summary", "agent_evidence"}
    ]
    invocation = "voice_goal" if run.request.instruction_profile == "voice-goal" else run.request.instruction_profile
    return {
        "runId": run.request.run_id, "agentKind": "background",
        "invocationType": invocation,
        "originId": run.local_session_id,
        "objective": run.request.objective,
        "recipe": run.request.recipe.value,
        "state": run.state.value, "cancellationRequested": run.cancellation_requested,
        "output": run.output,
        "failure": ({"code": run.failure_code, "message": run.failure_message}
                    if run.failure_code else None),
        "failureCode": run.failure_code,
        "failureMessage": run.failure_message,
        "failureExplanation": explain_failure(run),
        "modelTurns": run.model_turns,
        "toolCalls": run.tool_calls, "createdAt": run.created_at.isoformat(),
        "updatedAt": run.updated_at.isoformat(),
        "completedAt": run.completed_at.isoformat() if run.completed_at else None,
        "reasoningEntries": reasoning_entries,
        "progress": {
            "label": progress.label,
            "fraction": progress.fraction,
            "active": progress.active,
            "tone": progress.tone,
            "activity": progress.activity,
            "modelTurns": progress.model_turns or run.model_turns,
            "toolCalls": progress.tool_calls or run.tool_calls,
            "timeline": list(progress.timeline),
        },
    }


def _cookie_value(headers: Mapping[str, str], name: str) -> str:
    cookie = SimpleCookie()
    cookie.load(_header(headers, "cookie") or "")
    morsel = cookie.get(name)
    return morsel.value if morsel is not None else ""


def _session_token(headers: Mapping[str, str]) -> str:
    authorization = _header(headers, "authorization") or ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    token = _cookie_value(headers, "resono_refresh")
    if not token:
        from app.vault_runtime.local_identity.repository import LocalSessionError
        raise LocalSessionError("Local session is required.")
    return token


def _bearer_token(headers: Mapping[str, str]) -> str:
    authorization = _header(headers, "authorization") or ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    from app.vault_runtime.external_memory.repository import ExternalMemoryAuthorizationError
    raise ExternalMemoryAuthorizationError("Integration bearer credential is required.")


def _csrf_token(headers: Mapping[str, str]) -> str:
    cookie_token = _cookie_value(headers, "resono_csrf")
    header_token = _header(headers, "x-resono-csrf") or ""
    if not cookie_token or not header_token or not compare_digest(cookie_token, header_token):
        from app.vault_runtime.local_identity.repository import LocalSessionError
        raise LocalSessionError("CSRF proof is invalid.")
    return header_token


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _principal_payload(principal: LocalPrincipal) -> dict[str, Any]:
    return {
        "userId": principal.user_id, "username": principal.username,
        "displayName": principal.display_name, "experienceStyle": principal.experience_style,
        "isDeviceOwner": principal.is_device_owner,
        "passwordMode": principal.password_mode,
        "mustChangePassword": principal.must_change_password,
        "ageGroup": principal.age_group,
        "sessionId": principal.session_id, "activeWorkspaceId": principal.workspace_id,
        "expiresAt": principal.expires_at.isoformat(),
    }


def _session_response(
    tokens: LocalSessionTokens, *, status_code: int = 200, secure: bool = False,
) -> LocalApiResponse:
    return LocalApiResponse(
        status_code, {"user": _principal_payload(tokens.principal)},
        _session_cookie_headers(tokens.session_token, tokens.csrf_token, secure=secure),
    )


def _tool_category(tool_id: str, name: str) -> str:
    """Expose the canonical tool family already encoded in built-in names/IDs."""
    if tool_id.startswith("mcp:"):
        return "MCP"
    prefixes = (
        ("memory_", "Memory"), ("email_", "Email"),
        ("calendar_", "Calendar"), ("contacts_", "Contacts"),
        ("agent2agent_", "Agent2Agent"),
    )
    for prefix, category in prefixes:
        if name.startswith(prefix):
            return category
    if name == "web_search":
        return "Web"
    if name == "load_agent_skill":
        return "Skills"
    return "Other"


def _session_cookie_headers(
    session_token: str, csrf_token: str, *, secure: bool = False,
) -> tuple[tuple[str, str], ...]:
    suffix = _secure_cookie_suffix(secure)
    return (
        ("Set-Cookie", f"resono_refresh={session_token}; Path=/; HttpOnly; SameSite=Strict{suffix}"),
        ("Set-Cookie", f"resono_csrf={csrf_token}; Path=/; SameSite=Strict{suffix}"),
    )


def _clear_session_cookie_headers(*, secure: bool = False) -> tuple[tuple[str, str], ...]:
    suffix = _secure_cookie_suffix(secure)
    return (
        ("Set-Cookie", f"resono_refresh=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{suffix}"),
        ("Set-Cookie", f"resono_csrf=; Path=/; Max-Age=0; SameSite=Strict{suffix}"),
    )


def _request_uses_secure_cookies(headers: Mapping[str, str]) -> bool:
    return (_header(headers, "x-resono-request-secure") or "") == "1"


def _secure_cookie_suffix(secure: bool) -> str:
    return "; Secure" if secure else ""
