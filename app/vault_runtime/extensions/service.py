"""Owner-controlled Plugin/Skill lifecycle assembled from the frozen Voice/R1 donors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Thread

from app.vault_runtime.extensions.archives import ArchiveInspector, MAX_MCP_PACKAGE_UPLOAD_BYTES, QuarantinedArchive
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem, managed_mcp_identity
from app.vault_runtime.extensions.models import ExtensionAudience, ExtensionKind, ExtensionState
from app.vault_runtime.extensions.import_diagnostics import blocking_import_diagnostics
from app.vault_runtime.extensions.package_review import PackageReview, review_plugin_package
from app.vault_runtime.extensions.preflight import Preflight, PreflightRegistry
from app.vault_runtime.extensions.repository import (
    ExtensionConflictError, ExtensionNotFoundError, ExtensionRecord, ExtensionRepository,
)
from app.vault_runtime.extensions.skills import SkillDocument, SkillSpecificationError, parse_skill
from app.vault_runtime.extensions.specification import (
    McpServer, PluginManifest, PluginSpecificationError, parse_mcp_bytes,
    parse_mcp_document_partial, parse_plugin_manifest,
)
from app.vault_runtime.extensions.mcp_package_manifest import (
    McpPackageManifest, McpPackageManifestError, parse_mcp_package_manifest,
)
from app.vault_runtime.extensions.mcp_package_migration import (
    McpPackageMigrationError,
    MigrationAssessment,
    MigrationImportResult,
    assess_migration,
    discard_set_aside,
    import_migration_payload,
    restore_set_aside,
    validate_migration_payload,
)
from app.vault_runtime.extensions.plugin_package_contract import LocalShareManifest
from app.vault_runtime.extensions.plugin_workspace_import import (
    WorkspaceImportAssessment,
    assess_workspace_import,
    import_workspace_payload,
    revert_workspace_import,
    validate_workspace_import_payload,
)
from app.vault_runtime.extensions.mcp_runtime import (
    McpRuntimeError,
    McpRuntimeSupervisor,
    supervised_runtime_configuration,
)
from app.vault_runtime.extensions.vault_manifest import VaultPluginManifest, parse_vault_manifest
from app.vault_runtime.folders.service import FolderService
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LocalShareRegistration:
    """The user's folder chosen for a plugin's localShare during import."""

    folder_id: str
    created_during_import: bool = False


@dataclass(frozen=True, slots=True)
class SkillCandidate:
    archive: QuarantinedArchive
    document: SkillDocument


@dataclass(frozen=True, slots=True)
class PluginCandidate:
    archive: QuarantinedArchive
    manifest: PluginManifest
    skills: tuple[tuple[str, SkillDocument, str], ...]
    mcp_servers: tuple[McpServer, ...]
    diagnostics: tuple[str, ...] = ()
    review: PackageReview | None = None
    vault_manifest: VaultPluginManifest | None = None
    configuration_schema: dict[str, object] | None = None
    migration_assessment: MigrationAssessment | None = None
    workspace_import_assessment: WorkspaceImportAssessment | None = None


@dataclass(frozen=True, slots=True)
class McpCandidate:
    server: McpServer
    content_hash: str


@dataclass(frozen=True, slots=True)
class McpPackageCandidate:
    archive: QuarantinedArchive
    manifest: McpPackageManifest
    configuration_schema: dict[str, object] | None
    companion_plugin: PluginManifest | None
    companion_vault_manifest: VaultPluginManifest | None
    companion_configuration_schema: dict[str, object] | None
    companion_skills: tuple[tuple[str, SkillDocument, str], ...]
    diagnostics: tuple[str, ...] = ()
    migration_assessment: MigrationAssessment | None = None


class ExtensionImportService:
    def __init__(
        self, *, repository: ExtensionRepository, inspector: ArchiveInspector,
        filesystem: ExtensionFilesystem, mcp_runtime: McpRuntimeSupervisor | None = None,
        folders: FolderService | None = None,
        workspace_store: WorkspaceFilesystemStore | None = None,
    ) -> None:
        self._repository = repository
        self._inspector = inspector
        self._filesystem = filesystem
        self._mcp_runtime = mcp_runtime
        self._folders = folders
        self._workspace_store = workspace_store
        self._skill_preflights: PreflightRegistry[SkillCandidate] = PreflightRegistry(
            dispose=lambda candidate: candidate.archive.discard()
        )
        self._plugin_preflights: PreflightRegistry[PluginCandidate] = PreflightRegistry(
            dispose=lambda candidate: candidate.archive.discard()
        )
        self._mcp_preflights: PreflightRegistry[McpCandidate] = PreflightRegistry()
        self._mcp_package_preflights: PreflightRegistry[McpPackageCandidate] = PreflightRegistry(
            dispose=lambda candidate: candidate.archive.discard()
        )

    def preflight_skill(
        self, payload: bytes, filename: str, *, actor_user_id: str,
        workspace_id: str, audience: ExtensionAudience,
    ) -> Preflight[SkillCandidate]:
        archive = self._inspector.inspect(payload, filename, required_root_file="SKILL.md")
        try:
            document = parse_skill(archive.content_root)
            current = self._active_install(
                user_id=actor_user_id, workspace_id=workspace_id,
                kind=ExtensionKind.SKILL, identity=document.name, owner=True,
            )
            self._refuse_shared_storage(workspace_id, _skill_claims(document.name))
            return self._skill_preflights.issue(
                kind=ExtensionKind.SKILL, identity=document.name,
                principal_user_id=actor_user_id, workspace_id=workspace_id,
                candidate_hash=archive.content_hash,
                current_hash=current.content_hash if current else None,
                audience=audience, payload=SkillCandidate(archive, document),
            )
        except Exception:
            archive.discard()
            raise

    def confirm_skill(
        self, token: str, *, actor_user_id: str, workspace_id: str, replace: bool,
    ) -> ExtensionRecord:
        preview = self._repository_current_from_preflight(
            token, actor_user_id, workspace_id, self._skill_preflights, ExtensionKind.SKILL,
            replace=replace,
        )
        candidate = preview.payload
        self._refuse_shared_storage(
            workspace_id, _skill_claims(candidate.document.name), discard=candidate.archive.discard,
        )
        try:
            self._filesystem.replace(category="skills", identity=preview.identity, candidate_root=candidate.archive.content_root)
            record = self._repository.install(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                kind=ExtensionKind.SKILL, identity=candidate.document.name,
                display_name=candidate.document.name, version=candidate.document.metadata.get("version"),
                description=candidate.document.description, content_hash=candidate.archive.content_hash,
                configuration={"audience": sorted(agent.value for agent in preview.audience.agents)},
            )
            return record
        except Exception:
            self._filesystem.revert(
                category="skills", identity=preview.identity,
                had_active_install=preview.current_hash is not None,
            )
            raise
        finally:
            candidate.archive.discard()

    def preflight_plugin(
        self, payload: bytes, filename: str, *, actor_user_id: str,
        workspace_id: str, audience: ExtensionAudience,
    ) -> Preflight[PluginCandidate]:
        archive = self._inspector.inspect(payload, filename, required_root_file="plugin.json")
        try:
            manifest = parse_plugin_manifest(archive.content_root / "plugin.json")
            vault_manifest, configuration_schema = parse_vault_manifest(archive.content_root)
            diagnostics = list(manifest.diagnostics)
            review = review_plugin_package(archive.content_root)
            skills: list[tuple[str, SkillDocument, str]] = []
            skill_root = archive.content_root / "skills"
            if skill_root.exists():
                if not skill_root.is_dir():
                    diagnostics.append("skills: fixed component location is not a directory")
                else:
                    for child in sorted(skill_root.iterdir()):
                        if not child.is_dir():
                            diagnostics.append(f"skill:{child.name}: entry is not a directory")
                            continue
                        try:
                            skills.append((child.name, parse_skill(child), _directory_hash(child)))
                        except SkillSpecificationError as exc:
                            diagnostics.append(f"skill:{child.name}: {exc}")
            mcp_path = archive.content_root / "mcp.json"
            servers: tuple[McpServer, ...] = ()
            if mcp_path.exists():
                if not mcp_path.is_file():
                    diagnostics.append("mcp: fixed component location is not a file")
                else:
                    try:
                        mcp = parse_mcp_document_partial(mcp_path)
                        servers = mcp.servers
                        diagnostics.extend(mcp.diagnostics)
                    except PluginSpecificationError as exc:
                        diagnostics.append(f"mcp: {exc}")
            current = self._active_install(
                user_id=actor_user_id, workspace_id=workspace_id,
                kind=ExtensionKind.PLUGIN, identity=manifest.name, owner=True,
            )
            self._refuse_shared_storage(workspace_id, _plugin_claims(manifest.name, servers))
            migration_assessment = None
            if vault_manifest is not None and vault_manifest.migration is not None:
                try:
                    validate_migration_payload(archive.content_root, vault_manifest.migration)
                    migration_assessment = assess_migration(
                        data_dir=self._filesystem.plugin_data_dir(manifest.name),
                        migration=vault_manifest.migration,
                    )
                except McpPackageMigrationError as exc:
                    diagnostics.append(f"migration: {exc}")
            workspace_import_assessment = None
            if vault_manifest is not None and vault_manifest.workspace_import is not None:
                try:
                    validate_workspace_import_payload(
                        archive.content_root, vault_manifest.workspace_import,
                    )
                    if self._workspace_store is not None:
                        workspace_import_assessment = assess_workspace_import(
                            store=self._workspace_store,
                            workspace_id=workspace_id,
                            manifest=vault_manifest.workspace_import,
                        )
                except McpPackageMigrationError as exc:
                    diagnostics.append(f"workspaceImport: {exc}")
            candidate = PluginCandidate(
                archive, manifest, tuple(skills), tuple(servers), tuple(diagnostics), review,
                vault_manifest, configuration_schema, migration_assessment,
                workspace_import_assessment,
            )
            return self._plugin_preflights.issue(
                kind=ExtensionKind.PLUGIN, identity=manifest.name,
                principal_user_id=actor_user_id, workspace_id=workspace_id,
                candidate_hash=archive.content_hash,
                current_hash=current.content_hash if current else None,
                audience=audience, payload=candidate,
            )
        except Exception:
            archive.discard()
            raise

    def confirm_plugin(
        self, token: str, *, actor_user_id: str, workspace_id: str, replace: bool,
        replace_migration: bool = False,
        replace_workspace_import: bool = False,
        local_share: LocalShareRegistration | None = None,
    ) -> ExtensionRecord:
        preview = self._repository_current_from_preflight(
            token, actor_user_id, workspace_id, self._plugin_preflights, ExtensionKind.PLUGIN,
            replace=replace,
        )
        candidate = preview.payload
        self._refuse_shared_storage(
            workspace_id, _plugin_claims(candidate.manifest.name, candidate.mcp_servers),
            discard=candidate.archive.discard,
        )
        components = tuple(("skill", name, digest) for name, _document, digest in candidate.skills)
        components += tuple(("mcp", server.name, _value_hash(server.configuration)) for server in candidate.mcp_servers)
        migration = (
            candidate.vault_manifest.migration
            if candidate.vault_manifest is not None else None
        )
        exclude_roots = frozenset({"migration"}) if migration is not None else frozenset()
        workspace_import = (
            candidate.vault_manifest.workspace_import
            if candidate.vault_manifest is not None else None
        )
        imported_workspace: tuple[str, ...] = ()
        principal = LocalPrincipal(
            user_id=actor_user_id,
            username="import",
            display_name="Import",
            experience_style="balanced",
            is_device_owner=True,
            session_id="import",
            workspace_id=workspace_id,
            expires_at=datetime.now(UTC),
        )
        data_existed = self._filesystem.plugin_data_dir(preview.identity).exists()
        tree_replaced = False
        migration_result: MigrationImportResult | None = None
        try:
            migration_assessment = None
            if migration is not None:
                # Decide before touching any file, so a refusal changes nothing.
                migration_assessment = candidate.migration_assessment or assess_migration(
                    data_dir=self._filesystem.plugin_data_dir(candidate.manifest.name),
                    migration=migration,
                )
                if migration_assessment.requires_decision and not replace_migration:
                    raise McpPackageManifestError(
                        "Package data already exists. Confirm migration replacement to continue."
                    )
            self._filesystem.replace(
                category="plugins", identity=preview.identity,
                candidate_root=candidate.archive.content_root,
                exclude_root_names=exclude_roots,
            )
            tree_replaced = True
            migration_status: dict[str, str] | None = None
            if migration is not None and migration_assessment is not None:
                migration_result = import_migration_payload(
                    package_root=candidate.archive.content_root,
                    data_dir=self._filesystem.plugin_data_dir(candidate.manifest.name),
                    migration=migration,
                    assessment=migration_assessment,
                    replace_package=replace,
                    replace_migration=replace_migration,
                    set_aside_root=self._filesystem.data_set_aside_dir(),
                )
                migration_status = migration_result.status
            workspace_import_status: dict[str, str] | None = None
            if workspace_import is not None:
                if self._workspace_store is None:
                    raise McpPackageManifestError("Workspace import is unavailable on this Vault.")
                assessment = candidate.workspace_import_assessment or assess_workspace_import(
                    store=self._workspace_store,
                    workspace_id=workspace_id,
                    manifest=workspace_import,
                )
                if assessment.requires_decision and not replace_workspace_import:
                    raise McpPackageManifestError(
                        "Workspace paths already exist. Confirm workspace import replacement to continue."
                    )
                result = import_workspace_payload(
                    package_root=candidate.archive.content_root,
                    store=self._workspace_store,
                    workspace_id=workspace_id,
                    manifest=workspace_import,
                    assessment=assessment,
                    replace_package=replace,
                    replace_workspace_import=replace_workspace_import,
                )
                workspace_import_status = result.status
                imported_workspace = result.imported
            share_manifest = (
                candidate.vault_manifest.local_share
                if candidate.vault_manifest is not None else None
            )
            linked_local_share = self._resolve_local_share_registration(
                principal=principal,
                share_manifest=share_manifest,
                registration=local_share,
            )
            configuration: dict[str, object] = {
                "audience": sorted(agent.value for agent in preview.audience.agents),
                "vaultManifest": {
                    "minimumVaultVersion": candidate.vault_manifest.minimum_version,
                    "agents": sorted(agent.value for agent in candidate.vault_manifest.agents),
                    "services": list(candidate.vault_manifest.services),
                } if candidate.vault_manifest else None,
                "configurationSchema": candidate.configuration_schema,
                "settings": {},
            }
            if migration is not None:
                configuration["packageData"] = True
            if migration_status is not None:
                configuration["migrationStatus"] = migration_status
            if workspace_import_status is not None:
                configuration["workspaceImportStatus"] = workspace_import_status
            lifecycle = (
                candidate.vault_manifest.lifecycle
                if candidate.vault_manifest is not None else None
            )
            if lifecycle is not None and lifecycle.supervised and lifecycle.runtime is not None:
                configuration["supervised"] = True
                configuration["runtime"] = {
                    "command": list(lifecycle.runtime.command),
                    "cwd": lifecycle.runtime.cwd,
                    "port": lifecycle.runtime.port,
                    "healthPath": lifecycle.runtime.health_path,
                }
                configuration["runtimeStatus"] = {"state": "stopped"}
            if linked_local_share is not None:
                configuration["localShare"] = linked_local_share
            record = self._repository.install(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                kind=ExtensionKind.PLUGIN, identity=candidate.manifest.name,
                display_name=candidate.manifest.name, version=candidate.manifest.version,
                description=candidate.manifest.description, content_hash=candidate.archive.content_hash,
                configuration=configuration,
                components=components,
            )
            if migration_status is not None:
                record_event = getattr(self._repository, "record_event", None)
                if record_event is not None:
                    record_event(
                        actor_user_id=actor_user_id, workspace_id=workspace_id,
                        extension_id=record.extension_id, event_type="migration_imported",
                        detail={"status": migration_status},
                    )
            if workspace_import_status is not None:
                record_event = getattr(self._repository, "record_event", None)
                if record_event is not None:
                    record_event(
                        actor_user_id=actor_user_id, workspace_id=workspace_id,
                        extension_id=record.extension_id, event_type="workspace_imported",
                        detail={"status": workspace_import_status},
                    )
            reconcile = getattr(self._repository, "reconcile_managed_mcp", None)
            if reconcile is not None:
                reconcile(
                    actor_user_id=actor_user_id, workspace_id=workspace_id,
                    plugin=record,
                    servers=tuple((
                        server.name,
                        _value_hash(server.configuration),
                        {
                            "transport": server.validated.transport,
                            "url": server.validated.endpoint,
                            "headers": dict(server.validated.headers),
                            "executable": server.validated.executable,
                        },
                    ) for server in candidate.mcp_servers),
                )
            started = self._start_supervised_if_enabled(
                actor_user_id=actor_user_id, workspace_id=workspace_id, record=record,
            )
            if migration_result is not None:
                discard_set_aside(migration_result.set_aside)
            return started
        except Exception:
            if local_share is not None and local_share.created_during_import and self._folders is not None:
                try:
                    self._folders.remove_folder(principal=principal, folder_id=local_share.folder_id)
                except Exception:
                    pass
            self._restore_package_data(
                identity=preview.identity, data_existed=data_existed,
                migration_result=migration_result, created_by_import=migration is not None,
            )
            if (
                imported_workspace
                and workspace_import is not None
                and self._workspace_store is not None
            ):
                revert_workspace_import(
                    store=self._workspace_store,
                    workspace_id=workspace_id,
                    manifest=workspace_import,
                    imported=imported_workspace,
                )
            if tree_replaced:
                self._filesystem.revert(
                    category="plugins", identity=preview.identity,
                    had_active_install=preview.current_hash is not None,
                )
            raise
        finally:
            candidate.archive.discard()

    def preflight_mcp(
        self, payload: bytes, *, actor_user_id: str, workspace_id: str,
        audience: ExtensionAudience,
    ) -> tuple[Preflight[McpCandidate], ...]:
        servers = parse_mcp_bytes(payload)
        previews: list[Preflight[McpCandidate]] = []
        try:
            for server in servers:
                content_hash = _value_hash(server.configuration)
                current = self._active_install(
                    user_id=actor_user_id, workspace_id=workspace_id,
                    kind=ExtensionKind.MCP, identity=server.name, owner=True,
                )
                self._refuse_shared_storage(workspace_id, ((ExtensionKind.MCP, server.name, False),))
                previews.append(self._mcp_preflights.issue(
                    kind=ExtensionKind.MCP, identity=server.name,
                    principal_user_id=actor_user_id, workspace_id=workspace_id,
                    candidate_hash=content_hash,
                    current_hash=current.content_hash if current else None,
                    audience=audience, payload=McpCandidate(server, content_hash),
                ))
            return tuple(previews)
        except Exception:
            for preview in previews:
                self._mcp_preflights.discard(preview.token)
            raise

    def confirm_mcp(
        self, token: str, *, actor_user_id: str, workspace_id: str, replace: bool,
    ) -> ExtensionRecord:
        preview = self._repository_current_from_preflight(
            token, actor_user_id, workspace_id, self._mcp_preflights,
            ExtensionKind.MCP, replace=replace,
        )
        candidate = preview.payload
        self._refuse_shared_storage(workspace_id, ((ExtensionKind.MCP, candidate.server.name, False),))
        return self._repository.install(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            kind=ExtensionKind.MCP, identity=candidate.server.name,
            display_name=candidate.server.name, version=None,
            description="MCP connection", content_hash=candidate.content_hash,
            configuration={
                "transport": candidate.server.validated.transport,
                "endpoint": candidate.server.validated.endpoint,
                "headers": dict(candidate.server.validated.headers),
                "executable": candidate.server.validated.executable,
            },
        )

    def preflight_mcp_package(
        self, payload: bytes, filename: str, *, actor_user_id: str,
        workspace_id: str, audience: ExtensionAudience,
    ) -> Preflight[McpPackageCandidate]:
        archive = self._inspector.inspect(
            payload, filename, required_root_file="mcp.package.json",
            max_upload_bytes=MAX_MCP_PACKAGE_UPLOAD_BYTES,
        )
        try:
            manifest, configuration_schema = parse_mcp_package_manifest(archive.content_root)
            diagnostics: list[str] = []
            _validate_mcp_runtime_entry(archive.content_root, manifest, diagnostics)
            migration_assessment = None
            if manifest.migration is not None:
                try:
                    validate_migration_payload(archive.content_root, manifest.migration)
                    migration_assessment = assess_migration(
                        data_dir=self._filesystem.plugin_data_dir(manifest.name),
                        migration=manifest.migration,
                    )
                except McpPackageMigrationError as exc:
                    diagnostics.append(f"migration: {exc}")
            companion_plugin = None
            companion_vault_manifest = None
            companion_configuration_schema = None
            companion_skills: list[tuple[str, SkillDocument, str]] = []
            if manifest.companion_plugin is not None:
                plugin_root = archive.content_root / manifest.companion_plugin.directory
                try:
                    companion_plugin = parse_plugin_manifest(plugin_root / "plugin.json")
                    companion_vault_manifest, companion_configuration_schema = parse_vault_manifest(plugin_root)
                except PluginSpecificationError as exc:
                    diagnostics.append(f"companionPlugin: {exc}")
                else:
                    skill_root = plugin_root / "skills"
                    if skill_root.exists():
                        if not skill_root.is_dir():
                            diagnostics.append("companionPlugin.skills: fixed component location is not a directory")
                        else:
                            for child in sorted(skill_root.iterdir()):
                                if not child.is_dir():
                                    diagnostics.append(f"skill:{child.name}: entry is not a directory")
                                    continue
                                try:
                                    companion_skills.append((child.name, parse_skill(child), _directory_hash(child)))
                                except SkillSpecificationError as exc:
                                    diagnostics.append(f"skill:{child.name}: {exc}")
            current = self._active_install(
                user_id=actor_user_id, workspace_id=workspace_id,
                kind=ExtensionKind.MCP, identity=manifest.name, owner=True,
            )
            self._refuse_shared_storage(workspace_id, _hosted_claims(
                manifest.name, companion_plugin.name if companion_plugin is not None else None,
            ))
            candidate = McpPackageCandidate(
                archive, manifest, configuration_schema, companion_plugin,
                companion_vault_manifest, companion_configuration_schema,
                tuple(companion_skills), tuple(diagnostics), migration_assessment,
            )
            return self._mcp_package_preflights.issue(
                kind=ExtensionKind.MCP, identity=manifest.name,
                principal_user_id=actor_user_id, workspace_id=workspace_id,
                candidate_hash=archive.content_hash,
                current_hash=current.content_hash if current else None,
                audience=audience, payload=candidate,
            )
        except Exception:
            archive.discard()
            raise

    def confirm_mcp_package(
        self, token: str, *, actor_user_id: str, workspace_id: str, replace: bool,
        replace_migration: bool = False,
    ) -> ExtensionRecord:
        preview = self._repository_current_from_preflight(
            token, actor_user_id, workspace_id, self._mcp_package_preflights,
            ExtensionKind.MCP, replace=replace,
        )
        candidate = preview.payload
        self._refuse_shared_storage(workspace_id, _hosted_claims(
            candidate.manifest.name,
            candidate.companion_plugin.name if candidate.companion_plugin is not None else None,
        ), discard=candidate.archive.discard)
        blocked = blocking_import_diagnostics(candidate.diagnostics)
        if blocked:
            raise McpPackageManifestError("; ".join(blocked))
        bundle_id = _value_hash({
            "name": candidate.manifest.name,
            "version": candidate.manifest.version,
            "hash": candidate.archive.content_hash,
        })
        companion_identity = (
            candidate.companion_plugin.name if candidate.companion_plugin is not None else None
        )
        companion_was_active = companion_identity is not None and self._active_install(
            user_id=actor_user_id, workspace_id=workspace_id,
            kind=ExtensionKind.PLUGIN, identity=companion_identity, owner=True,
        ) is not None
        data_existed = self._filesystem.plugin_data_dir(preview.identity).exists()
        tree_replaced = companion_replaced = False
        migration_result: MigrationImportResult | None = None
        try:
            migration_assessment = None
            if candidate.manifest.migration is not None:
                # Decide before touching any file, so a refusal changes nothing.
                migration_assessment = candidate.migration_assessment or assess_migration(
                    data_dir=self._filesystem.plugin_data_dir(candidate.manifest.name),
                    migration=candidate.manifest.migration,
                )
                if migration_assessment.requires_decision and not replace_migration:
                    raise McpPackageManifestError(
                        "Package data already exists. Confirm migration replacement to continue."
                    )
            self._filesystem.replace(
                category="mcps", identity=preview.identity,
                candidate_root=candidate.archive.content_root,
                exclude_root_names=frozenset({"migration"}),
            )
            tree_replaced = True
            migration_status: dict[str, str] | None = None
            if candidate.manifest.migration is not None and migration_assessment is not None:
                migration_result = import_migration_payload(
                    package_root=candidate.archive.content_root,
                    data_dir=self._filesystem.plugin_data_dir(candidate.manifest.name),
                    migration=candidate.manifest.migration,
                    assessment=migration_assessment,
                    replace_package=replace,
                    replace_migration=replace_migration,
                    set_aside_root=self._filesystem.data_set_aside_dir(),
                )
                migration_status = migration_result.status
            mcp_configuration: dict[str, object] = {
                "audience": sorted(agent.value for agent in preview.audience.agents),
                "packageType": "hosted",
                "packageBundleId": bundle_id,
                "transport": "streamable-http",
                "executable": True,
                "headers": {},
                "runtime": {
                    "type": candidate.manifest.runtime.type,
                    "command": list(candidate.manifest.runtime.command),
                    "cwd": candidate.manifest.runtime.cwd,
                    "port": candidate.manifest.runtime.port,
                    "healthPath": candidate.manifest.runtime.health_path,
                    "mcpPath": candidate.manifest.runtime.mcp_path,
                },
                "configurationSchema": candidate.configuration_schema,
                "settings": {},
                "runtimeStatus": {"state": "stopped"},
            }
            if migration_status is not None:
                mcp_configuration["migrationStatus"] = migration_status
            if candidate.manifest.companion_plugin is not None:
                mcp_configuration["companionRemoveWithPackage"] = (
                    candidate.manifest.companion_plugin.remove_with_package
                )
            record = self._repository.install(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                kind=ExtensionKind.MCP, identity=candidate.manifest.name,
                display_name=candidate.manifest.name, version=candidate.manifest.version,
                description=candidate.manifest.description or "Hosted MCP package",
                content_hash=candidate.archive.content_hash,
                configuration=mcp_configuration,
            )
            record = self._repository.set_state(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                extension_id=record.extension_id, state=ExtensionState.DISABLED,
            )
            if candidate.companion_plugin is not None and candidate.manifest.companion_plugin is not None:
                plugin_root = candidate.archive.content_root / candidate.manifest.companion_plugin.directory
                plugin_identity = candidate.companion_plugin.name
                self._filesystem.replace(
                    category="plugins", identity=plugin_identity, candidate_root=plugin_root,
                )
                companion_replaced = True
                components = tuple(("skill", name, digest) for name, _document, digest in candidate.companion_skills)
                plugin_record = self._repository.install(
                    actor_user_id=actor_user_id, workspace_id=workspace_id,
                    kind=ExtensionKind.PLUGIN, identity=plugin_identity,
                    display_name=candidate.companion_plugin.name,
                    version=candidate.companion_plugin.version,
                    description=candidate.companion_plugin.description,
                    content_hash=_directory_hash(plugin_root),
                    configuration={
                        "audience": sorted(agent.value for agent in preview.audience.agents),
                        "packageBundleId": bundle_id,
                        "companionMcpId": record.extension_id,
                        "companionMcpName": record.display_name,
                        "vaultManifest": {
                            "minimumVaultVersion": candidate.companion_vault_manifest.minimum_version,
                            "agents": sorted(agent.value for agent in candidate.companion_vault_manifest.agents),
                            "services": list(candidate.companion_vault_manifest.services),
                        } if candidate.companion_vault_manifest is not None else None,
                        "configurationSchema": candidate.companion_configuration_schema,
                        "settings": {},
                    },
                    components=components,
                )
                plugin_record = self._repository.set_state(
                    actor_user_id=actor_user_id, workspace_id=workspace_id,
                    extension_id=plugin_record.extension_id, state=ExtensionState.DISABLED,
                )
                record = self._repository.update_configuration(
                    actor_user_id=actor_user_id, workspace_id=workspace_id,
                    extension_id=record.extension_id,
                    configuration={**record.configuration, "companionPluginId": plugin_record.extension_id},
                )
            if migration_status is not None:
                record_event = getattr(self._repository, "record_event", None)
                if record_event is not None:
                    record_event(
                        actor_user_id=actor_user_id, workspace_id=workspace_id,
                        extension_id=record.extension_id, event_type="migration_imported",
                        detail={"status": migration_status},
                    )
            if migration_result is not None:
                discard_set_aside(migration_result.set_aside)
            return record
        except Exception:
            self._restore_package_data(
                identity=preview.identity, data_existed=data_existed,
                migration_result=migration_result, created_by_import=True,
            )
            if tree_replaced:
                self._filesystem.revert(
                    category="mcps", identity=preview.identity,
                    had_active_install=preview.current_hash is not None,
                )
            if companion_replaced and companion_identity is not None:
                self._filesystem.revert(
                    category="plugins", identity=companion_identity,
                    had_active_install=companion_was_active,
                )
            raise
        finally:
            candidate.archive.discard()

    def _restore_package_data(
        self, *, identity: str, data_existed: bool,
        migration_result: MigrationImportResult | None, created_by_import: bool,
    ) -> None:
        """Undo a failed import's data changes; never delete data that existed before it."""
        if migration_result is not None:
            try:
                restore_set_aside(migration_result.set_aside)
            except Exception:
                # The replaced data stays in the extension recovery folder.
                _LOG.exception("extension_data_restore_failed identity=%s", identity)
                return
        if created_by_import and not data_existed:
            self._remove_unshared_data(identity, excluding_extension_id=None)

    def _refuse_shared_storage(
        self, workspace_id: str, claims: tuple[tuple[ExtensionKind, str, bool], ...],
        *, discard=None,
    ) -> None:
        """Refuse an install whose name-keyed tree or data folder another workspace uses.

        Callers reach this only after the device-owner check. The message names the
        extension but nothing about the other workspace.
        """
        used = getattr(self._repository, "storage_used_elsewhere", None)
        if used is None:
            return
        for kind, identity, uses_data in claims:
            if used(workspace_id=workspace_id, kind=kind, identity=identity, uses_data=uses_data):
                if discard is not None:
                    discard()
                raise ExtensionConflictError(
                    f"'{identity}' is already installed in another workspace on this device. "
                    "Vault keeps one copy of an extension's files per name for now, so remove it "
                    "from the other workspace before installing it here."
                )

    def _remove_unshared_tree(self, workspace_id: str, kind: ExtensionKind, identity: str) -> None:
        """Delete an install tree unless another workspace's install still owns it."""
        used = getattr(self._repository, "storage_used_elsewhere", None)
        if used is not None and used(workspace_id=workspace_id, kind=kind, identity=identity, uses_data=False):
            return
        self._filesystem.remove(category=_CATEGORY[kind], identity=identity)

    def _remove_unshared_data(self, identity: str, *, excluding_extension_id: str | None) -> None:
        """Plugin data is keyed by identity alone, so an install of any kind in any
        workspace with the same identity may still use it."""
        still_installed = getattr(self._repository, "identity_still_installed", None)
        if still_installed is not None and still_installed(
            identity=identity, excluding_extension_id=excluding_extension_id,
        ):
            return
        self._filesystem.remove_plugin_data(identity)

    def _start_supervised_if_enabled(
        self, *, actor_user_id: str, workspace_id: str, record: ExtensionRecord,
    ) -> ExtensionRecord:
        if (
            self._mcp_runtime is None
            or record.state is not ExtensionState.ENABLED
            or supervised_runtime_configuration(record) is None
        ):
            return record
        try:
            self._mcp_runtime.start(
                actor_user_id=actor_user_id, workspace_id=workspace_id, record=record,
            )
        except McpRuntimeError as exc:
            _LOG.warning("extension_runtime_start_failed extension_id=%s error=%s", record.extension_id, type(exc).__name__)
        return self._repository.by_id(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            extension_id=record.extension_id, owner=True,
        )

    def _sync_supervised_runtime(
        self,
        *,
        actor_user_id: str,
        workspace_id: str,
        record: ExtensionRecord,
        state: ExtensionState,
    ) -> None:
        if self._mcp_runtime is None or supervised_runtime_configuration(record) is None:
            return
        if state is ExtensionState.ENABLED:
            if self._mcp_runtime.safe_mode_active():
                # The state change stands; the process starts when safe mode is turned off.
                return
            refreshed = self._repository.by_id(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                extension_id=record.extension_id, owner=True,
            )
            self._mcp_runtime.start(
                actor_user_id=actor_user_id, workspace_id=workspace_id, record=refreshed,
            )
        elif state in {ExtensionState.DISABLED, ExtensionState.REMOVED}:
            self._mcp_runtime.stop(
                record=record, actor_user_id=actor_user_id, workspace_id=workspace_id,
                release_port=state is ExtensionState.REMOVED,
            )

    def enter_safe_mode(self) -> None:
        """Stop every supervised process; the durable setting already blocks new starts."""
        if self._mcp_runtime is not None:
            self._mcp_runtime.stop_all()

    def leave_safe_mode(self) -> None:
        """Start enabled supervised runtimes again, in the background like boot restore."""
        if self._mcp_runtime is not None:
            Thread(
                target=self._mcp_runtime.restore_on_boot,
                name="resono-vault-mcp-resume", daemon=True,
            ).start()

    def set_state(
        self, *, actor_user_id: str, workspace_id: str,
        extension_id: str, state: ExtensionState,
    ) -> ExtensionRecord:
        current = self._repository.by_id(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            extension_id=extension_id, owner=True,
        )
        self._sync_supervised_runtime(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            record=current, state=state,
        )
        record = self._repository.set_state(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            extension_id=extension_id, state=state,
        )
        if current.kind is ExtensionKind.MCP:
            self._sync_companion_plugin_state(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                mcp_record=record, state=state,
            )
        if current.kind is ExtensionKind.PLUGIN:
            set_managed_state = getattr(self._repository, "set_managed_state", None)
            if set_managed_state is not None:
                set_managed_state(
                    actor_user_id=actor_user_id, workspace_id=workspace_id,
                    plugin_id=current.extension_id, state=state,
                )
        if state is ExtensionState.REMOVED:
            if current.kind is ExtensionKind.MCP:
                companion_id = current.configuration.get("companionPluginId")
                remove_companion = (
                    isinstance(companion_id, str)
                    and current.configuration.get("companionRemoveWithPackage", True)
                )
                if current.configuration.get("packageType") == "hosted":
                    # Its own current and previous trees; data only when nothing else uses it.
                    self._remove_unshared_tree(workspace_id, ExtensionKind.MCP, current.identity)
                    self._remove_unshared_data(current.identity, excluding_extension_id=current.extension_id)
                else:
                    if current.configuration.get("managedByPluginId") is None:
                        self._remove_unshared_tree(workspace_id, ExtensionKind.MCP, current.identity)
                if remove_companion:
                    companion = self._repository.by_id(
                        actor_user_id=actor_user_id, workspace_id=workspace_id,
                        extension_id=companion_id, owner=True,
                    )
                    if companion.kind is ExtensionKind.PLUGIN:
                        self._repository.set_state(
                            actor_user_id=actor_user_id, workspace_id=workspace_id,
                            extension_id=companion_id, state=ExtensionState.REMOVED,
                        )
                        self._remove_unshared_tree(workspace_id, ExtensionKind.PLUGIN, companion.identity)
            elif current.kind in {ExtensionKind.SKILL, ExtensionKind.PLUGIN}:
                self._remove_unshared_tree(workspace_id, current.kind, current.identity)
                if current.kind is ExtensionKind.PLUGIN and current.configuration.get("packageData"):
                    self._remove_unshared_data(current.identity, excluding_extension_id=current.extension_id)
        return record

    def _sync_companion_plugin_state(
        self,
        *,
        actor_user_id: str,
        workspace_id: str,
        mcp_record: ExtensionRecord,
        state: ExtensionState,
    ) -> None:
        if state not in {ExtensionState.ENABLED, ExtensionState.DISABLED}:
            return
        if mcp_record.configuration.get("packageType") != "hosted":
            return
        companion_id = mcp_record.configuration.get("companionPluginId")
        if not isinstance(companion_id, str):
            return
        try:
            companion = self._repository.by_id(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                extension_id=companion_id, owner=True,
            )
        except ExtensionNotFoundError:
            return
        if companion.kind is not ExtensionKind.PLUGIN or companion.state is state:
            return
        self._repository.set_state(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            extension_id=companion_id, state=state,
        )
        set_managed_state = getattr(self._repository, "set_managed_state", None)
        if set_managed_state is not None:
            set_managed_state(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                plugin_id=companion_id, state=state,
            )

    def _resolve_local_share_registration(
        self,
        *,
        principal: LocalPrincipal,
        share_manifest: LocalShareManifest | None,
        registration: LocalShareRegistration | None,
    ) -> dict[str, str] | None:
        if share_manifest is None:
            if registration is not None:
                raise McpPackageManifestError("Package does not declare localShare")
            return None
        if share_manifest.required and registration is None:
            raise McpPackageManifestError("This package needs one of your folders. Choose a folder to continue.")
        if registration is None:
            return None
        folder = (
            self._folders.get_folder(principal=principal, folder_id=registration.folder_id)
            if self._folders is not None else None
        )
        if folder is None:
            raise McpPackageManifestError("That folder is no longer available.")
        if share_manifest.permission == "write" and folder.permission != "write":
            raise McpPackageManifestError("This package needs a folder set to 'Can view and edit'.")
        return {
            "folderId": folder.folder_id,
            "mountName": folder.name,
            "permission": folder.permission,
            "label": share_manifest.label,
            "pathPrefix": f"local/{folder.name}",
        }

    def _repository_current_from_preflight(
        self, token: str, actor_user_id: str, workspace_id: str,
        registry: PreflightRegistry, kind: ExtensionKind, *, replace: bool = False,
    ) -> Preflight:
        record = registry.peek(token)
        current = self._active_install(
            user_id=actor_user_id, workspace_id=workspace_id, kind=kind,
            identity=record.identity, owner=True,
        )
        return registry.consume(
            token, principal_user_id=actor_user_id, workspace_id=workspace_id,
            current_hash=current.content_hash if current else None, replace=replace,
        )

    def _active_install(
        self,
        *,
        user_id: str,
        workspace_id: str,
        kind: ExtensionKind,
        identity: str,
        owner: bool = False,
    ) -> ExtensionRecord | None:
        get_active = getattr(self._repository, "get_active", None)
        if get_active is not None:
            return get_active(
                user_id=user_id, workspace_id=workspace_id, kind=kind, identity=identity, owner=owner,
            )
        record = self._repository.get(
            user_id=user_id, workspace_id=workspace_id, kind=kind, identity=identity, owner=owner,
        )
        if record is None or record.state is ExtensionState.REMOVED:
            return None
        return record


