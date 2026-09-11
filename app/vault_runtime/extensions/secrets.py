"""Local encrypted credential owner replacing R1's Android credential envelope."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.vault_runtime.extensions.repository import (
    ExtensionAuthorizationError, ExtensionNotFoundError, ExtensionRepository,
)


class ExtensionSecretError(RuntimeError):
    code = "extension_secret_error"


class LocalMasterKey:
    def __init__(self, path: Path) -> None:
        self._path = path.resolve()

    def load_or_create(self) -> bytes:
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            try:
                os.write(descriptor, os.urandom(32))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        mode = self._path.stat().st_mode & 0o777
        if mode & 0o077:
            raise ExtensionSecretError("local credential key permissions are unsafe")
        key = self._path.read_bytes()
        if len(key) != 32:
            raise ExtensionSecretError("local credential key is invalid")
        return key


class ExtensionSecretStore:
    def __init__(
        self, *, repository: ExtensionRepository, master_key: LocalMasterKey,
    ) -> None:
        self._repository = repository
        self._key = master_key

    def set_headers(
        self, *, actor_user_id: str, workspace_id: str, extension_id: str,
        headers: dict[str, str],
    ) -> None:
        if not headers or any(
            not isinstance(name, str) or not name.strip() or not isinstance(value, str) or not value
            for name, value in headers.items()
        ):
            raise ValueError("credential headers must map names to non-empty values")
        import json
        plaintext = json.dumps(headers, sort_keys=True, separators=(",", ":")).encode()
        nonce = os.urandom(12)
        aad = f"{workspace_id}:{extension_id}:headers".encode()
        ciphertext = AESGCM(self._key.load_or_create()).encrypt(nonce, plaintext, aad)
        with self._repository._connect() as connection:
            with connection.cursor() as cursor:
                self._repository._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute("SELECT 1 FROM vault_private.vault_extensions WHERE extension_id=%s AND installed_in_workspace_id=%s AND kind='mcp' AND state <> 'removed'", (extension_id,workspace_id))
                if cursor.fetchone() is None:
                    raise ExtensionNotFoundError("MCP connection is unavailable")
                cursor.execute(
                    """INSERT INTO vault_private.vault_extension_secrets
                       (extension_id,secret_name,nonce,ciphertext,changed_by_user_id)
                       VALUES (%s,'headers',%s,%s,%s)
                       ON CONFLICT (extension_id,secret_name) DO UPDATE SET
                         nonce=EXCLUDED.nonce,ciphertext=EXCLUDED.ciphertext,
                         changed_by_user_id=EXCLUDED.changed_by_user_id,updated_at=now()""",
                    (extension_id,nonce,ciphertext,actor_user_id),
                )

    def resolve_headers(
        self, *, user_id: str, workspace_id: str, extension_id: str,
    ) -> tuple[tuple[str, str], ...]:
        import json
        with self._repository._connect() as connection:
            with connection.cursor() as cursor:
                self._repository._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """SELECT s.nonce,s.ciphertext FROM vault_private.vault_extension_secrets s
                       JOIN vault_private.vault_extensions e ON e.extension_id=s.extension_id
                       WHERE s.extension_id=%s AND s.secret_name='headers'
                         AND e.installed_in_workspace_id=%s AND e.state='enabled'""",
                    (extension_id,workspace_id),
                )
                row = cursor.fetchone()
        if row is None:
            return ()
        aad = f"{workspace_id}:{extension_id}:headers".encode()
        try:
            plaintext = AESGCM(self._key.load_or_create()).decrypt(bytes(row[0]), bytes(row[1]), aad)
            value = json.loads(plaintext)
        except Exception as exc:
            raise ExtensionSecretError("local MCP credential cannot be decrypted") from exc
        if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
            raise ExtensionSecretError("local MCP credential payload is invalid")
        return tuple(sorted(value.items()))

    def remove(self, *, actor_user_id: str, workspace_id: str, extension_id: str) -> None:
        with self._repository._connect() as connection:
            with connection.cursor() as cursor:
                self._repository._require_scope(cursor, user_id=actor_user_id, workspace_id=workspace_id, owner=True)
                cursor.execute("DELETE FROM vault_private.vault_extension_secrets WHERE extension_id=%s", (extension_id,))
