"""Standalone composition root for the admitted local Vault runtime modules."""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Thread

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
from app.vault_runtime.email_runtime import LocalEmailRuntime
from app.vault_runtime.email_schema import ensure_email_schema
from app.vault_runtime.email_tools import register_email_tools
from app.vault_runtime.background_agent.openai_executor import OpenAIBackgroundExecutor
from app.vault_runtime.background_agent.repository import BackgroundRunRepository
from app.vault_runtime.background_agent.service import BackgroundAgentService
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
from app.vault_runtime.calendar_runtime import LocalCalendarRuntime
from app.vault_runtime.calendar_tools import register_calendar_tools
from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from app.vault_runtime.local_api.stores import PostgresVaultHealthStore
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.memory.repository import MemoryRepository
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
from app.vault_runtime.host_filesystem.repository import HostFilesystemRepository
from app.vault_runtime.link_companion.repository import LinkCompanionRepository
from app.vault_runtime.host_filesystem.service import HostFilesystemService
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
from app.vault_runtime.voice.goal_tools import register_goal_tools
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
    identity_repository = LocalIdentityRepository(database_url=database_url)
    identity_repository.ensure_schema()
    live_memory_preferences = LiveMemoryPreferenceRepository(database_url=database_url)
    live_memory_preferences.ensure_schema()
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
    memories.ensure_schema()
    voices = VoiceSessionRepository(database_url=database_url)
    voices.ensure_schema()
    import psycopg
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            ensure_email_schema(cursor)
    extensions = ExtensionRepository(database_url=database_url)
    extensions.ensure_schema()
    personal_data = PersonalDataRepository(database_url=database_url)
    personal_data.ensure_schema()
    builtin_plugins = BuiltinPluginRepository(database_url=database_url)
    builtin_plugins.ensure_schema()

    tool_authority = LocalToolAuthority(database_url=database_url)
    catalog = ToolCatalog(authorizer=tool_authority.authorize)
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
    register_memory_tools(catalog=catalog, repository=memories, service=memory_service)
    register_contacts_tools(catalog=catalog, store=personal_data)
    register_web_search_tool(catalog=catalog, credentials=provider_credentials)
    register_builtin_plugin_tools(catalog=catalog, repository=builtin_plugins, credentials=provider_credentials)
    decision_review = None
    if config.decision_review_enabled:
        from app.vault_runtime.decision_learning.rules import DecisionRuleRepository
        decision_review = VoiceDecisionReview(database_url=database_url,catalog=catalog,credentials=provider_credentials,
            repository_type=DecisionRuleRepository)
        decision_review.ensure_schema()
    voice_learning = VoiceMemoryLearning(
        memories=memories, sessions=voices, credentials=provider_credentials,
        embedder_factory=embedding_factory,
        decision_finalize=decision_review.finalize if decision_review is not None else None,
    )
    external_integrations = ExternalMemoryRepository(database_url=database_url)
    external_integrations.ensure_schema()
    host_filesystem_repository = HostFilesystemRepository(database_url=database_url)
    host_filesystem_repository.ensure_schema()
    link_companion = LinkCompanionRepository(database_url=database_url)
    link_companion.ensure_schema()
    host_filesystem = HostFilesystemService(
        repository=host_filesystem_repository,
        credential_key=LocalMasterKey(data_root / "keys" / "host-filesystem.key"),
    )

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
    a2a_repository.ensure_schema()
    a2a_service = A2AService(repository=a2a_repository, client=A2AClient())
    register_a2a_tools(catalog, a2a_service, builtin_plugins=builtin_plugins)
    register_collab_tools(catalog, a2a_service, builtin_plugins=builtin_plugins)
    a2a_service.start()

    from app.vault_runtime.memory_search.maintenance import IndexedMemoryMaintenance
    memory_maintenance = IndexedMemoryMaintenance(database_url=database_url, service=memory_service,
        identities=identity_repository, enabled=config.indexed_memory_enabled)
    memory_maintenance.start()
    background_runs = BackgroundRunRepository(database_url=database_url)
    background_runs.ensure_schema()
    background_service = BackgroundAgentService(
        repository=background_runs, catalog=catalog,
        executor=OpenAIBackgroundExecutor(
            credentials=provider_credentials, memories=memory_service,
        ),
    )
    background_service.start()
    inbound_app = A2AInboundApp(
        repository=a2a_repository, builtin_plugins=builtin_plugins,
        background=background_service, runs=background_runs,
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
    email_runtime = LocalEmailRuntime(
        database_url=database_url,
        master_key=LocalMasterKey(data_root / "keys" / "mail-credentials.key"),
    )
    register_email_tools(catalog=catalog, runtime=email_runtime, builtin_plugins=builtin_plugins)
    calendar_runtime = LocalCalendarRuntime(
        database_url=database_url,
        master_key=LocalMasterKey(data_root / "keys" / "calendar-credentials.key"),
        records=personal_data,
    )
    calendar_runtime.ensure_schema()
    register_calendar_tools(catalog=catalog, runtime=calendar_runtime, records=personal_data)
    tasks = TaskRepository(database_url=database_url)
    tasks.ensure_schema()
    register_tasks_tools(catalog=catalog, repository=tasks, builtin_plugins=builtin_plugins)
    workspace_file_repository = WorkspaceFileRepository(database_url=database_url)
    migrated_workspace_files = workspace_file_repository.ensure_schema(storage=workspace_storage)
    if migrated_workspace_files:
        logging.getLogger(__name__).info(
            "Migrated %s legacy workspace file projection(s) to disk.",
            migrated_workspace_files,
        )
    workspace_files = WorkspaceFileService(
        workspace_file_repository,
        workspace_storage,
        host_filesystem=host_filesystem,
    )
    register_workspace_file_tools(catalog=catalog, service=workspace_files)
    extension_root = data_root / "extensions"
    skill_activation = SkillActivation(repository=extensions, extension_root=extension_root)
    catalog.register(skill_activation.tool_definition())
    voice_modes = VoiceModeService()
    register_voice_mode_tool(catalog, voice_modes)
    register_goal_tools(catalog, background_service, voice_modes)
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
        host_filesystem_repository=host_filesystem_repository,
        host_filesystem=host_filesystem,
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
    background_service.attach_tool_restore(lambda user_id, workspace_id: mcp_lifecycle.restore_scope(
        user_id=user_id, workspace_id=workspace_id, agent=AgentKind.BACKGROUND,
    ))
    Thread(
        target=mcp_runtime.restore_on_boot,
        name="resono-vault-mcp-restore",
        daemon=True,
    ).start()
    notifications = NotificationRepository(database_url=database_url)
    notifications.ensure_schema()
    conversation_runtime = ConversationRuntime(database_url=database_url,credentials=provider_credentials,
        memories=memory_service,catalog=catalog,authority=tool_authority)
    conversation_runtime.ensure_schema()
    conversation_runtime.genui_enabled = config.genui_enabled
    if config.genui_enabled and config.genui_presentation_hints:
        from app.vault_runtime.decision_routing.openai_transport import OpenAIDecisionTransport
        conversation_runtime.presentation_transport_factory = lambda principal: OpenAIDecisionTransport(
            credential_resolver=provider_credentials, principal=principal)
    from app.vault_runtime.conversation.attachments import ConversationAttachments
    conversation_runtime.attachments=ConversationAttachments(database_url=database_url,storage=workspace_storage)
    conversation_runtime.attachments.ensure_schema()
    from app.vault_runtime.memory.chat_learning import ChatMemoryLearning
    conversation_runtime.memory_learning = ChatMemoryLearning(database_url=database_url,
        memories=memories,voice_learning=voice_learning,runtime_store=conversation_runtime.store,
        attachments=conversation_runtime.attachments)
    conversation_runtime.memory_learning.ensure_schema()
    if config.decision_review_enabled:
        from app.vault_runtime.decision_learning.chat_source import ChatReviewSource
        from app.vault_runtime.decision_learning.rules import DecisionRuleRepository
        from app.vault_runtime.decision_learning.chat_learning import ChatLearningPublisher
        conversation_runtime.decision_review = VoiceDecisionReview(database_url=database_url,
            catalog=catalog,credentials=provider_credentials,
            source=ChatReviewSource(database_url=database_url,catalog=catalog,memories=memories,attachments=conversation_runtime.attachments),
            repository_type=DecisionRuleRepository)
        conversation_runtime.decision_review.ensure_schema()
        from app.vault_runtime.decision_learning.chat_activation import ChatActivationGates
        from app.vault_runtime.decision_learning.activation import CatalogActivator
        gates = ChatActivationGates(source=conversation_runtime.decision_review.source,
            catalog=catalog,authority=tool_authority)
        activator = CatalogActivator(repository=conversation_runtime.decision_review.repository,
            qualify_rule=gates.qualify,current_capabilities=gates.capabilities)
        activator.ensure_schema()
        conversation_runtime.decision_review.on_completed = ChatLearningPublisher(database_url=database_url,
            repository=conversation_runtime.decision_review.repository,
            embedder_factory=memory_service._embedder_factory or (lambda user_id,workspace_id:None),
            activator=activator)
    from app.vault_runtime.live_memory.chat_runtime import ChatPreparationRuntime
    conversation_runtime.preparation = ChatPreparationRuntime(database_url=database_url,
        store=conversation_runtime.store,memories=memory_service,preferences=live_memory_preferences,
        credentials=provider_credentials,catalog=catalog,authority=tool_authority,
        user_ids=tuple({user_id for user_id,_ in storage_identities}))
    conversation_runtime.preparation.maintenance = memory_maintenance
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
        background_service=background_service, background_runs=background_runs,
        voice_learning=voice_learning,
        decision_review=decision_review,
        conversation_runtime=conversation_runtime,
        voice_tools=voice_tools,
        external_memory_integrations=external_integrations,
        external_memory=external_memory,
        host_filesystem_integrations=host_filesystem_repository,
        host_filesystem=host_filesystem,
        link_companion=link_companion,
        a2a_service=a2a_service,
        help_assistant=help_assistant,
        builtin_plugins=builtin_plugins,
        plugin_services=plugin_services,
        workspace_files=workspace_files,
        tasks=tasks,
        notifications=notifications,
    )
