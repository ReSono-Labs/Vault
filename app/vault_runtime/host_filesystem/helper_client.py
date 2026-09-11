from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any


class HostFilesystemHelperError(RuntimeError):
    code = "host_filesystem_helper_error"


class HostFilesystemHelperClient:
    def __init__(self, *, base_url: str, credential: str, ca_file: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        if base_url.startswith("http://"):
            self._context = ssl._create_unverified_context()  # noqa: SLF001
        else:
            self._context = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()

    def _request(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._base_url + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self._credential}",
                "Content-Type": "application/json",
            },
        )
        try:
            if self._base_url.startswith("http://"):
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            with urllib.request.urlopen(request, timeout=timeout, context=self._context) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                message = parsed.get("error", {}).get("message", detail)
            except json.JSONDecodeError:
                message = detail or str(exc)
            raise HostFilesystemHelperError(message) from exc
        except urllib.error.URLError as exc:
            raise HostFilesystemHelperError(
                "The host filesystem helper is not reachable. Install and start it, then try again."
            ) from exc

    def health(self) -> dict[str, Any]:
        return self._request(method="GET", path="/v1/health")

    def pick_mount(self) -> dict[str, Any]:
        return self._request(method="POST", path="/v1/mounts/pick", payload={})

    def register_mount(
        self,
        *,
        mount_id: str,
        host_path: str,
        mount_name: str,
        permission: str,
    ) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/mounts/register",
            payload={
                "mountId": mount_id,
                "hostPath": host_path,
                "mountName": mount_name,
                "permission": permission,
            },
        )

    def revoke_mount(self, *, mount_id: str) -> dict[str, Any]:
        return self._request(method="POST", path="/v1/mounts/revoke", payload={"mountId": mount_id})

    def list_directory(self, *, mount_id: str, directory: str = "") -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/list",
            payload={"mountId": mount_id, "directory": directory},
        )

    def read_file(self, *, mount_id: str, file_key: str) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/read",
            payload={"mountId": mount_id, "fileKey": file_key},
        )

    def write_file(self, *, mount_id: str, file_key: str, content_base64: str, mime_type: str) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/write",
            payload={
                "mountId": mount_id,
                "fileKey": file_key,
                "contentBase64": content_base64,
                "mimeType": mime_type,
            },
        )

    def create_directory(self, *, mount_id: str, directory: str) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/directories",
            payload={"mountId": mount_id, "directory": directory},
        )

    def move_path(self, *, mount_id: str, source_path: str, destination_path: str) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/move",
            payload={
                "mountId": mount_id,
                "sourcePath": source_path,
                "destinationPath": destination_path,
            },
        )

    def delete_path(self, *, mount_id: str, path: str, recursive: bool) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/delete",
            payload={"mountId": mount_id, "path": path, "recursive": recursive},
        )

    def upload_files(
        self,
        *,
        mount_id: str,
        directory: str,
        files: list[dict[str, str]],
    ) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/upload",
            payload={"mountId": mount_id, "directory": directory, "files": files},
        )
