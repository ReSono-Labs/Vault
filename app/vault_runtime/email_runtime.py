"""Local composition adapter around the copied Voice multi-account Mail client."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from typing import Any, Iterator

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.vault_runtime.email_service import VaultEmailService
from app.vault_runtime.email_store import VaultPostgresEmailStore
from app.vault_runtime.extensions.secrets import LocalMasterKey
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.signals.email.session_tools import VaultEmailSignalSessionTools


class LocalEmailRuntime:
    def __init__(self, *, database_url: str, master_key: LocalMasterKey, provider: Any = None) -> None:
        self._database_url = database_url
        self._master_key = master_key
        self._provider = provider

    @contextmanager
    def service(self, principal: LocalPrincipal) -> Iterator[VaultEmailService]:
        import psycopg
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            store = _ScopedEmailStore(
                connection=connection, principal=principal, master_key=self._master_key,
            )
            yield VaultEmailService(store=store, provider=self._provider)

    @contextmanager
    def tools(self, principal: LocalPrincipal, *, mailbox_role: str = "normal_email") -> Iterator[VaultEmailSignalSessionTools]:
        import psycopg
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            store = _ScopedEmailStore(
                connection=connection, principal=principal, master_key=self._master_key,
            )
            yield VaultEmailSignalSessionTools(store=store, mailbox_role=mailbox_role)


class _ScopedEmailStore:
    def __init__(self, *, connection: Any, principal: LocalPrincipal, master_key: LocalMasterKey) -> None:
        self._connection = connection
        self._principal = principal
        self._master_key = master_key
        self._email = _ScopedEmailRepository(
            VaultPostgresEmailStore(connection), principal=principal,
        )

    def email_store(self) -> Any:
        return self._email

    def _require_scope(self, account_id: str, workspace_id: str) -> None:
        if account_id != self._principal.user_id or workspace_id != self._principal.workspace_id:
            raise PermissionError("Mail scope was not authorized.")

    def upsert_provider_credential(
        self, payload: dict[str, Any], *, account_id: str, workspace_id: str,
    ) -> dict[str, Any]:
        self._require_scope(account_id, workspace_id)
        if payload.get("providerKind") != "email":
            raise ValueError("Only the built-in Mail credential type is accepted.")
        credential_id = str(payload.get("providerCredentialId") or "").strip()
        credentials = payload.get("credentials")
        if not credential_id or not isinstance(credentials, dict):
            raise ValueError("Mail credential payload is invalid.")
        plaintext = json.dumps(credentials, sort_keys=True, separators=(",", ":")).encode()
        nonce = os.urandom(12)
        aad = f"{account_id}:{workspace_id}:{credential_id}:mail".encode()
        ciphertext = AESGCM(self._master_key.load_or_create()).encrypt(nonce, plaintext, aad)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO vault_private.vault_email_provider_credentials
                     (provider_credential_id,account_id,workspace_id,nonce,ciphertext,status)
                   VALUES (%s,%s,%s,%s,%s,'active')
                   ON CONFLICT (provider_credential_id) DO UPDATE SET
                     account_id=EXCLUDED.account_id,workspace_id=EXCLUDED.workspace_id,
                     nonce=EXCLUDED.nonce,ciphertext=EXCLUDED.ciphertext,status='active',updated_at=now()""",
                (credential_id,account_id,workspace_id,nonce,ciphertext),
            )
        self._connection.commit()
        return {"providerCredentialId": credential_id, "status": "active"}

    def get_provider_credential_by_id(
        self, *, account_id: str, workspace_id: str, provider_credential_id: str,
    ) -> dict[str, Any] | None:
        self._require_scope(account_id, workspace_id)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT nonce,ciphertext FROM vault_private.vault_email_provider_credentials
                   WHERE provider_credential_id=%s AND account_id=%s AND workspace_id=%s AND status='active'""",
                (provider_credential_id,account_id,workspace_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        aad = f"{account_id}:{workspace_id}:{provider_credential_id}:mail".encode()
        try:
            plaintext = AESGCM(self._master_key.load_or_create()).decrypt(bytes(row[0]), bytes(row[1]), aad)
            credentials = json.loads(plaintext)
        except Exception as exc:
            raise RuntimeError("Mail credential cannot be decrypted.") from exc
        if not isinstance(credentials, dict):
            raise RuntimeError("Mail credential payload is invalid.")
        return {"sourcePayload": {"providerKind": "email", "credentials": credentials}}

    def delete_provider_credential_by_id(
        self, *, account_id: str, workspace_id: str, provider_credential_id: str,
    ) -> bool:
        self._require_scope(account_id, workspace_id)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """DELETE FROM vault_private.vault_email_provider_credentials
                   WHERE provider_credential_id=%s AND account_id=%s AND workspace_id=%s""",
                (provider_credential_id,account_id,workspace_id),
            )
            changed = cursor.rowcount > 0
        self._connection.commit()
        return changed


class _ScopedEmailRepository:
    """Bind every donor repository call carrying scope to the local principal."""
    def __init__(self, repository: VaultPostgresEmailStore, *, principal: LocalPrincipal) -> None:
        self._repository = repository
        self._principal = principal

    def __getattr__(self, name: str):
        value = getattr(self._repository, name)
        if not callable(value):
            return value

        def scoped(*args, **kwargs):
            account_id = kwargs.get("account_id")
            workspace_id = kwargs.get("workspace_id")
            if account_id is not None and account_id != self._principal.user_id:
                raise PermissionError("Mail user scope was not authorized.")
            if workspace_id is not None and workspace_id != self._principal.workspace_id:
                raise PermissionError("Mail workspace scope was not authorized.")
            return value(*args, **kwargs)

        return scoped