_CATEGORY = {ExtensionKind.SKILL: "skills", ExtensionKind.PLUGIN: "plugins", ExtensionKind.MCP: "mcps"}


def _skill_claims(name: str) -> tuple[tuple[ExtensionKind, str, bool], ...]:
    """(kind, identity, uses data folder) for every name-keyed storage path an install takes."""
    return ((ExtensionKind.SKILL, name, False),)


def _plugin_claims(name: str, servers: tuple[McpServer, ...]) -> tuple[tuple[ExtensionKind, str, bool], ...]:
    return ((ExtensionKind.PLUGIN, name, True),) + tuple(
        (ExtensionKind.MCP, managed_mcp_identity(plugin_identity=name, server_name=server.name), False)
        for server in servers
    )


def _hosted_claims(name: str, companion: str | None) -> tuple[tuple[ExtensionKind, str, bool], ...]:
    return ((ExtensionKind.MCP, name, True),) + (
        ((ExtensionKind.PLUGIN, companion, True),) if companion is not None else ()
    )


def _directory_hash(root: Path) -> str:
    digest = sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(relative); digest.update(b"\0"); digest.update(path.read_bytes())
    return digest.hexdigest()


def _value_hash(value: object) -> str:
    import json
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_mcp_runtime_entry(
    package_root: Path, manifest: McpPackageManifest, diagnostics: list[str],
) -> None:
    runtime_root = (package_root / manifest.runtime.cwd).resolve()
    if not runtime_root.is_relative_to(package_root.resolve()):
        diagnostics.append("runtime.cwd escapes the package root")
        return
    command = manifest.runtime.command
    if not command:
        diagnostics.append("runtime.command is empty")
        return
    entry = command[-1] if command[0] in {"python", "python3"} else command[0]
    entry_path = (runtime_root / entry).resolve()
    if not entry_path.is_file():
        diagnostics.append(f"runtime.command entry is missing: {entry}")
