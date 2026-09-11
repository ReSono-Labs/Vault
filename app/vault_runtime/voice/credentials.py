"""Workspace-scoped Voice provider secrets adapted from Voice credentials and Phase 5 AES-GCM."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
import os
import json
import time
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.vault_runtime.extensions.secrets import LocalMasterKey
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.voice.provider import ProviderCredential


class VoiceProviderCredentialError(RuntimeError):
    code = "voice_provider_credential_error"


class VoiceProviderCredentialStore:
    def __init__(
        self, *, database_url: str, master_key: LocalMasterKey,
        connector: Callable[..., AbstractContextManager[Any]] | None = None,
        google_oauth_client_id: str | None = None,
        google_oauth_client_secret: str | None = None,
    ) -> None:
        self._database_url = database_url
        self._master_key = master_key
        self._connector = connector
        self._google_oauth_client_id = google_oauth_client_id
        self._google_oauth_client_secret = google_oauth_client_secret

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    @staticmethod
    def _require_scope(cursor: Any, principal: LocalPrincipal, *, owner: bool) -> None:
        cursor.execute(
            """SELECT u.is_device_owner FROM vault_private.local_users u
               JOIN vault_private.local_workspace_memberships m ON m.user_id=u.user_id
               JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
               WHERE u.user_id=%s AND m.workspace_id=%s AND u.status='active'
                 AND m.status='active' AND w.status='active'""",
            (principal.user_id, principal.workspace_id),
        )
        row = cursor.fetchone()
        if row is None or (owner and not bool(row[0])):
            raise VoiceProviderCredentialError("Vault master-account authority is required.")

    @staticmethod
    def _shared_provider_workspace(cursor: Any) -> str:
        """Resolve the permanent master's private workspace as provider authority."""
        cursor.execute(
            """SELECT m.workspace_id
               FROM vault_private.local_users u
               JOIN vault_private.local_workspace_memberships m ON m.user_id=u.user_id
               JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
               WHERE u.is_device_owner=true AND u.status='active'
                 AND m.membership_type='owner' AND m.status='active' AND w.status='active'
               ORDER BY u.created_at,m.created_at,m.workspace_id LIMIT 1"""
        )
        row = cursor.fetchone()
        if row is None:
            raise VoiceProviderCredentialError("Vault master provider workspace is unavailable.")
        return str(row[0])

    @staticmethod
    def _user_workspace(cursor: Any, user_id: str) -> str:
        cursor.execute(
            """SELECT m.workspace_id FROM vault_private.local_users u
               JOIN vault_private.local_workspace_memberships m ON m.user_id=u.user_id
               JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
               WHERE u.user_id=%s AND u.status='active' AND m.membership_type='owner'
                 AND m.status='active' AND w.status='active' LIMIT 1""", (user_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise VoiceProviderCredentialError("Local account is unavailable.")
        return str(row[0])

    def _provider_workspace(self, cursor: Any, principal: LocalPrincipal, provider_key: str) -> tuple[str, str]:
        cursor.execute(
            "SELECT access_mode FROM vault_private.vault_voice_provider_access WHERE user_id=%s AND provider_key=%s",
            (principal.user_id, provider_key),
        )
        row = cursor.fetchone()
        mode = str(row[0]) if row else "shared"
        return (self._user_workspace(cursor, principal.user_id) if mode == "individual" else self._shared_provider_workspace(cursor), mode)

    def status(
        self, principal: LocalPrincipal, provider_key: str = "openai", *,
        default_model_key: str = "gpt-realtime", default_voice: str = "marin",
        default_background_model_key: str = "gpt-5.6-sol",
    ) -> dict[str, object]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=False)
                provider_workspace_id, access_mode = self._provider_workspace(cursor, principal, provider_key)
                cursor.execute(
                    """SELECT model_key,voice,background_model_key,updated_at,auth_method,api_key_configured,
                              EXISTS(SELECT 1 FROM vault_private.vault_ai_oauth_credentials o
                                     WHERE o.workspace_id=vault_voice_provider_credentials.workspace_id
                                       AND o.provider_key=vault_voice_provider_credentials.provider_key)
                       FROM vault_private.vault_voice_provider_credentials
                       WHERE workspace_id=%s AND provider_key=%s""",
                    (provider_workspace_id, provider_key),
                )
                row = cursor.fetchone()
        return {
            "providerKey": provider_key,
            "configured": row is not None,
            "modelKey": str(row[0]) if row else default_model_key,
            "voice": str(row[1]) if row else default_voice,
            "backgroundModelKey": str(row[2]) if row else default_background_model_key,
            "updatedAt": row[3].isoformat() if row else None,
            "accessMode": access_mode,
            "authMethod": str(row[4]) if row else None,
            "apiKeyConnected": bool(row[5]) if row else False,
            "oauthConnected": bool(row[6]) if row else False,
        }

    def account_access_status(self, principal: LocalPrincipal, target_user_id: str, provider_key: str = "openai") -> dict[str, object]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=True)
                target_workspace = self._user_workspace(cursor, target_user_id)
                cursor.execute("SELECT access_mode FROM vault_private.vault_voice_provider_access WHERE user_id=%s AND provider_key=%s", (target_user_id, provider_key))
                policy = cursor.fetchone()
                mode = str(policy[0]) if policy else "shared"
                shared_workspace = self._shared_provider_workspace(cursor)
                cursor.execute("SELECT 1 FROM vault_private.vault_voice_provider_credentials WHERE workspace_id=%s AND provider_key=%s", (shared_workspace, provider_key))
                shared_configured = cursor.fetchone() is not None
                cursor.execute("SELECT 1 FROM vault_private.vault_voice_provider_credentials WHERE workspace_id=%s AND provider_key=%s", (target_workspace, provider_key))
                individual_configured = cursor.fetchone() is not None
        return {"userId": target_user_id, "accessMode": mode, "sharedConfigured": shared_configured, "individualConfigured": individual_configured}

    def set_account_access(
        self, principal: LocalPrincipal, *, target_user_id: str, access_mode: str,
        provider_key: str = "openai", api_key: str | None = None,
        model_key: str = "gpt-realtime", voice: str = "alloy",
        background_model_key: str = "gpt-5.6-sol",
    ) -> None:
        if access_mode not in {"shared", "individual"}:
            raise ValueError("accessMode is invalid")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=True)
                target_workspace = self._user_workspace(cursor, target_user_id)
                if access_mode == "individual":
                    secret = _bounded(api_key or "", "apiKey", 4096)
                    if any(character.isspace() for character in secret):
                        raise ValueError("apiKey is malformed")
                    nonce = os.urandom(12)
                    aad = f"{target_workspace}:{provider_key}:voice-provider".encode()
                    ciphertext = AESGCM(self._master_key.load_or_create()).encrypt(nonce, secret.encode(), aad)
                    cursor.execute(
                        """INSERT INTO vault_private.vault_voice_provider_credentials
                             (workspace_id,provider_key,model_key,background_model_key,voice,nonce,ciphertext,changed_by_user_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (workspace_id,provider_key) DO UPDATE SET model_key=EXCLUDED.model_key,
                             background_model_key=EXCLUDED.background_model_key,voice=EXCLUDED.voice,
                             nonce=EXCLUDED.nonce,ciphertext=EXCLUDED.ciphertext,
                             changed_by_user_id=EXCLUDED.changed_by_user_id,updated_at=now()""",
                        (target_workspace,provider_key,_bounded(model_key,"modelKey",255),_bounded(background_model_key,"backgroundModelKey",255),_bounded(voice,"voice",120),nonce,ciphertext,principal.user_id),
                    )
                cursor.execute(
                    """INSERT INTO vault_private.vault_voice_provider_access (user_id,provider_key,access_mode,changed_by_user_id)
                       VALUES (%s,%s,%s,%s) ON CONFLICT (user_id,provider_key) DO UPDATE SET
                       access_mode=EXCLUDED.access_mode,changed_by_user_id=EXCLUDED.changed_by_user_id,updated_at=now()""",
                    (target_user_id,provider_key,access_mode,principal.user_id),
                )

    def update_preferences(
        self,
        principal: LocalPrincipal,
        *,
        provider_key: str,
        model_key: str,
        voice: str,
        background_model_key: str = "gpt-5.6-sol",
    ) -> None:
        provider = _bounded(provider_key, "providerKey", 120)
        model = _bounded(model_key, "modelKey", 255)
        selected_voice = _bounded(voice, "voice", 120)
        background_model = _bounded(background_model_key, "backgroundModelKey", 255)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=True)
                provider_workspace_id = self._shared_provider_workspace(cursor)
                cursor.execute(
                    """SELECT auth_method FROM vault_private.vault_voice_provider_credentials
                       WHERE workspace_id=%s AND provider_key=%s""",
                    (provider_workspace_id, provider),
                )
                row = cursor.fetchone()
                if row is None:
                    raise VoiceProviderCredentialError("Voice provider is not configured.")
                cursor.execute(
                    """UPDATE vault_private.vault_voice_provider_credentials
                       SET model_key=%s, background_model_key=%s, voice=%s,
                           changed_by_user_id=%s, updated_at=now()
                       WHERE workspace_id=%s AND provider_key=%s""",
                    (
                        model, background_model, selected_voice, principal.user_id,
                        provider_workspace_id, provider,
                    ),
                )

    def set(
        self, principal: LocalPrincipal, *, provider_key: str, api_key: str,
        model_key: str, voice: str, background_model_key: str = "gpt-5.6-sol",
    ) -> None:
        provider = _bounded(provider_key, "providerKey", 120)
        model = _bounded(model_key, "modelKey", 255)
        selected_voice = _bounded(voice, "voice", 120)
        background_model = _bounded(background_model_key, "backgroundModelKey", 255)
        secret = _bounded(api_key, "apiKey", 4096)
        if any(character.isspace() for character in secret):
            raise ValueError("apiKey is malformed")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=True)
                provider_workspace_id = self._shared_provider_workspace(cursor)
                nonce = os.urandom(12)
                aad = f"{provider_workspace_id}:{provider}:voice-provider".encode()
                ciphertext = AESGCM(self._master_key.load_or_create()).encrypt(nonce, secret.encode(), aad)
                cursor.execute(
                    """INSERT INTO vault_private.vault_voice_provider_credentials
                         (workspace_id,provider_key,model_key,background_model_key,voice,nonce,ciphertext,changed_by_user_id,auth_method)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'api_key')
                       ON CONFLICT (workspace_id,provider_key) DO UPDATE SET
                         model_key=EXCLUDED.model_key,background_model_key=EXCLUDED.background_model_key,
                         voice=EXCLUDED.voice,nonce=EXCLUDED.nonce,
                         ciphertext=EXCLUDED.ciphertext,changed_by_user_id=EXCLUDED.changed_by_user_id,
                         auth_method='api_key',api_key_configured=true,updated_at=now()""",
                    (provider_workspace_id,provider,model,background_model,selected_voice,nonce,ciphertext,principal.user_id),
                )
                cursor.execute(
                    """INSERT INTO vault_private.vault_ai_provider_selection
                         (workspace_id,provider_key,changed_by_user_id) VALUES (%s,%s,%s)
                       ON CONFLICT (workspace_id) DO UPDATE SET provider_key=EXCLUDED.provider_key,
                         changed_by_user_id=EXCLUDED.changed_by_user_id,updated_at=now()""",
                    (principal.workspace_id, provider, principal.user_id),
                )

    def remove(self, principal: LocalPrincipal, provider_key: str = "openai") -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=True)
                provider_workspace_id = self._shared_provider_workspace(cursor)
                cursor.execute(
                    "DELETE FROM vault_private.vault_voice_provider_credentials WHERE workspace_id=%s AND provider_key=%s",
                    (provider_workspace_id, provider_key),
                )
                cursor.execute(
                    "DELETE FROM vault_private.vault_ai_provider_selection WHERE workspace_id=%s AND provider_key=%s",
                    (provider_workspace_id, provider_key),
                )

    def selected_provider(self, *, user_id: str, workspace_id: str) -> str:
        principal = type("ScopedPrincipal", (), {"user_id": user_id, "workspace_id": workspace_id})()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=False)  # type: ignore[arg-type]
                cursor.execute(
                    "SELECT provider_key FROM vault_private.vault_ai_provider_selection WHERE workspace_id=%s",
                    (workspace_id,),
                )
                row = cursor.fetchone()
        return str(row[0]) if row else "openai"

    def select_provider(self, principal: LocalPrincipal, provider_key: str) -> None:
        provider = _bounded(provider_key, "providerKey", 120)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=False)
                provider_workspace_id, _mode = self._provider_workspace(cursor, principal, provider)
                cursor.execute(
                    "SELECT 1 FROM vault_private.vault_voice_provider_credentials WHERE workspace_id=%s AND provider_key=%s",
                    (provider_workspace_id, provider),
                )
                if cursor.fetchone() is None:
                    raise VoiceProviderCredentialError("Selected AI provider is not configured.")
                cursor.execute(
                    """INSERT INTO vault_private.vault_ai_provider_selection
                         (workspace_id,provider_key,changed_by_user_id) VALUES (%s,%s,%s)
                       ON CONFLICT (workspace_id) DO UPDATE SET provider_key=EXCLUDED.provider_key,
                         changed_by_user_id=EXCLUDED.changed_by_user_id,updated_at=now()""",
                    (principal.workspace_id, provider, principal.user_id),
                )

    def resolve(self, principal: LocalPrincipal, provider_key: str) -> ProviderCredential:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=False)
                provider_workspace_id, _mode = self._provider_workspace(cursor, principal, provider_key)
                cursor.execute(
                    """SELECT c.nonce,c.ciphertext,c.auth_method,o.nonce,o.ciphertext
                       FROM vault_private.vault_voice_provider_credentials c
                       LEFT JOIN vault_private.vault_ai_oauth_credentials o
                         ON o.workspace_id=c.workspace_id AND o.provider_key=c.provider_key
                       WHERE c.workspace_id=%s AND c.provider_key=%s""",
                    (provider_workspace_id, provider_key),
                )
                row = cursor.fetchone()
        if row is None:
            raise VoiceProviderCredentialError("Voice provider is not configured.")
        aad = f"{provider_workspace_id}:{provider_key}:voice-provider".encode()
        auth_method = str(row[2])
        selected_nonce, selected_ciphertext = (row[3], row[4]) if auth_method != "api_key" else (row[0], row[1])
        if selected_nonce is None or selected_ciphertext is None:
            raise VoiceProviderCredentialError("Selected OAuth connection is unavailable.")
        try:
            value = AESGCM(self._master_key.load_or_create()).decrypt(bytes(selected_nonce), bytes(selected_ciphertext), aad).decode()
        except Exception as exc:
            raise VoiceProviderCredentialError("Voice provider credential cannot be decrypted.") from exc
        if auth_method != "api_key":
            payload = json.loads(value)
            refreshed = self._refresh_oauth(provider_key, payload)
            if refreshed != payload:
                self._store_refreshed_oauth(provider_workspace_id, provider_key, refreshed)
            payload = refreshed
            value = str(payload.get("access_token") or "")
            if not value:
                raise VoiceProviderCredentialError("OAuth connection must be reconnected.")
        return ProviderCredential(value, auth_method=auth_method)

    def resolve_api_key(self, principal: LocalPrincipal, provider_key: str) -> ProviderCredential:
        """Resolve the retained API key even while OAuth is selected."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=False)
                provider_workspace_id, _mode = self._provider_workspace(cursor, principal, provider_key)
                cursor.execute(
                    """SELECT nonce,ciphertext,api_key_configured
                       FROM vault_private.vault_voice_provider_credentials
                       WHERE workspace_id=%s AND provider_key=%s""",
                    (provider_workspace_id, provider_key),
                )
                row = cursor.fetchone()
        if row is None or not bool(row[2]):
            raise VoiceProviderCredentialError("Provider API key is not configured.")
        aad = f"{provider_workspace_id}:{provider_key}:voice-provider".encode()
        try:
            value = AESGCM(self._master_key.load_or_create()).decrypt(
                bytes(row[0]), bytes(row[1]), aad,
            ).decode()
        except Exception as exc:
            raise VoiceProviderCredentialError("Provider API key cannot be decrypted.") from exc
        return ProviderCredential(value, auth_method="api_key")

    def _store_refreshed_oauth(
        self, workspace_id: str, provider_key: str, payload: dict[str, object],
    ) -> None:
        aad = f"{workspace_id}:{provider_key}:voice-provider".encode()
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._master_key.load_or_create()).encrypt(
            nonce, json.dumps(payload, separators=(",", ":")).encode(), aad,
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE vault_private.vault_ai_oauth_credentials SET nonce=%s,ciphertext=%s,updated_at=now() WHERE workspace_id=%s AND provider_key=%s",
                    (nonce, ciphertext, workspace_id, provider_key),
                )

    def set_oauth_tokens(
        self, principal: LocalPrincipal, *, provider_key: str, auth_method: str,
        token_payload: dict[str, object], model_key: str, background_model_key: str, voice: str,
    ) -> None:
        if auth_method not in {"chatgpt_oauth", "gemini_oauth"}:
            raise ValueError("OAuth method is invalid")
        serialized = json.dumps(token_payload, separators=(",", ":"))
        provider = _bounded(provider_key, "providerKey", 120)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=True)
                provider_workspace_id = self._shared_provider_workspace(cursor)
                nonce = os.urandom(12)
                aad = f"{provider_workspace_id}:{provider}:voice-provider".encode()
                key = self._master_key.load_or_create()
                ciphertext = AESGCM(key).encrypt(nonce, serialized.encode(), aad)
                placeholder_nonce = os.urandom(12)
                placeholder = AESGCM(key).encrypt(placeholder_nonce, b"oauth-managed", aad)
                cursor.execute(
                    """INSERT INTO vault_private.vault_voice_provider_credentials
                         (workspace_id,provider_key,model_key,background_model_key,voice,nonce,ciphertext,changed_by_user_id,auth_method,api_key_configured)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,false)
                       ON CONFLICT (workspace_id,provider_key) DO UPDATE SET
                         auth_method=EXCLUDED.auth_method,
                         changed_by_user_id=EXCLUDED.changed_by_user_id,updated_at=now()""",
                    (provider_workspace_id, provider, model_key, background_model_key, voice,
                     placeholder_nonce, placeholder, principal.user_id, auth_method),
                )
                cursor.execute(
                    """INSERT INTO vault_private.vault_ai_oauth_credentials
                         (workspace_id,provider_key,nonce,ciphertext) VALUES (%s,%s,%s,%s)
                       ON CONFLICT (workspace_id,provider_key) DO UPDATE SET nonce=EXCLUDED.nonce,
                         ciphertext=EXCLUDED.ciphertext,updated_at=now()""",
                    (provider_workspace_id, provider, nonce, ciphertext),
                )
                cursor.execute(
                    """INSERT INTO vault_private.vault_ai_provider_selection
                         (workspace_id,provider_key,changed_by_user_id) VALUES (%s,%s,%s)
                       ON CONFLICT (workspace_id) DO UPDATE SET provider_key=EXCLUDED.provider_key,
                         changed_by_user_id=EXCLUDED.changed_by_user_id,updated_at=now()""",
                    (principal.workspace_id, provider, principal.user_id),
                )

    def select_auth_method(self, principal: LocalPrincipal, *, provider_key: str, auth_method: str) -> None:
        if auth_method not in {"api_key", "chatgpt_oauth", "gemini_oauth"}:
            raise ValueError("authMethod is invalid")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=True)
                workspace_id = self._shared_provider_workspace(cursor)
                cursor.execute(
                    """SELECT api_key_configured,
                              EXISTS(SELECT 1 FROM vault_private.vault_ai_oauth_credentials o
                                     WHERE o.workspace_id=c.workspace_id AND o.provider_key=c.provider_key)
                       FROM vault_private.vault_voice_provider_credentials c
                       WHERE c.workspace_id=%s AND c.provider_key=%s""",
                    (workspace_id, provider_key),
                )
                row = cursor.fetchone()
                if row is None or (auth_method == "api_key" and not bool(row[0])) or (auth_method != "api_key" and not bool(row[1])):
                    raise VoiceProviderCredentialError("Requested provider connection is not configured.")
                cursor.execute(
                    """UPDATE vault_private.vault_voice_provider_credentials
                       SET auth_method=%s,
                           model_key=CASE WHEN %s='api_key' AND model_key='gpt-live-1'
                                          THEN 'gpt-realtime-2.1' ELSE model_key END,
                           voice=CASE WHEN %s='api_key' AND lower(voice)='sol'
                                      THEN 'marin' ELSE voice END,
                           updated_at=now()
                       WHERE workspace_id=%s AND provider_key=%s""",
                    (auth_method, auth_method, auth_method, workspace_id, provider_key),
                )

    def remove_oauth(self, principal: LocalPrincipal, provider_key: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=True)
                workspace_id = self._shared_provider_workspace(cursor)
                cursor.execute(
                    "SELECT api_key_configured FROM vault_private.vault_voice_provider_credentials WHERE workspace_id=%s AND provider_key=%s",
                    (workspace_id, provider_key),
                )
                row = cursor.fetchone()
                cursor.execute(
                    "DELETE FROM vault_private.vault_ai_oauth_credentials WHERE workspace_id=%s AND provider_key=%s",
                    (workspace_id, provider_key),
                )
                if row is not None and bool(row[0]):
                    cursor.execute(
                        """UPDATE vault_private.vault_voice_provider_credentials
                           SET auth_method='api_key',
                               model_key=CASE WHEN model_key='gpt-live-1' THEN 'gpt-realtime-2.1' ELSE model_key END,
                               voice=CASE WHEN lower(voice)='sol' THEN 'marin' ELSE voice END,
                               updated_at=now() WHERE workspace_id=%s AND provider_key=%s""",
                        (workspace_id, provider_key),
                    )
                elif row is not None:
                    cursor.execute(
                        "DELETE FROM vault_private.vault_voice_provider_credentials WHERE workspace_id=%s AND provider_key=%s",
                        (workspace_id, provider_key),
                    )

    def _refresh_oauth(self, provider_key: str, payload: dict[str, object]) -> dict[str, object]:
        expires_at = int(payload.get("_resono_expires_at") or 0)
        if expires_at > int(time.time()) + 300:
            return payload
        refresh_token = payload.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            return payload
        import httpx
        if provider_key == "openai":
            response = httpx.post("https://auth.openai.com/oauth/token", json={
                "grant_type": "refresh_token", "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
                "refresh_token": refresh_token,
            }, headers={"Accept": "application/json"}, timeout=30.0)
        elif provider_key == "gemini" and self._google_oauth_client_id and self._google_oauth_client_secret:
            response = httpx.post("https://oauth2.googleapis.com/token", data={
                "grant_type": "refresh_token", "client_id": self._google_oauth_client_id,
                "client_secret": self._google_oauth_client_secret, "refresh_token": refresh_token,
            }, timeout=30.0)
        else:
            return payload
        response.raise_for_status()
        refreshed = response.json()
        if not isinstance(refreshed, dict):
            return payload
        refreshed.setdefault("refresh_token", refresh_token)
        if isinstance(refreshed.get("expires_in"), int):
            refreshed["_resono_expires_at"] = int(time.time()) + int(refreshed["expires_in"])
        return refreshed

    def background_access(self, *, user_id: str, workspace_id: str, provider_key: str | None = None) -> tuple[ProviderCredential, str]:
        provider_key = provider_key or self.selected_provider(user_id=user_id, workspace_id=workspace_id)
        principal = type("ScopedPrincipal", (), {"user_id": user_id, "workspace_id": workspace_id})()
        credential = self.resolve(principal, provider_key)  # type: ignore[arg-type]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal, owner=False)  # type: ignore[arg-type]
                provider_workspace_id, _mode = self._provider_workspace(cursor, principal, provider_key)  # type: ignore[arg-type]
                cursor.execute(
                    """SELECT background_model_key FROM vault_private.vault_voice_provider_credentials
                       WHERE workspace_id=%s AND provider_key=%s""",
                    (provider_workspace_id,provider_key),
                )
                row = cursor.fetchone()
        if row is None:
            raise VoiceProviderCredentialError("Background model is not configured.")
        return credential, str(row[0])


def _bounded(value: str, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} is invalid")
    return value
