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
from app.vault_runtime.agent_network.client import A2AClient
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
from app.vault_runtime.memory.openai_embeddings import ScopedOpenAIEmbeddingFactory
from app.vault_runtime.memory.service import MemoryService
from app.vault_runtime.memory.tools import register_memory_tools
from app.vault_runtime.memory.voice_learning import VoiceMemoryLearning
from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
from app.vault_runtime.memory.pipeline import MemoryPipeline
from app.vault_runtime.external_memory.repository import ExternalMemoryRepository
from app.vault_runtime.external_memory.service import ExternalMemoryService
from app.vault_runtime.host_filesystem.repository import HostFilesystemRepository
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
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from app.vault_runtime.workspace_storage import WorkspaceStorage
from app.vault_runtime.workspace_files.repository import WorkspaceFileRepository
from app.vault_runtime.workspace_files.service import WorkspaceFileService
from app.vault_runtime.workspace_files.tools import register_workspace_file_tools
from app.vault_runtime.tasks.repository import TaskRepository
from app.vault_runtime.tasks_tools import register_tasks_tools
from app.vault_runtime.notifications.repository import NotificationRepository


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
    embedding_factory = ScopedOpenAIEmbeddingFactory(provider_credentials)
    memory_service = MemoryService(
        repository=memories, embedder_factory=embedding_factory,
    )
    register_memory_tools(catalog=catalog, repository=memories, service=memory_service)
    register_contacts_tools(catalog=catalog, store=personal_data)
    register_web_search_tool(catalog=catalog, credentials=provider_credentials)
    register_builtin_plugin_tools(catalog=catalog, repository=builtin_plugins, credentials=provider_credentials)
    voice_learning = VoiceMemoryLearning(
        memories=memories, sessions=voices, credentials=provider_credentials,
        embedder_factory=embedding_factory,
    )
    external_integrations = ExternalMemoryRepository(database_url=database_url)
    external_integrations.ensure_schema()
    host_filesystem_repository = HostFilesystemRepository(database_url=database_url)
    host_filesystem_repository.ensure_schema()
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
    register_a2a_tools(catalog, a2a_service)
    a2a_service.start()

    def backfill_memory_vectors() -> None:
        for user_id, workspace_id in storage_identities:
            stored, failed = memory_service.ensure_vectors(
                user_id=user_id, workspace_id=workspace_id, limit=1000,
            )
            if stored or failed:
                logging.getLogger(__name__).info(
                    "Vault memory vector backfill completed stored=%s failed=%s",
                    stored, failed,
                )

    Thread(
        target=backfill_memory_vectors,
        name="vault-memory-vector-backfill",
        daemon=True,
    ).start()
    background_runs = BackgroundRunRepository(database_url=database_url)
    background_runs.ensure_schema()
    background_service = BackgroundAgentService(
        repository=background_runs, catalog=catalog,
        executor=OpenAIBackgroundExecutor(
            credentials=provider_credentials, memories=memory_service,
        ),
    )
    background_service.start()
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
    coordinator = VoiceSessionCoordinator(
        sessions=voices,
        contexts=VoiceContextBuilder(memories=memories, skills=skill_activation, builtin_plugins=builtin_plugins), tools=catalog,
        providers=ProviderRegistry((OpenAIRealtimeProvider(), GeminiLiveProvider(), XAIRealtimeProvider())),
        tool_authority=tool_authority,
    )
    voice_tools = VoiceToolRuntime(catalog=catalog, authority=tool_authority)
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
    Thread(
        target=mcp_runtime.restore_on_boot,
        name="resono-vault-mcp-restore",
        daemon=True,
    ).start()
    notifications = NotificationRepository(database_url=database_url)
    notifications.ensure_schema()
    return VaultLocalApiApp(
        store=PostgresVaultHealthStore.from_config(config), token=config.token,
        max_body_bytes=config.max_body_bytes, identity_service=identities,
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
        voice_tools=voice_tools,
        external_memory_integrations=external_integrations,
        external_memory=external_memory,
        host_filesystem_integrations=host_filesystem_repository,
        host_filesystem=host_filesystem,
        a2a_service=a2a_service,
        help_assistant=help_assistant,
        builtin_plugins=builtin_plugins,
        plugin_services=plugin_services,
        workspace_files=workspace_files,
        tasks=tasks,
        notifications=notifications,
    )
