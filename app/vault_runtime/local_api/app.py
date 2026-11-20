from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import SplitResult, urlsplit

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.background_agent.repository import BackgroundRunRepository
from app.vault_runtime.voice.provider import ProviderCredential, VoiceSessionCoordinator
from app.vault_runtime.voice.repository import VoiceSessionRepository
from app.vault_runtime.voice.tools import VoiceToolRuntime
from app.vault_runtime.voice.credentials import VoiceProviderCredentialStore
from app.vault_runtime.voice.oauth import ProviderOAuthService
from app.vault_runtime.email.runtime import LocalEmailRuntime
from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.calendar.runtime import LocalCalendarRuntime
from app.vault_runtime.extensions.repository import ExtensionRepository
from app.vault_runtime.extensions.mcp_accounts import McpAccounts
from app.vault_runtime.extensions.secrets import ExtensionSecretStore
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.extensions.mcp_lifecycle import McpLifecycle
from app.vault_runtime.extensions.plugin_services import PluginVaultServices
from app.vault_runtime.memory.voice_learning import VoiceMemoryLearning
from app.vault_runtime.external_memory.repository import ExternalMemoryRepository
from app.vault_runtime.external_memory.service import ExternalMemoryService
from app.vault_runtime.commands.service import CommandService
from app.vault_runtime.folders.service import FolderService
from app.vault_runtime.link_companion.repository import LinkCompanionRepository
from app.vault_runtime.agent_network.service import A2AService
from app.vault_runtime.help_assistant import HelpAssistant
from app.vault_runtime.builtin_plugins import BuiltinPluginRepository
from app.vault_runtime.workspace_files.service import WorkspaceFileService
from app.vault_runtime.tasks.repository import TaskRepository
from app.vault_runtime.notifications.repository import NotificationRepository
from app.vault_runtime.live_memory.preferences import LiveMemoryPreference, LiveMemoryPreferenceRepository
from app.vault_runtime.local_api.routes.common import LocalApiResponse, _session_token
from app.vault_runtime.local_api.routes.live_memory import LiveMemoryRoutes
from app.vault_runtime.local_api.routes.conversations import ConversationRoutes
from app.vault_runtime.local_api.routes.plugin_services import PluginServiceRoutes
from app.vault_runtime.local_api.routes.identity import IdentityRoutes, _session_cookie_headers
from app.vault_runtime.local_api.routes.background import BackgroundRoutes
from app.vault_runtime.local_api.routes.voice import VoiceRoutes
from app.vault_runtime.local_api.routes.agent_network import AgentNetworkRoutes
from app.vault_runtime.local_api.routes.extensions import ExtensionRoutes
from app.vault_runtime.local_api.routes.external_memory import ExternalMemoryRoutes
from app.vault_runtime.local_api.routes.link_companion import LinkCompanionRoutes
from app.vault_runtime.local_api.routes.approvals import ApprovalRoutes
from app.vault_runtime.local_api.routes.commands import CommandRoutes
from app.vault_runtime.local_api.routes.folders import FolderRoutes
from app.vault_runtime.local_api.routes.providers import ProviderRoutes
from app.vault_runtime.local_api.routes.help import HelpRoutes
from app.vault_runtime.local_api.routes.notifications import NotificationRoutes
from app.vault_runtime.local_api.routes.tasks import TaskRoutes
from app.vault_runtime.local_api.routes.workspace_files import WorkspaceFileRoutes
from app.vault_runtime.local_api.routes.mail import MailRoutes
from app.vault_runtime.local_api.routes.contacts import ContactRoutes
from app.vault_runtime.local_api.routes.calendar import CalendarRoutes


# Re-exported for callers and tests that import them from this module.
__all__ = ["LocalApiResponse", "VaultLocalApiApp", "_session_cookie_headers", "_session_token"]


class VaultLocalApiHealthStore(Protocol):
    def health(self) -> dict[str, Any]: ...


class ProviderCredentialResolver(Protocol):
    def __call__(self, principal: LocalPrincipal, provider_key: str) -> ProviderCredential: ...


