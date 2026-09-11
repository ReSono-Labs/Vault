from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.vault_runtime.host_filesystem.helper_client import HostFilesystemHelperClient, HostFilesystemHelperError
from app.vault_runtime.host_filesystem.models import HostFilesystemIntegration, HostFilesystemMount, HostFilesystemSettings
from app.vault_runtime.host_filesystem.repository import (
    HostFilesystemAuthorizationError,
    HostFilesystemNotFoundError,
    HostFilesystemRepository,
)
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.local_paths import LOCAL_FILES_ROOT, build_local_mount_path
from app.vault_runtime.workspace_paths import normalize_workspace_file_prefix


_MOUNT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True)
class HostMountAccess:
    mount: HostFilesystemMount
    mount_path: str
    relative_path: str = ""

    @property
    def can_read(self) -> bool:
        return self.mount.permission in {"read", "write"}

    @property
    def can_write(self) -> bool:
        return self.mount.permission == "write"


class HostFilesystemService:
    def __init__(
        self,
        *,
        repository: HostFilesystemRepository,
        credential_key,
    ) -> None:
        self._repository = repository
        self._credential_key = credential_key

    def start_pairing(
        self,
        *,
        display_name: str,
        adapter_kind: str,
        poll_token: str,
        runtime_token_hash: str,
        outbound_credential: str | None = None,
    ) -> dict[str, str]:
        encrypted = self._encrypt_credential(outbound_credential.strip()) if outbound_credential else None
        return self._repository.start_pairing(
            display_name=display_name,
            adapter_kind=adapter_kind,
            poll_token=poll_token,
            runtime_token_hash=runtime_token_hash,
            outbound_credential_enc=encrypted,
        )

    def pairing_status(self, *, pairing_id: str, poll_token: str) -> str:
        return self._repository.pairing_status(pairing_id=pairing_id, poll_token=poll_token)

    def pairing_by_code(self, *, pairing_code: str) -> dict[str, object]:
        return self._repository.pairing_by_code(pairing_code=pairing_code)

    def approve_pairing(self, *, principal: LocalPrincipal, pairing_id: str) -> dict[str, object]:
        integration = self._repository.approve_pairing(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            pairing_id=pairing_id,
        )
        return self._integration_payload(integration)

    def revoke_integration(self, *, principal: LocalPrincipal, integration_id: str) -> None:
        self._repository.revoke_integration(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            integration_id=integration_id,
        )

    def remove_integration(self, *, principal: LocalPrincipal, integration_id: str) -> None:
        self._repository.remove_revoked_integration(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            integration_id=integration_id,
        )

    def settings(self, *, principal: LocalPrincipal) -> HostFilesystemSettings:
        return self._repository.get_settings(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
        )

    def save_settings(
        self,
        *,
        principal: LocalPrincipal,
        enabled: bool,
        helper_base_url: str | None = None,
    ) -> HostFilesystemSettings:
        if enabled:
            self._repository.ensure_browser_integration(
                user_id=principal.user_id,
                workspace_id=principal.workspace_id,
            )
        return self._repository.save_settings(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            enabled=enabled,
            helper_base_url=helper_base_url,
        )

    def list_integrations(self, *, principal: LocalPrincipal) -> list[dict[str, object]]:
        return [self._integration_payload(item) for item in self._repository.list_integrations(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
        )]

    def list_mounts(self, *, principal: LocalPrincipal) -> list[dict[str, object]]:
        return [self._mount_payload(item) for item in self._repository.list_mounts(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
        )]

    def register_mount(
        self,
        *,
        principal: LocalPrincipal,
        mount_id: str,
        mount_name: str,
        permission: str,
        host_path: str = "",
        source: str = "browser",
    ) -> dict[str, object]:
        mount, _prior = self._register_mount(
            principal=principal,
            mount_id=mount_id,
            mount_name=mount_name,
            permission=permission,
            host_path=host_path,
            source=source,
        )
        return self._mount_payload(mount)

    def register_mount_for_import(
        self,
        *,
        principal: LocalPrincipal,
        mount_id: str,
        mount_name: str,
        permission: str,
        host_path: str = "",
        source: str = "browser",
    ) -> tuple[dict[str, object], HostFilesystemMount | None]:
        mount, prior = self._register_mount(
            principal=principal,
            mount_id=mount_id,
            mount_name=mount_name,
            permission=permission,
            host_path=host_path,
            source=source,
        )
        return self._mount_payload(mount), prior

    def restore_mount(self, *, principal: LocalPrincipal, prior: HostFilesystemMount) -> None:
        integration = self._repository.ensure_browser_integration(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
        )
        self._repository.upsert_mount(
            integration_id=integration.integration_id,
            user_id=prior.user_id,
            workspace_id=prior.workspace_id,
            mount_id=prior.mount_id,
            mount_name=prior.mount_name,
            permission=prior.permission,
            source=prior.source,
            status=prior.status,
            revoked_at=prior.revoked_at,
        )

    def _register_mount(
        self,
        *,
        principal: LocalPrincipal,
        mount_id: str,
        mount_name: str,
        permission: str,
        host_path: str = "",
        source: str = "browser",
    ) -> tuple[HostFilesystemMount, HostFilesystemMount | None]:
        self._require_enabled(principal)
        normalized_name = self._normalize_mount_name(mount_name)
        if permission not in {"read", "write"}:
            raise ValueError("permission must be read or write.")
        if source not in {"browser", "helper"}:
            raise ValueError("source must be browser or helper.")
        integration = self._repository.ensure_browser_integration(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
        )
        existing_by_id = self._repository.get_mount(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            mount_id=mount_id,
        )
        if existing_by_id is not None:
            if existing_by_id.mount_name != normalized_name:
                raise ValueError("That folder link id is already registered under a different name.")
            if (
                existing_by_id.permission == permission
                and existing_by_id.source == source
            ):
                return existing_by_id, None
            mount = self._repository.update_mount_permission(
                user_id=principal.user_id,
                workspace_id=principal.workspace_id,
                mount_id=mount_id,
                permission=permission,
            )
            return mount, existing_by_id
        if source == "helper":
            if not host_path:
                raise ValueError("hostPath is required for helper-linked folders.")
            client = self._client_for(principal)
            client.register_mount(
                mount_id=mount_id,
                host_path=host_path,
                mount_name=normalized_name,
                permission=permission,
            )
        return self._repository.upsert_mount(
            integration_id=integration.integration_id,
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            mount_id=mount_id,
            mount_name=normalized_name,
            permission=permission,
            source=source,
        )

    def revoke_mount(self, *, principal: LocalPrincipal, mount_id: str) -> None:
        mount = self._repository.revoke_mount(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            mount_id=mount_id,
        )
        if mount.source == "helper":
            try:
                self._client_for(principal).revoke_mount(mount_id=mount.mount_id)
            except HostFilesystemHelperError:
                pass

    def is_enabled_for(self, *, principal: LocalPrincipal) -> bool:
        return self.settings(principal=principal).enabled

    def resolve_mount_access(
        self,
        *,
        principal: LocalPrincipal,
        view_path: str,
    ) -> HostMountAccess | None:
        if not self.is_enabled_for(principal=principal):
            return None
        normalized = normalize_workspace_file_prefix(view_path)
        if normalized == LOCAL_FILES_ROOT:
            return None
        if not normalized.startswith(f"{LOCAL_FILES_ROOT}/"):
            return None
        relative = normalized.removeprefix(f"{LOCAL_FILES_ROOT}/")
        mount_name, _, remainder = relative.partition("/")
        mount = self._repository.get_mount_by_name(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            mount_name=mount_name,
        )
        if mount is None:
            raise HostFilesystemNotFoundError("That linked folder is unavailable.")
        return HostMountAccess(
            mount=mount,
            mount_path=build_local_mount_path(mount_name=mount.mount_name),
            relative_path=remainder,
        )

    def list_mount_names(self, *, principal: LocalPrincipal) -> list[str]:
        if not self.is_enabled_for(principal=principal):
            return []
        return [mount.mount_name for mount in self._repository.list_mounts(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
        )]

    def helper_list_directory(self, *, access: HostMountAccess, principal: LocalPrincipal) -> dict[str, object]:
        client = self._client_for(principal)
        return client.list_directory(mount_id=access.mount.mount_id, directory=access.relative_path)

    def helper_read_file(self, *, access: HostMountAccess, principal: LocalPrincipal, file_key: str) -> dict[str, object]:
        client = self._client_for(principal)
        return client.read_file(mount_id=access.mount.mount_id, file_key=file_key)

    def helper_write_file(
        self,
        *,
        access: HostMountAccess,
        principal: LocalPrincipal,
        file_key: str,
        content_base64: str,
        mime_type: str,
    ) -> dict[str, object]:
        self._require_write(access)
        client = self._client_for(principal)
        return client.write_file(
            mount_id=access.mount.mount_id,
            file_key=file_key,
            content_base64=content_base64,
            mime_type=mime_type,
        )

    def helper_create_directory(
        self,
        *,
        access: HostMountAccess,
        principal: LocalPrincipal,
        directory: str,
    ) -> dict[str, object]:
        self._require_write(access)
        client = self._client_for(principal)
        return client.create_directory(mount_id=access.mount.mount_id, directory=directory)

    def helper_move_path(
        self,
        *,
        access: HostMountAccess,
        principal: LocalPrincipal,
        source_path: str,
        destination_path: str,
    ) -> dict[str, object]:
        self._require_write(access)
        client = self._client_for(principal)
        return client.move_path(
            mount_id=access.mount.mount_id,
            source_path=source_path,
            destination_path=destination_path,
        )

    def helper_delete_path(
        self,
        *,
        access: HostMountAccess,
        principal: LocalPrincipal,
        path: str,
        recursive: bool,
    ) -> dict[str, object]:
        self._require_write(access)
        client = self._client_for(principal)
        return client.delete_path(mount_id=access.mount.mount_id, path=path, recursive=recursive)

    def helper_upload_files(
        self,
        *,
        access: HostMountAccess,
        principal: LocalPrincipal,
        directory: str,
        files: list[dict[str, str]],
    ) -> dict[str, object]:
        self._require_write(access)
        client = self._client_for(principal)
        return client.upload_files(mount_id=access.mount.mount_id, directory=directory, files=files)

    def _client_for(self, principal: LocalPrincipal) -> HostFilesystemHelperClient:
        settings = self.settings(principal=principal)
        integration = self._require_integration(principal)
        credential = self._decrypt_credential(integration)
        return HostFilesystemHelperClient(base_url=settings.helper_base_url, credential=credential)

    def _require_integration(self, principal: LocalPrincipal) -> HostFilesystemIntegration:
        integration = self._repository.active_integration(
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
        )
        if integration is None:
            raise HostFilesystemAuthorizationError("Host filesystem helper is not paired.")
        return integration

    def _require_enabled(self, principal: LocalPrincipal) -> None:
        if not self.is_enabled_for(principal=principal):
            raise HostFilesystemAuthorizationError("Host filesystem access is disabled.")

    @staticmethod
    def _require_write(access: HostMountAccess) -> None:
        if not access.can_write:
            raise HostFilesystemAuthorizationError("Write access is required.")

    @staticmethod
    def _normalize_mount_name(name: str) -> str:
        normalized = name.strip()
        if not _MOUNT_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("Folder name must use letters, numbers, dots, dashes, or underscores.")
        return normalized

    def _encrypt_credential(self, credential: str) -> str:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._credential_key.load_or_create()).encrypt(
            nonce,
            credential.encode("utf-8"),
            b"host-filesystem-outbound",
        )
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def _decrypt_credential(self, integration: HostFilesystemIntegration) -> str:
        encrypted = self._repository.outbound_credential_enc(integration_id=integration.integration_id)
        if not encrypted:
            raise HostFilesystemAuthorizationError("Host filesystem helper is not fully paired.")
        raw = base64.b64decode(encrypted.encode("ascii"))
        nonce, ciphertext = raw[:12], raw[12:]
        plaintext = AESGCM(self._credential_key.load_or_create()).decrypt(
            nonce,
            ciphertext,
            b"host-filesystem-outbound",
        )
        return plaintext.decode("utf-8")

    @staticmethod
    def _integration_payload(integration: HostFilesystemIntegration) -> dict[str, object]:
        return {
            "integrationId": integration.integration_id,
            "displayName": integration.display_name,
            "adapterKind": integration.adapter_kind,
            "status": integration.status,
            "createdAt": integration.created_at.isoformat(),
            "revokedAt": integration.revoked_at.isoformat() if integration.revoked_at else None,
        }

    def agent_mount_descriptors(self, *, principal: LocalPrincipal) -> list[dict[str, object]]:
        if not self.is_enabled_for(principal=principal):
            return []
        return [
            {
                "path": build_local_mount_path(mount_name=mount.mount_name),
                "mountName": mount.mount_name,
                "permission": mount.permission,
                "source": mount.source,
                "agentAccessible": mount.source == "helper",
            }
            for mount in self._repository.list_mounts(
                user_id=principal.user_id,
                workspace_id=principal.workspace_id,
            )
        ]

    @staticmethod
    def _mount_payload(mount: HostFilesystemMount) -> dict[str, object]:
        return {
            "mountId": mount.mount_id,
            "mountName": mount.mount_name,
            "mountPath": build_local_mount_path(mount_name=mount.mount_name),
            "permission": mount.permission,
            "source": mount.source,
            "status": mount.status,
            "createdAt": mount.created_at.isoformat(),
        }
