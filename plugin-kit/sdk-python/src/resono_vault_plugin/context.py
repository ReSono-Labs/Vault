from __future__ import annotations

from base64 import urlsafe_b64decode
from dataclasses import dataclass
import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class VaultServiceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VaultInvocationContext:
    service_url: str
    capability_token: str
    invocation_id: str
    configuration: dict[str, object]

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> "VaultInvocationContext":
        lowered = {key.lower(): value for key, value in headers.items()}
        try:
            encoded = lowered.get("x-vault-configuration", "")
            configuration = json.loads(urlsafe_b64decode(encoded).decode()) if encoded else {}
            if not isinstance(configuration, dict):
                raise ValueError("configuration must be an object")
            return cls(lowered["x-vault-service-url"].rstrip("/"), lowered["x-vault-capability"], lowered["x-vault-invocation-id"], configuration)
        except KeyError as exc:
            raise VaultServiceError(f"Vault invocation header is missing: {exc.args[0]}") from exc


class VaultServiceClient:
    def __init__(self, context: VaultInvocationContext, *, timeout: float = 10.0) -> None:
        self._context = context
        self._timeout = timeout

    def call(self, service: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            f"{self._context.service_url}/{service}",
            data=json.dumps(payload, separators=(",", ":")).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._context.capability_token}",
                "Content-Type": "application/json",
                "X-Vault-Invocation-Id": self._context.invocation_id,
            },
        )
        try:
            ca_file = os.getenv("RESONO_VAULT_CA_FILE")
            tls_context = ssl.create_default_context(cafile=ca_file) if ca_file else None
            with urlopen(request, timeout=self._timeout, context=tls_context) as response:
                value = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VaultServiceError("Vault service request failed.") from exc
        if not isinstance(value, dict):
            raise VaultServiceError("Vault service returned an invalid response.")
        return value

    def search_memory(self, query: str, *, limit: int = 5) -> dict[str, object]:
        return self.call("memory/search", {"query": query, "limit": limit})

    def propose_memory(self, text: str, *, source: str = "plugin") -> dict[str, object]:
        return self.call("memory/propose", {"text": text, "source": source})

    def locale(self) -> dict[str, object]:
        return self.call("context/locale", {})

    def report_activity(self, message: str) -> dict[str, object]:
        return self.call("activity/report", {"message": message})