class VaultLocalApiApp(
    LiveMemoryRoutes, ConversationRoutes, PluginServiceRoutes, IdentityRoutes, BackgroundRoutes, VoiceRoutes,
    AgentNetworkRoutes, ExtensionRoutes, ExternalMemoryRoutes, LinkCompanionRoutes, ApprovalRoutes,
    CommandRoutes, FolderRoutes, ProviderRoutes, HelpRoutes, NotificationRoutes, TaskRoutes,
    WorkspaceFileRoutes, MailRoutes, ContactRoutes, CalendarRoutes,
):
    """Phase-bounded extraction of the Voice Vault local API foundation."""

    def __init__(
        self, *, store: VaultLocalApiHealthStore, token: str, max_body_bytes: int = 1_048_576,
        identity_service: LocalIdentityService | None = None,
        voice_coordinator: VoiceSessionCoordinator | None = None,
        voice_sessions: VoiceSessionRepository | None = None,
        provider_credential_resolver: ProviderCredentialResolver | None = None,
        background_runs: BackgroundRunRepository | None = None,
        direct_runs: Any = None,
        extension_imports: ExtensionImportService | None = None,
        extensions: ExtensionRepository | None = None,
        extension_secrets: ExtensionSecretStore | None = None,
        mcp_accounts: McpAccounts | None = None,
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
        folders: FolderService | None = None,
        commands: CommandService | None = None,
        tool_routing: Any | None = None,
        link_companion: LinkCompanionRepository | None = None,
        link_tools: Any | None = None,
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
        self._background_runs = background_runs
        self._direct_runs = direct_runs
        self._extension_imports = extension_imports
        self._extensions = extensions
        self._extension_secrets = extension_secrets
        self._mcp_accounts = mcp_accounts
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
        self._folders = folders
        self._commands = commands
        self._tool_routing = tool_routing
        self._link_companion = link_companion
        self._link_tools = link_tools
        self._companion_voice = None  # Built on first Link Companion voice use.
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
        if self._companion_voice is not None:
            self._companion_voice.shutdown()  # Hang up live phone calls and finalize their transcripts.
        if self._conversation_runtime is not None:
            self._conversation_runtime.close()
        jobs = self._background_jobs()
        if jobs is not None:
            jobs.stop()
        if self._a2a_service is not None:
            self._a2a_service.stop()

    def _background_jobs(self):
        """The durable worker of the background coordinator, when coordination is on."""
        coordinator = getattr(self._conversation_runtime, "background_coordinator", None)
        return getattr(coordinator, "jobs", None)

    def handle(
        self, *, method: str, target: str, headers: Mapping[str, str], body: bytes = b""
    ) -> LocalApiResponse:
        target_parts = urlsplit(target)
        path = target_parts.path
        for route in _ROUTES:  # First match wins: the table order is the order of precedence.
            if route.matches(self, method, path):
                return getattr(self, route.handler)(
                    method=method, path=path, target_parts=target_parts, headers=headers, body=body,
                )
        return LocalApiResponse(
            status_code=404,
            payload={"error": {"code": "not_found", "message": "Not found."}},
        )

    def _route_health(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        return self._health()

    def _health(self) -> LocalApiResponse:
        return LocalApiResponse(status_code=200, payload={"status": "ok", "store": self._store.health()})


@dataclass(frozen=True, slots=True)
class _Route:
    """One dispatcher entry: a request matches by exact path or path prefix (and optional suffix)."""

    handler: str  # VaultLocalApiApp method: (method=, path=, target_parts=, headers=, body=) -> response
    paths: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    suffix: str | None = None
    method: str | None = None  # Only this HTTP method; other methods fall through to later entries.
    needs_identity: bool = False  # Only when the local identity service is configured.

    def matches(self, app: "VaultLocalApiApp", method: str, path: str) -> bool:
        if self.method is not None and method.upper() != self.method:
            return False
        if self.needs_identity and app._identity_service is None:
            return False
        if path in self.paths:
            return True
        return path.startswith(self.prefixes) and (self.suffix is None or path.endswith(self.suffix))


_ROUTES: tuple[_Route, ...] = (
    _Route("_route_health", paths=("/health",), method="GET"),
    _Route("_route_conversations", paths=("/conversations",), prefixes=("/conversations/",)),
    _Route("_route_live_memory", paths=("/live-memory",)),
    _Route("_route_live_tool_routing", paths=("/live-tool-routing",)),
    _Route("_route_plugin_services", prefixes=("/plugin-services/v1/",)),
    _Route("_route_identity_setup_start", paths=("/identity/setup/start",), method="GET", needs_identity=True),
    _Route("_route_identity", prefixes=("/identity/", "/me", "/workspaces", "/local-users"), needs_identity=True),
    _Route("_route_runtime", prefixes=("/system-agents", "/tools", "/voice/", "/background/"), needs_identity=True),
    _Route("_route_agent2agent", prefixes=("/agent2agent",), needs_identity=True),
    _Route("_route_extensions", prefixes=("/extensions",), needs_identity=True),
    _Route("_route_builtin_plugins", prefixes=("/builtin-plugins",), needs_identity=True),
    _Route("_route_external_memory_pairing", prefixes=("/external-memory/pairing/",)),
    _Route("_route_external_memory_integrations", prefixes=("/external-memory/integrations",), needs_identity=True),
    _Route("_route_link_companion_tools", prefixes=("/link-companion/tools/",)),
    _Route("_route_link_companion_voice", prefixes=("/link-companion/voice/",)),
    _Route("_route_link_companion_chat", prefixes=("/link-companion/chat/",)),
    _Route("_route_link_front_door", paths=("/v1/responses", "/link/v1/capabilities"),
           prefixes=("/v1/responses/", "/link/v1/responses/", "/link/v1/drafts")),
    _Route("_route_link_companion_pairing", paths=("/link-companion/pairing/start", "/link-companion/pairing/status",
                                       "/link-companion/agent-network/apply", "/link-companion/release")),
    _Route("_route_link_companion", prefixes=("/link-companion",), needs_identity=True),
    _Route("_route_approvals", paths=("/approvals",), prefixes=("/approvals/",), needs_identity=True),
    _Route("_route_commands", paths=("/admin/commands/settings",), prefixes=("/commands",), needs_identity=True),
    _Route("_route_folders", paths=("/folders",), prefixes=("/folders/", "/admin/folders", "/admin/folder-access/"),
           needs_identity=True),
    _Route("_route_folders", prefixes=("/admin/users/",), suffix="/folder-access", needs_identity=True),
    _Route("_route_external_memory", prefixes=("/external-memory/v1/",)),
    _Route("_route_providers", prefixes=("/providers/",), needs_identity=True),
    _Route("_route_help", prefixes=("/help/",), needs_identity=True),
    _Route("_route_notifications", prefixes=("/notifications",), needs_identity=True),
    _Route("_route_tasks", prefixes=("/tasks",), needs_identity=True),
    _Route("_route_workspace_files", prefixes=("/workspace-files",), needs_identity=True),
    _Route("_route_mail", prefixes=("/mail/",), needs_identity=True),
    _Route("_route_contacts", prefixes=("/contacts",), needs_identity=True),
    _Route("_route_calendar", prefixes=("/calendar",), needs_identity=True),
)


