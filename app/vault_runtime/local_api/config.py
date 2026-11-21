from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from app.vault_runtime.folders.models import LOCATION_KINDS, DeviceLocation
from app.vault_runtime.runtime_paths import resolve_vault_data_root


@dataclass(frozen=True, slots=True)
class VaultLocalApiConfig:
    host: str
    port: int
    token: str | None
    data_root: str
    storage_status_file: str
    storage_mount_point: str
    database_url: str | None = None
    database_url_file: str | None = None
    setup_credential_hash: str | None = None
    setup_credential_hash_file: str | None = None
    session_capability_secret: str | None = None
    session_capability_secret_file: str | None = None
    device_identity_key_file: str | None = None
    max_body_bytes: int = 134_217_728
    browser_startup_host: str | None = None
    browser_startup_port: int = 8766
    browser_startup_allowed_origins: tuple[str, ...] = ()
    browser_media_enabled: bool = False
    browser_media_port: int = 8767
    browser_media_path: str = "/session-relay/ws"
    session_opaque_relay_ttl_seconds: int = 7_200
    web_root: str | None = None
    tls_certificate_file: str | None = None
    tls_private_key_file: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    plugin_service_url: str = "https://127.0.0.1:8765/plugin-services/v1"
    # Feature flags below (decision review, indexed memory, coordination, owner approvals, GenUI,
    # presentation hints) are kept as emergency off-switches (owner decision 6-A, cleanup B5).
    # Production turns them all on: from_env defaults each to True (compose.yml also sets coordination
    # and owner approvals to true). Directly built configs (tests) leave coordination, approvals and hints off.
    decision_review_enabled: bool = True
    indexed_memory_enabled: bool = True
    background_coordination_enabled: bool = False
    # Owner approvals (plan 2026-11-17): gated Chat/Voice tool calls stop for the owner's approve/deny.
    # Off by default for directly built configs (tests); from_env and the packages turn it on.
    owner_approvals_enabled: bool = False
    genui_enabled: bool = True
    # Network-calling hint: off for directly constructed configs (tests); from_env enables it.
    genui_presentation_hints: bool = False
    # Who answers Link Companion chat: "coordinator" (the Vault coordinator, when coordination is on) or
    # any other value for the Voice Agent's text channel. Env: RESONO_VAULT_LINK_CHAT_RESPONDER.
    link_chat_responder: str = "coordinator"
    # Host directories Vault can see (set by the installer). Empty hides the folders feature.
    device_locations: tuple[DeviceLocation, ...] = ()
    documents_folder: str | None = None

    @classmethod
    def from_env(cls) -> "VaultLocalApiConfig":
        data_root = resolve_vault_data_root()
        # The old local API token protected no route; it is no longer required or created.
        # Existing config/local-api-token files and RESONO_VAULT_LOCAL_API_TOKEN* are ignored.
        token = None
        host = _optional_env("RESONO_VAULT_LOCAL_API_HOST") or "127.0.0.1"
        tls_certificate_file = _optional_env("RESONO_VAULT_LOCAL_API_TLS_CERTIFICATE_FILE")
        tls_private_key_file = _optional_env("RESONO_VAULT_LOCAL_API_TLS_PRIVATE_KEY_FILE")
        if bool(tls_certificate_file) != bool(tls_private_key_file):
            raise RuntimeError("Both Vault local API TLS certificate and private key files are required.")
        if host not in {"127.0.0.1", "::1"} and not tls_certificate_file:
            raise RuntimeError("Vault local API network binding requires TLS.")
        browser_startup_host = _optional_env("RESONO_VAULT_BROWSER_STARTUP_HOST")
        browser_startup_allowed_origins = _origin_tuple_env("RESONO_VAULT_BROWSER_STARTUP_ALLOWED_ORIGINS")
        if browser_startup_host and not browser_startup_allowed_origins:
            raise RuntimeError(
                "RESONO_VAULT_BROWSER_STARTUP_ALLOWED_ORIGINS is required when the browser startup listener is enabled."
            )
        browser_media_enabled = _bool_env("RESONO_VAULT_BROWSER_MEDIA_ENABLED", False)
        browser_startup_port = _int_env("RESONO_VAULT_BROWSER_STARTUP_PORT", 8766)
        browser_media_port = _int_env("RESONO_VAULT_BROWSER_MEDIA_PORT", 8767)
        browser_media_path = _optional_env("RESONO_VAULT_BROWSER_MEDIA_PATH") or "/session-relay/ws"
        if browser_media_enabled and not browser_startup_host:
            raise RuntimeError("RESONO_VAULT_BROWSER_STARTUP_HOST is required when browser media WebSocket is enabled.")
        if browser_media_enabled and browser_media_path != "/session-relay/ws":
            raise RuntimeError("RESONO_VAULT_BROWSER_MEDIA_PATH must be /session-relay/ws.")
        if browser_media_enabled and browser_media_port == browser_startup_port:
            raise RuntimeError("RESONO_VAULT_BROWSER_MEDIA_PORT must differ from RESONO_VAULT_BROWSER_STARTUP_PORT.")
        storage_root = data_root / "storage"
        return cls(
            host=host,
            port=_int_env("RESONO_VAULT_LOCAL_API_PORT", 8765), token=token, data_root=str(data_root),
            storage_status_file=_optional_env("RESONO_VAULT_STORAGE_STATUS_FILE")
            or str(storage_root / "bootstrap-status.json"),
            storage_mount_point=_optional_env("RESONO_VAULT_STORAGE_MOUNT_POINT") or str(data_root / "private"),
            database_url=_optional_env("RESONO_VAULT_DATABASE_URL"),
            database_url_file=_optional_env("RESONO_VAULT_DATABASE_URL_FILE")
            or str(data_root / "config" / "database-url"),
            setup_credential_hash=_optional_env("RESONO_VAULT_SETUP_CREDENTIAL_HASH"),
            setup_credential_hash_file=_optional_env("RESONO_VAULT_SETUP_CREDENTIAL_HASH_FILE")
            or str(data_root / "config" / "setup-credential-hash"),
            session_capability_secret=_optional_env("RESONO_VAULT_SESSION_CAPABILITY_SECRET"),
            session_capability_secret_file=_optional_env("RESONO_VAULT_SESSION_CAPABILITY_SECRET_FILE")
            or str(data_root / "config" / "session-capability-secret"),
            device_identity_key_file=_optional_env("RESONO_VAULT_DEVICE_IDENTITY_KEY_FILE")
            or str(data_root / "keys" / "device-identity-ed25519.pem"),
            max_body_bytes=_int_env("RESONO_VAULT_LOCAL_API_MAX_BODY_BYTES", 134_217_728),
            browser_startup_host=browser_startup_host, browser_startup_port=browser_startup_port,
            browser_startup_allowed_origins=browser_startup_allowed_origins,
            browser_media_enabled=browser_media_enabled, browser_media_port=browser_media_port,
            browser_media_path=browser_media_path,
            session_opaque_relay_ttl_seconds=_bounded_int_env(
                "RESONO_VAULT_SESSION_OPAQUE_RELAY_TTL_SECONDS", 7_200, minimum=600, maximum=7_200
            ),
            web_root=_optional_env("RESONO_VAULT_WEB_ROOT"),
            tls_certificate_file=tls_certificate_file,
            tls_private_key_file=tls_private_key_file,
            google_oauth_client_id=_optional_env("RESONO_VAULT_GOOGLE_OAUTH_CLIENT_ID"),
            google_oauth_client_secret=_optional_env("RESONO_VAULT_GOOGLE_OAUTH_CLIENT_SECRET"),
            plugin_service_url=_optional_env("RESONO_VAULT_PLUGIN_SERVICE_URL")
            or "https://127.0.0.1:8765/plugin-services/v1",
            decision_review_enabled=_bool_env("RESONO_VAULT_DECISION_REVIEW_ENABLED",True),
            indexed_memory_enabled=_bool_env("RESONO_VAULT_INDEXED_MEMORY_ENABLED",True),
            background_coordination_enabled=_bool_env("RESONO_VAULT_BACKGROUND_COORDINATION_ENABLED",True),
            owner_approvals_enabled=_bool_env("RESONO_VAULT_OWNER_APPROVALS_ENABLED",True),
            genui_enabled=_bool_env("RESONO_VAULT_GENUI_ENABLED",True),
            genui_presentation_hints=_bool_env("RESONO_VAULT_GENUI_PRESENTATION_HINTS",True),
            link_chat_responder=_optional_env("RESONO_VAULT_LINK_CHAT_RESPONDER") or "coordinator",
            device_locations=_device_locations_env("RESONO_VAULT_DEVICE_LOCATIONS"),
            documents_folder=_optional_env("RESONO_VAULT_DOCUMENTS_FOLDER"),
        )

    def database_url_value(self) -> str:
        if self.database_url and self.database_url.strip():
            return self.database_url.strip()
        if self.database_url_file:
            try:
                value = Path(self.database_url_file).read_text(encoding="utf-8").strip()
            except OSError:
                value = ""
            if value:
                return value
        raise RuntimeError("RESONO_VAULT_DATABASE_URL or RESONO_VAULT_DATABASE_URL_FILE is required.")

    def setup_credential_hash_value(self) -> str | None:
        if self.setup_credential_hash and self.setup_credential_hash.strip():
            return self.setup_credential_hash.strip()
        if self.setup_credential_hash_file:
            try:
                value = Path(self.setup_credential_hash_file).read_text(encoding="utf-8").strip()
            except OSError:
                return None
            return value or None
        return None

    def session_capability_secret_value(self) -> str | None:
        if self.session_capability_secret and self.session_capability_secret.strip():
            return self.session_capability_secret.strip()
        if not self.session_capability_secret_file:
            return None
        try:
            value = Path(self.session_capability_secret_file).read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value is not None and value.strip() else None


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None or not value.strip() else int(value)


