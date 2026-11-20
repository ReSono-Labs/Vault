"""Invocation-bound Vault services for managed MCP plugin connections."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import time

from app.vault_runtime.extensions.repository import ExtensionRepository
from app.vault_runtime.extensions.secrets import LocalMasterKey
from app.vault_runtime.memory.pipeline import FinalizeResult
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.service import MemoryService


class PluginCapabilityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PluginCapability:
    plugin_id: str
    user_id: str
    workspace_id: str
    invocation_id: str
    services: frozenset[str]


class PluginVaultServices:
    def __init__(
        self, *, repository: ExtensionRepository, key: LocalMasterKey,
        memories: MemoryRepository, memory_service: MemoryService,
        finalize: Callable[[str, str, str], FinalizeResult], service_url: str,
    ) -> None:
        self._repository = repository
        self._key = key
        self._memories = memories
        self._memory_service = memory_service
        self._finalize = finalize
        self.service_url = service_url.rstrip("/")

    def issue_for_connection(self, *, connection, user_id: str, workspace_id: str, invocation_id: str) -> str | None:
        if invocation_id.startswith("discover:"):
            return None
        plugin_id = connection.configuration.get("companionPluginId")
        if not isinstance(plugin_id, str):
            plugin_id = connection.configuration.get("managedByPluginId")
        if not isinstance(plugin_id, str):
            return None
        plugin = self._repository.by_id(
            actor_user_id=user_id, workspace_id=workspace_id,
            extension_id=plugin_id,
        )
        manifest = plugin.configuration.get("vaultManifest")
        services = manifest.get("services", []) if isinstance(manifest, dict) else []
        if not isinstance(services, list) or not services:
            return None
        now = int(time.time())
        payload = {
            "v": 1, "plugin": plugin_id, "user": user_id, "workspace": workspace_id,
            "invocation": invocation_id, "services": services, "iat": now, "exp": now + 300,
        }
        encoded = urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).rstrip(b"=")
        signature = urlsafe_b64encode(hmac.new(self._key.load_or_create(), encoded, sha256).digest()).rstrip(b"=")
        return f"{encoded.decode()}.{signature.decode()}"

    def configuration_for_connection(self, *, connection, user_id: str, workspace_id: str) -> str | None:
        if connection.configuration.get("packageType") == "hosted":
            settings = connection.configuration.get("settings", {})
            if not isinstance(settings, dict) or not settings:
                return None
            return urlsafe_b64encode(json.dumps(settings, separators=(",", ":")).encode()).decode()
        plugin_id = connection.configuration.get("companionPluginId")
        if not isinstance(plugin_id, str):
            plugin_id = connection.configuration.get("managedByPluginId")
        if not isinstance(plugin_id, str):
            return None
        plugin = self._repository.by_id(
            actor_user_id=user_id, workspace_id=workspace_id, extension_id=plugin_id,
        )
        settings = plugin.configuration.get("settings", {})
        if not isinstance(settings, dict):
            return None
        return urlsafe_b64encode(json.dumps(settings, separators=(",", ":")).encode()).decode()

    def authorize(self, token: str, *, invocation_id: str, service: str) -> PluginCapability:
        try:
            encoded_text, signature_text = token.split(".", 1)
            encoded = encoded_text.encode()
            signature = _decode(signature_text)
            expected = hmac.new(self._key.load_or_create(), encoded, sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise PluginCapabilityError("Plugin capability is invalid")
            value = json.loads(_decode(encoded_text))
        except PluginCapabilityError:
            raise
        except Exception as exc:
            raise PluginCapabilityError("Plugin capability is invalid") from exc
        if not isinstance(value, dict) or value.get("v") != 1 or int(value.get("exp", 0)) < int(time.time()):
            raise PluginCapabilityError("Plugin capability has expired")
        if value.get("invocation") != invocation_id or service not in value.get("services", []):
            raise PluginCapabilityError("Plugin capability does not allow this request")
        plugin = self._repository.by_id(
            actor_user_id=str(value["user"]), workspace_id=str(value["workspace"]),
            extension_id=str(value["plugin"]),
        )
        if plugin.state.value != "enabled":
            raise PluginCapabilityError("Plugin is turned off")
        manifest = plugin.configuration.get("vaultManifest")
        current = manifest.get("services", []) if isinstance(manifest, dict) else []
        if service not in current:
            raise PluginCapabilityError("Plugin service access was removed")
        return PluginCapability(
            plugin.extension_id, str(value["user"]), str(value["workspace"]),
            invocation_id, frozenset(str(item) for item in value["services"]),
        )

    def call(self, *, token: str, invocation_id: str, service: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        capability = self.authorize(token, invocation_id=invocation_id, service=service)
        if service == "memory.search":
            query = payload.get("query")
            limit = payload.get("limit", 5)
            if not isinstance(query, str) or not query.strip() or len(query) > 1024:
                raise ValueError("query must contain 1 to 1024 characters")
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 25:
                raise ValueError("limit must be between 1 and 25")
            matches = self._memory_service.search(
                user_id=capability.user_id, workspace_id=capability.workspace_id,
                query=query.strip(), limit=limit,
            )
            return 200, {"items": [{
                "memoryId": item.memory.memory_id, "content": item.memory.content_text,
                "domain": item.memory.domain, "type": item.memory.memory_type,
                "confidence": item.memory.confidence, "score": item.score,
                "matchMethods": list(item.match_methods),
            } for item in matches]}
        if service == "memory.propose":
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 4096:
                raise ValueError("text must contain 1 to 4096 characters")
            session_id = f"plugin:{capability.plugin_id}:{capability.invocation_id}"
            self._memories.append_transcript(
                user_id=capability.user_id, workspace_id=capability.workspace_id,
                voice_session_id=session_id, entry_index=0, role="tool",
                event_type="plugin_memory_proposal", text_content=text.strip(),
                metadata={"pluginId": capability.plugin_id, "invocationId": capability.invocation_id},
            )
            result = self._finalize(capability.user_id, capability.workspace_id, session_id)
            return 202, {"status": "reviewed", "memoryCount": result.memory_count,
                         "alreadyCompleted": result.already_completed}
        if service == "context.locale":
            return 200, {"locale": "en-US", "timeZone": time.tzname[0] or "UTC"}
        if service == "activity.report":
            message = payload.get("message")
            if not isinstance(message, str) or not message.strip() or len(message) > 500:
                raise ValueError("message must contain 1 to 500 characters")
            self._repository.record_plugin_activity(
                actor_user_id=capability.user_id, workspace_id=capability.workspace_id,
                plugin_id=capability.plugin_id, message=message.strip(),
            )
            return 202, {"status": "recorded"}
        raise PluginCapabilityError("Plugin service is unavailable")


def _decode(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))
