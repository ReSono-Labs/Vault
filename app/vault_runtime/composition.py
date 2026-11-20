"""Standalone composition root for the admitted local Vault runtime modules."""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Thread

import psycopg

from app.vault_runtime.extensions.archives import ArchiveInspector
from app.vault_runtime.extensions.activation import SkillActivation
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.mcp_client import HttpMcpTransport, McpClient
from app.vault_runtime.extensions.mcp_lifecycle import McpLifecycle
from app.vault_runtime.extensions.repository import ExtensionRepository
from app.vault_runtime.extensions.secrets import ExtensionSecretStore, LocalMasterKey
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.extensions.mcp_runtime import McpRuntimeSupervisor
from app.vault_runtime.extensions.plugin_services import PluginVaultServices
from app.vault_runtime.email.runtime import LocalEmailRuntime
from app.vault_runtime.email.tools import register_email_tools
from app.vault_runtime.background_agent.repository import BackgroundRunRepository
from app.vault_runtime.agent_network import A2AService, register_a2a_tools
from app.vault_runtime.agent_network.collab import register_collab_tools
from app.vault_runtime.agent_network.client import A2AClient
from app.vault_runtime.agent_network.inbound import (
    A2AInboundApp,
    A2AInboundHttpServer,
    listen_host_from_env,
    listen_port_from_env,
)
from app.vault_runtime.agent_network.repository import A2ARepository
from app.vault_runtime.contacts_tools import register_contacts_tools
from app.vault_runtime.calendar.runtime import LocalCalendarRuntime
from app.vault_runtime.calendar.tools import register_calendar_tools
from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from app.vault_runtime.local_api.stores import PostgresVaultHealthStore
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.migrations import run as run_migrations
from app.vault_runtime.live_memory.preferences import LiveMemoryPreferenceRepository
from app.vault_runtime.memory.service import MemoryService
from app.vault_runtime.memory.tools import register_memory_tools
from app.vault_runtime.memory.voice_learning import VoiceMemoryLearning
from app.vault_runtime.decision_learning.voice_review import VoiceDecisionReview
from app.vault_runtime.conversation.runtime import ConversationRuntime
from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
from app.vault_runtime.memory.pipeline import MemoryPipeline
from app.vault_runtime.external_memory.repository import ExternalMemoryRepository
from app.vault_runtime.external_memory.service import ExternalMemoryService
from app.vault_runtime.commands.repository import CommandRepository
from app.vault_runtime.commands.service import CommandService
from app.vault_runtime.commands.tools import register_command_tools
from app.vault_runtime.folders.repository import FolderRepository
from app.vault_runtime.link_companion.repository import LinkCompanionRepository
from app.vault_runtime.folders.service import FolderService
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.web_search import register_web_search_tool
from app.vault_runtime.help_assistant import HelpAssistant
from app.vault_runtime.builtin_plugins import BuiltinPluginRepository
from app.vault_runtime.builtin_plugin_tools import register_builtin_plugin_tools
from app.vault_runtime.voice.context import VoiceContextBuilder
from app.vault_runtime.voice.credentials import VoiceProviderCredentialStore
from app.vault_runtime.voice.openai_realtime import OpenAIRealtimeProvider
from app.vault_runtime.voice.gemini_live import GeminiLiveProvider
from app.vault_runtime.voice.xai_realtime import XAIRealtimeProvider
from app.vault_runtime.voice.provider import ProviderRegistry, VoiceSessionCoordinator
from app.vault_runtime.voice.oauth import ProviderOAuthService
from app.vault_runtime.voice.repository import VoiceSessionRepository
from app.vault_runtime.voice.tools import LocalToolAuthority, VoiceToolRuntime
from app.vault_runtime.voice.modes import VoiceModeService, register_voice_mode_tool
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from app.vault_runtime.workspace_storage import WorkspaceStorage
from app.vault_runtime.workspace_files.repository import WorkspaceFileRepository
from app.vault_runtime.workspace_files.service import WorkspaceFileService
from app.vault_runtime.workspace_files.tools import register_workspace_file_tools
from app.vault_runtime.tasks.repository import TaskRepository
from app.vault_runtime.tasks_tools import register_tasks_tools
from app.vault_runtime.notifications.repository import NotificationRepository
from app.vault_runtime.system_agents.inventory import AgentKind