def _bounded_int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    return min(maximum, max(minimum, _int_env(name, default)))


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip().lower() in {"1", "true", "yes", "on"}


def _origin_tuple_env(name: str) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return ()
    origins = tuple(dict.fromkeys(item.strip().rstrip("/") for item in value.split(",") if item.strip()))
    if any(origin == "*" or not _is_http_origin(origin) for origin in origins):
        raise RuntimeError(f"{name} must be a comma-separated list of HTTP(S) origins, not '*'.")
    return origins


def _is_http_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not parsed.path and not parsed.query


_LOCATION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def _device_locations_env(name: str) -> tuple[DeviceLocation, ...]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return ()
    try:
        items = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} must be a JSON list of locations.") from exc
    if not isinstance(items, list):
        raise RuntimeError(f"{name} must be a JSON list of locations.")
    locations: list[DeviceLocation] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError(f"{name} entries must be objects.")
        location_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        path = str(item.get("path") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not _LOCATION_ID.fullmatch(location_id) or location_id in seen:
            raise RuntimeError(f"{name} has a missing, invalid or repeated id: {location_id!r}.")
        if not label or not path.startswith("/") or kind not in LOCATION_KINDS:
            raise RuntimeError(f"{name} entry {location_id!r} needs a label, an absolute path and a known kind.")
        seen.add(location_id)
        locations.append(DeviceLocation(id=location_id, label=label[:64], path=Path(path).resolve(), kind=kind))
    return tuple(locations)