def build_local_app(config: VaultLocalApiConfig) -> VaultLocalApiApp:
    """Compose only accepted modules; no cloud plane or non-system agent registry."""
    database_url = config.database_url_value()
    data_root = Path(config.data_root)
    setup_hash_file = Path(config.setup_credential_hash_file) if config.setup_credential_hash_file else None

    def consume_setup_credential() -> None:
        if setup_hash_file is None:
            return
        setup_hash_file.unlink(missing_ok=True)
        (setup_hash_file.parent / "setup-credential").unlink(missing_ok=True)

    workspace_storage = WorkspaceStorage(Path(config.storage_mount_point))
    workspace_storage.ensure_root()
    # The schema comes only from numbered migrations, applied once under an advisory lock.
    run_migrations(database_url, storage=workspace_storage)
    identity_repository = LocalIdentityRepository(database_url=database_url)
    live_memory_preferences = LiveMemoryPreferenceRepository(database_url=database_url)
    storage_identities = identity_repository.active_storage_identities()
    for owner_user_id, workspace_id in storage_identities:
        workspace_storage.reconcile_identity(
            user_id=owner_user_id, workspace_id=workspace_id,
        )
    identities = LocalIdentityService(
        repository=identity_repository,
        setup_credential_hash=config.setup_credential_hash_value(),
        setup_credential_consumer=consume_setup_credential,
        workspace_storage=workspace_storage,
    )
    memories = MemoryRepository(database_url=database_url)
    memories.require_semantic_suppression = True
    voices = VoiceSessionRepository(database_url=database_url)
    extensions = ExtensionRepository(database_url=database_url)
    personal_data = PersonalDataRepository(database_url=database_url)
    builtin_plugins = BuiltinPluginRepository(database_url=database_url)

    from app.vault_runtime.background_agent.coordination_repository import CoordinationRepository

    coordination_repo = CoordinationRepository(database_url=database_url)
    background_authority = None
    if config.background_coordination_enabled:
        from app.vault_runtime.background_agent.authority import BackgroundAuthority
        background_authority = BackgroundAuthority(database_url=database_url)

    tool_authority = LocalToolAuthority(database_url=database_url, background_authority=background_authority)
    catalog = ToolCatalog(
        authorizer=tool_authority.authorize,
        background_authorizer=tool_authority.authorize_background if background_authority is not None else None,
    )
    provider_credentials = VoiceProviderCredentialStore(
        database_url=database_url,
        master_key=LocalMasterKey(data_root / "keys" / "voice-provider.key"),
        google_oauth_client_id=config.google_oauth_client_id,
        google_oauth_client_secret=config.google_oauth_client_secret,
    )
    provider_oauth = ProviderOAuthService(
        credentials=provider_credentials,
        google_client_id=config.google_oauth_client_id,
        google_client_secret=config.google_oauth_client_secret,
    )
    from app.vault_runtime.memory.local_embeddings import LocalEmbeddingFactory
    embedding_factory = LocalEmbeddingFactory()
    memory_service = MemoryService(
        repository=memories, embedder_factory=embedding_factory,
        reviewer_factory=lambda user_id,workspace_id:OpenAIMemoryReviewer(credentials=provider_credentials,
            user_id=user_id,workspace_id=workspace_id),
    )

    background_coordinator_holder: list[object] = []
    background_routines_holder: list[object] = []

    def _source_event_sink(source_kind: str):
        if not config.background_coordination_enabled:
            return None
        from datetime import datetime, timezone
        from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
        from app.vault_runtime.background_agent.routines import source_fingerprint_changed

        def sink(account_id: str, workspace_id: str, source_id: str, payload: dict[str, object]) -> None:
            if not background_routines_holder or not background_coordinator_holder:
                return
            scope = OwnerScope(account_id, workspace_id)
            now = datetime.now(timezone.utc)
            routines_svc = background_routines_holder[0]
            coord_svc = background_coordinator_holder[0]
            if not routines_svc.observe_source_change(
                scope, source_kind=source_kind, source_id=source_id, items=payload, now=now,
            ):
                return
            _, fp = source_fingerprint_changed(None, payload)
            coord_svc.observe(scope, source_kind, f"{source_id}:{fp}", dict(payload))

        return sink

    email_runtime = LocalEmailRuntime(
        database_url=database_url,
        master_key=LocalMasterKey(data_root / "keys" / "mail-credentials.key"),
        background_event_sink=_source_event_sink("mail_sync"),
    )
    calendar_runtime = LocalCalendarRuntime(
        database_url=database_url,
        master_key=LocalMasterKey(data_root / "keys" / "calendar-credentials.key"),
        records=personal_data,
        background_event_sink=_source_event_sink("calendar_sync"),
    )
    tasks = TaskRepository(database_url=database_url)

    background_actions = None
    background_action_bridge = None
    if config.background_coordination_enabled:
        from app.vault_runtime.background_agent.action_bridge import (
            BackgroundActionBridge,
            current_tool_authorizer,
        )
        from app.vault_runtime.background_agent.action_domains import (
            MailSendDomain,
            TaskActionDomain,
            calendar_domain,
            contacts_domain,
        )
        from app.vault_runtime.background_agent.actions import BackgroundActions
        from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
        from app.vault_runtime.tools.definitions import ToolInvocationContext

        def _work_session(scope) -> str | None:
            if getattr(scope, "grant_id", None) or coordination_repo is None:
                return None
            row = coordination_repo.get(OwnerScope(scope.user_id, scope.workspace_id), scope.work_id)
            val = row.get("local_session_id")
            return str(val) if isinstance(val, str) and val else None

        def _domain_context(scope, tool_name: str) -> ToolInvocationContext:
            return ToolInvocationContext(
                agent=AgentKind.BACKGROUND,
                user_id=scope.user_id,
                workspace_id=scope.workspace_id,
                tool_call_id=f"{tool_name}:{scope.work_id}:{scope.intent_version}"[:128],
                local_session_id=_work_session(scope),
                background_scope=scope,
            )

        action_domains = {
            "tasks": TaskActionDomain(repository=tasks),
            "calendar": calendar_domain(
                records=personal_data, runtime=calendar_runtime, context_factory=_domain_context,
            ),
            "contacts": contacts_domain(
                records=personal_data, context_factory=_domain_context, usage=False,
            ),
            "contacts_use": contacts_domain(
                records=personal_data, context_factory=_domain_context, usage=True,
            ),
            "mail": MailSendDomain(
                runtime=email_runtime, context_factory=_domain_context, kind="mail", mailbox_role="normal_email",
            ),
            "agent_mail": MailSendDomain(
                runtime=email_runtime, context_factory=_domain_context, kind="agent_mail", mailbox_role="agent_mail",
            ),
        }
        background_actions = BackgroundActions(
            database_url=database_url,
            domains=action_domains,
            authorizer=current_tool_authorizer(
                catalog=catalog, tool_authority=tool_authority, work_session=_work_session,
            ),
        )
        background_action_bridge = BackgroundActionBridge(
            actions=background_actions, domains=action_domains,
        )

    register_memory_tools(catalog=catalog, repository=memories, service=memory_service)
    register_contacts_tools(catalog=catalog, store=personal_data, background_actions=background_action_bridge)
    register_web_search_tool(catalog=catalog, credentials=provider_credentials)
    register_builtin_plugin_tools(catalog=catalog, repository=builtin_plugins, credentials=provider_credentials)
    decision_review = None
    if config.decision_review_enabled:
        from app.vault_runtime.decision_learning.rules import DecisionRuleRepository
        decision_review = VoiceDecisionReview(database_url=database_url,catalog=catalog,credentials=provider_credentials,
            repository_type=DecisionRuleRepository)
    notifications = NotificationRepository(database_url=database_url)

    background_coordinator = None
    resumable_executor = None
    if config.background_coordination_enabled:
        from app.vault_runtime.background_agent.coordinator import BackgroundCoordinator
        from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor
        from app.vault_runtime.background_agent.results import BackgroundResults
        from app.vault_runtime.background_agent.routines import BackgroundRoutines

        resumable_executor = ResumableBackgroundExecutor(
            credentials=provider_credentials,
            memories=memory_service,
            actions=background_actions,
            authority=background_authority,
            catalog=catalog,
            database_url=database_url,
        )
        background_results = BackgroundResults(
            database_url=database_url,
            notifications=notifications,
        )
        background_coordinator = BackgroundCoordinator(
            database_url=database_url,
            executor=resumable_executor,
            catalog=catalog,
            results=background_results,
            auto_dispatch=True,
        )
        background_coordinator.jobs._schema_ensured = True  # migration 0001 created the queue
        background_routines = BackgroundRoutines(
            database_url=database_url,
            jobs=background_coordinator.jobs,
        )
        background_coordinator.jobs.attach_routines(background_routines)
        background_coordinator_holder.append(background_coordinator)
        background_routines_holder.append(background_routines)
        from app.vault_runtime.background_agent.coordinator_tools import register_background_conversation_tools

        register_background_conversation_tools(
            catalog=catalog, database_url=database_url,
            resolve_principal=identity_repository.resolve_review_principal,
            coordinator=background_coordinator,
        )
        from app.vault_runtime.background_agent.scratchpad import CoordinatorScratchpad, register_scratchpad_tools
        coordinator_scratchpad = CoordinatorScratchpad(database_url=database_url)
        register_scratchpad_tools(catalog=catalog, scratchpad=coordinator_scratchpad)

    voice_learning = VoiceMemoryLearning(
        memories=memories, sessions=voices, credentials=provider_credentials,
        embedder_factory=embedding_factory,
        decision_finalize=decision_review.finalize if decision_review is not None else None,
        background_coordinator=background_coordinator,
    )
    external_integrations = ExternalMemoryRepository(database_url=database_url)
    folder_repository = FolderRepository(database_url=database_url)
    link_companion = LinkCompanionRepository(database_url=database_url)
    from app.vault_runtime.link_companion.tools import CompanionLinkTools
    link_tools = CompanionLinkTools(catalog=catalog, authority=tool_authority,
                                    pairing=lambda: link_companion.link_session_id() if (link_companion.current_link() or {}).get("status") == "paired" else None)
    folders = FolderService(
        repository=folder_repository,
        locations=config.device_locations,
        documents_folder=config.documents_folder,
    )
    # Left over from the removed host helper; it encrypted credentials nothing uses now.
    (data_root / "keys" / "host-filesystem.key").unlink(missing_ok=True)

    def finalize_external_memory(user_id: str, workspace_id: str, session_id: str):
        reviewer = OpenAIMemoryReviewer(
            credentials=provider_credentials, user_id=user_id, workspace_id=workspace_id,
        )
        embedder = None
        try:
            embedder = embedding_factory(user_id, workspace_id)
        except Exception:
            pass
        return MemoryPipeline(repository=memories, reviewer=reviewer).finalize(
            user_id=user_id, workspace_id=workspace_id, voice_session_id=session_id,
            embedder=embedder, embedding_provider="openai" if embedder is not None else None,
        )

    external_memory = ExternalMemoryService(
        integrations=external_integrations, memories=memories,
        memory_service=memory_service, finalize=finalize_external_memory,
    )
    plugin_services = PluginVaultServices(
        repository=extensions,
        key=LocalMasterKey(data_root / "keys" / "plugin-capabilities.key"),
        memories=memories, memory_service=memory_service,
        finalize=finalize_external_memory, service_url=config.plugin_service_url,
    )
    a2a_repository = A2ARepository(
        database_url=database_url,
        master_key=LocalMasterKey(data_root / "keys" / "agent-network.key"),
    )
    a2a_service = A2AService(repository=a2a_repository, client=A2AClient())
    register_a2a_tools(catalog, a2a_service, builtin_plugins=builtin_plugins)
    register_collab_tools(catalog, a2a_service, builtin_plugins=builtin_plugins)
    a2a_service.start()

    from app.vault_runtime.memory_search.indexed import INDEXED_QUERY_OPTIONS, PgvectorMemorySearchBackend
    from app.vault_runtime.memory_search.maintenance import IndexedMemoryMaintenance
    # One pgvector backend: MemoryService switches to it once the indexes are ready; Chat preparation uses it.
    indexed_memory_search = PgvectorMemorySearchBackend(memories=memories, options=INDEXED_QUERY_OPTIONS)
    memory_maintenance = IndexedMemoryMaintenance(database_url=database_url, service=memory_service,
        identities=identity_repository, enabled=config.indexed_memory_enabled,
        indexed_backend=indexed_memory_search)
    memory_maintenance.start()
    background_runs = BackgroundRunRepository(database_url=database_url)
    # Old-engine rows left active by an earlier process can never finish now: mark them failed.
    background_runs.recover_interrupted()
    if background_coordinator is not None:
        # The durable worker runs routines, check-ins, wakes and coordinator work; the app stops it.
        background_coordinator.jobs.start()
    direct_runs = None
    if background_coordinator is not None:
        from app.vault_runtime.background_agent.direct_runs import DirectBackgroundRuns
        # A2A inbound (owner decision 5-B): a direct one-shot run on the durable engine.
        direct_runs = DirectBackgroundRuns(coordinator=background_coordinator, database_url=database_url)
    inbound_app = A2AInboundApp(
        repository=a2a_repository, builtin_plugins=builtin_plugins,
        background=direct_runs, runs=direct_runs,
        sessions=identity_repository,
    )
    a2a_service.attach_inbound(inbound_app)
    try:
        inbound_http = A2AInboundHttpServer(
            inbound_app, host=listen_host_from_env(), port=listen_port_from_env(),
        )
        inbound_http.start()
        a2a_service._inbound_http = inbound_http
    except OSError:
        logging.getLogger(__name__).exception("vault A2A inbound listener did not start")
    help_assistant = HelpAssistant(
        credentials=provider_credentials,
        source_root=Path("/opt/resono-vault/help-source"),
        data_root=data_root,
    )
    register_email_tools(
        catalog=catalog, runtime=email_runtime, builtin_plugins=builtin_plugins,
        background_actions=background_action_bridge,
    )
    register_calendar_tools(
        catalog=catalog, runtime=calendar_runtime, records=personal_data,
        background_actions=background_action_bridge,
    )
    register_tasks_tools(
        catalog=catalog, repository=tasks, builtin_plugins=builtin_plugins,
        background_actions=background_action_bridge,
    )
    workspace_file_repository = WorkspaceFileRepository(database_url=database_url)
    workspace_files = WorkspaceFileService(
        workspace_file_repository,
        workspace_storage,
        folders=folders,
    )
    register_workspace_file_tools(catalog=catalog, service=workspace_files)
    command_repository = CommandRepository(database_url=database_url)
    commands = CommandService(
        repository=command_repository, folders=folders, scratch_root=data_root / "runtime" / "commands",
    )
    register_command_tools(catalog=catalog, service=commands)
    extension_root = data_root / "extensions"
    skill_activation = SkillActivation(repository=extensions, extension_root=extension_root)
    catalog.register(skill_activation.tool_definition())
    voice_modes = VoiceModeService()
    register_voice_mode_tool(catalog, voice_modes)
    coordinator = VoiceSessionCoordinator(
        sessions=voices,
        contexts=VoiceContextBuilder(memories=memories, skills=skill_activation, builtin_plugins=builtin_plugins), tools=catalog,
        providers=ProviderRegistry((OpenAIRealtimeProvider(), GeminiLiveProvider(), XAIRealtimeProvider())),
        tool_authority=tool_authority,
        voice_modes=voice_modes,
    )
    voice_tools = VoiceToolRuntime(catalog=catalog, authority=tool_authority, voice_modes=voice_modes)
    extension_files = ExtensionFilesystem(extension_root)
    extension_files.recover()
    # Name-keyed storage shared across workspaces: keep the bytes, block access until resolved.
    storage_conflicts = extensions.flag_storage_conflicts()
    if storage_conflicts:
        logging.getLogger(__name__).warning("extension_storage_conflicts blocked=%d", len(storage_conflicts))
    extension_secrets = ExtensionSecretStore(
        repository=extensions,
        master_key=LocalMasterKey(data_root / "keys" / "extension-credentials.key"),
    )
    mcp_runtime = McpRuntimeSupervisor(
        repository=extensions, secrets=extension_secrets, extension_root=extension_root,
    )
    extension_imports = ExtensionImportService(
        repository=extensions,
        inspector=ArchiveInspector(extension_root / "quarantine"),
        filesystem=extension_files,
        mcp_runtime=mcp_runtime,
        folders=folders,
        workspace_store=WorkspaceFilesystemStore(workspace_storage),
    )

    def mcp_client(connection, context):
        configuration = connection.configuration
        endpoint = configuration.get("endpoint") or configuration.get("url")
        public_headers = configuration.get("headers", {})
        if not isinstance(endpoint, str) or not isinstance(public_headers, dict):
            raise ValueError("MCP connection configuration is invalid")
        credential_headers = extension_secrets.resolve_headers(
            user_id=context.user_id, workspace_id=context.workspace_id,
            extension_id=connection.extension_id,
        )
        capability = plugin_services.issue_for_connection(
            connection=connection, user_id=context.user_id,
            workspace_id=context.workspace_id, invocation_id=context.tool_call_id,
        )
        plugin_configuration = plugin_services.configuration_for_connection(
            connection=connection, user_id=context.user_id,
            workspace_id=context.workspace_id,
        )
        invocation_headers = (() if capability is None else (
            ("X-Vault-Service-Url", plugin_services.service_url),
            ("X-Vault-Capability", capability),
            ("X-Vault-Invocation-Id", context.tool_call_id),
        )) + (() if plugin_configuration is None else (("X-Vault-Configuration", plugin_configuration),))
        return McpClient(HttpMcpTransport(
            endpoint,
            public_headers=tuple(sorted((str(key), str(value)) for key, value in public_headers.items())),
            credential_headers=credential_headers + invocation_headers,
        ))

    mcp_lifecycle = McpLifecycle(
        repository=extensions, catalog=catalog, client_factory=mcp_client,
    )
    if direct_runs is not None:
        direct_runs.attach_tool_restore(lambda user_id, workspace_id: mcp_lifecycle.restore_scope(
            user_id=user_id, workspace_id=workspace_id, agent=AgentKind.BACKGROUND,
        ))
    Thread(
        target=mcp_runtime.restore_on_boot,
        name="resono-vault-mcp-restore",
        daemon=True,
    ).start()
    conversation_runtime = ConversationRuntime(database_url=database_url,credentials=provider_credentials,
        memories=memory_service,catalog=catalog,authority=tool_authority,
        # A coordinator that does the work itself (search, files, agents) needs room to finish it.
        turn_seconds=300 if background_coordinator is not None else 120)
    conversation_runtime.title_runner = conversation_runtime.runner
    conversation_runtime.link_chat_responder = config.link_chat_responder
    conversation_runtime.store.recover_orphans()
    conversation_runtime.genui_enabled = config.genui_enabled
    conversation_runtime.background_coordinator = background_coordinator
    conversation_runtime.background_actions = background_actions
    if background_coordinator is not None:
        from app.vault_runtime.local_identity.repository import LocalSessionError

        def wake_conversation(user_id, workspace_id, conversation_id):
            """Coordinator wake (2026-11-18): run as the owner session last active in that chat."""
            with psycopg.connect(database_url) as connection:
                row = connection.execute(
                    """SELECT activity_session_id FROM vault_private.vault_conversations
                       WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s""",
                    (user_id, workspace_id, conversation_id)).fetchone()
            if row is None or not row[0]:
                return "unavailable"
            try:
                principal = identity_repository.resolve_review_principal(user_id, workspace_id, row[0])
            except LocalSessionError:
                return "unavailable"  # Signed out: the result stays in the chat for the next visit.
            return conversation_runtime.wake(principal, conversation_id)["state"]

        background_coordinator.jobs.attach_wake(wake_conversation)
        # Voice hands work to the coordinator (Coordinator intake) on every Voice path.
        from app.vault_runtime.voice.coordinator_tools import register_coordinator_voice_tools
        conversation_runtime.voice_hand_offs = {}
        conversation_runtime.voice_hand_off_times = {}

        def record_hand_off(voice_session_id, conversation_id):
            from time import time
            conversation_runtime.voice_hand_offs[voice_session_id] = conversation_id
            conversation_runtime.voice_hand_off_times.setdefault(voice_session_id, time())

        register_coordinator_voice_tools(
            catalog=catalog, database_url=database_url, runtime=conversation_runtime,
            resolve_principal=identity_repository.resolve_review_principal, voice_modes=voice_modes,
            on_hand_off=record_hand_off,
        )
        background_coordinator.jobs.attach_checkins(background_coordinator.daily_checkins)
    if config.owner_approvals_enabled:
        # One approval system for Chat and Voice: the stop lives in the shared catalog, so every
        # agent path gets it; the Link run status reads the same records.
        from app.vault_runtime.background_agent.owner_approvals import OwnerApprovals
        from app.vault_runtime.conversation_tools.approval_gate import ApprovalGate, ApprovalText
        owner_approvals = OwnerApprovals(database_url=database_url, actions=background_actions)
        owner_approvals.expire_all_waiting()     # questions of the previous process are deny
        catalog.set_approval_gate(ApprovalGate(approvals=owner_approvals,
                                               text=ApprovalText(database_url=database_url, records=personal_data),
                                               tool_authority=tool_authority))
        conversation_runtime.approvals = owner_approvals
    if config.genui_enabled:
        from app.vault_runtime.genui.feedback import GenuiFeedbackStore
        conversation_runtime.genui_feedback = GenuiFeedbackStore(database_url=database_url,
            embedder_factory=memory_service._embedder_factory)
    if config.genui_enabled and config.genui_presentation_hints:
        from app.vault_runtime.decision_routing.openai_transport import OpenAIDecisionTransport
        # The hint uses the OpenAI Decisions API: skip it entirely without an OpenAI API key.
        conversation_runtime.presentation_transport_factory = lambda principal: OpenAIDecisionTransport(
            credential_resolver=provider_credentials, principal=principal,
        ) if provider_credentials.has_api_key(principal, "openai") else None
    from app.vault_runtime.conversation.attachments import ConversationAttachments
    conversation_runtime.attachments=ConversationAttachments(database_url=database_url,storage=workspace_storage)
    from app.vault_runtime.memory.chat_learning import ChatMemoryLearning
    conversation_runtime.memory_learning = ChatMemoryLearning(database_url=database_url,
        memories=memories,voice_learning=voice_learning,runtime_store=conversation_runtime.store,
        attachments=conversation_runtime.attachments)
    if config.decision_review_enabled:
        from app.vault_runtime.decision_learning.chat_source import ChatReviewSource
        from app.vault_runtime.decision_learning.rules import DecisionRuleRepository
        from app.vault_runtime.decision_learning.chat_learning import ChatLearningPublisher
        conversation_runtime.decision_review = VoiceDecisionReview(database_url=database_url,
            catalog=catalog,credentials=provider_credentials,
            source=ChatReviewSource(database_url=database_url,catalog=catalog,memories=memories,attachments=conversation_runtime.attachments),
            repository_type=DecisionRuleRepository)
        from app.vault_runtime.decision_learning.chat_activation import ChatActivationGates
        from app.vault_runtime.decision_learning.activation import CatalogActivator
        gates = ChatActivationGates(source=conversation_runtime.decision_review.source,
            catalog=catalog,authority=tool_authority)
        activator = CatalogActivator(repository=conversation_runtime.decision_review.repository,
            qualify_rule=gates.qualify,current_capabilities=gates.capabilities)
        conversation_runtime.decision_review.on_completed = ChatLearningPublisher(database_url=database_url,
            repository=conversation_runtime.decision_review.repository,
            embedder_factory=memory_service._embedder_factory or (lambda user_id,workspace_id:None),
            activator=activator)
    from app.vault_runtime.live_memory.chat_runtime import ChatPreparationRuntime
    conversation_runtime.preparation = ChatPreparationRuntime(database_url=database_url,
        store=conversation_runtime.store,memories=memory_service,preferences=live_memory_preferences,
        credentials=provider_credentials,catalog=catalog,authority=tool_authority,
        user_ids=tuple({user_id for user_id,_ in storage_identities}), search=indexed_memory_search)
    conversation_runtime.preparation.maintenance = memory_maintenance
    from app.vault_runtime.live_memory.tool_routing import ToolRoutingPreferences
    tool_routing = ToolRoutingPreferences(database_url=database_url, credentials=provider_credentials)
    conversation_runtime.preparation.tool_routing = tool_routing
    from app.vault_runtime.live_memory.voice_host import PreparationSources
    conversation_runtime.preparation.store=PreparationSources(conversation_runtime.store,voices)
    conversation_runtime.preparation.loader.context_identity=conversation_runtime.preparation.store.context_identity
    coordinator.live_preparation=lambda principal:live_memory_preferences.get(principal).enabled
    coordinator.transcription_available=lambda principal:provider_credentials.has_api_key(principal,"openai")
    if config.decision_review_enabled:
        from app.vault_runtime.decision_routing.example_index import ActiveDecisionQueries
        from app.vault_runtime.memory_search.postgres import QueryOptions
        conversation_runtime.preparation.learned_queries = ActiveDecisionQueries(activator=activator,
            options=QueryOptions(timeout_ms=1500,ef_search=100,max_scan_tuples=20000))
        from app.vault_runtime.decision_learning.reconciliation import DecisionReconciler
        conversation_runtime.decision_review.reconciler = DecisionReconciler(
            repository=conversation_runtime.decision_review.repository,
            queries=conversation_runtime.preparation.learned_queries,
            embedder_factory=lambda user_id,workspace_id: memory_service._embedder_factory(user_id,workspace_id)
                if memory_service._embedder_factory else None)
        conversation_runtime.decision_review.on_completed.require_reconciliation = True
        # Both channels use the same publisher, reconciliation and activation.
        # Voice supplies its existing canonical session logs, never another capture path.
        conversation_runtime.decision_review.source.voice_source = decision_review.source
        decision_review.source.existing_source = conversation_runtime.decision_review.source
        decision_review.on_completed = conversation_runtime.decision_review.on_completed
        decision_review.reconciler = DecisionReconciler(
            repository=decision_review.repository,
            queries=conversation_runtime.preparation.learned_queries,
            embedder_factory=lambda user_id,workspace_id: memory_service._embedder_factory(user_id,workspace_id)
                if memory_service._embedder_factory else None)

    conversation_runtime.voice_learning=voice_learning
    conversation_runtime.voice_decision_review=decision_review
    conversation_runtime.start_review_recovery(identity_repository.resolve_review_principal)
    return VaultLocalApiApp(
        store=PostgresVaultHealthStore.from_config(config), token=config.token,
        max_body_bytes=config.max_body_bytes, identity_service=identities,
        live_memory_preferences=live_memory_preferences,
        tool_routing=tool_routing,
        live_memory_invalidator=conversation_runtime.preparation.registry.preference_changed,
        voice_coordinator=coordinator, voice_sessions=voices,
        provider_credential_resolver=provider_credentials.resolve,
        extension_imports=extension_imports, extensions=extensions,
        extension_secrets=extension_secrets, mcp_lifecycle=mcp_lifecycle,
        voice_provider_credentials=provider_credentials,
        provider_oauth=provider_oauth,
        email_runtime=email_runtime,
        personal_data=personal_data,
        calendar_runtime=calendar_runtime,
        background_runs=background_runs, direct_runs=direct_runs,
        voice_learning=voice_learning,
        decision_review=decision_review,
        conversation_runtime=conversation_runtime,
        voice_tools=voice_tools,
        external_memory_integrations=external_integrations,
        external_memory=external_memory,
        folders=folders,
        commands=commands,
        link_companion=link_companion, link_tools=link_tools,
        a2a_service=a2a_service,
        help_assistant=help_assistant,
        builtin_plugins=builtin_plugins,
        plugin_services=plugin_services,
        workspace_files=workspace_files,
        tasks=tasks,
        notifications=notifications,
    )
