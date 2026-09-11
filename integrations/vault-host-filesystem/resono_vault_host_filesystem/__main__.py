#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import ssl
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_PORT = 8767
STATE_DIR = Path.home() / ".local" / "share" / "resono-vault-host-filesystem"


def _post(base_url: str, path: str, payload: dict[str, object], *, context: ssl.SSLContext | None = None) -> dict[str, object]:
    request = Request(
        base_url + path,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"content-type": "application/json"},
    )
    with urlopen(request, timeout=15, context=context) as response:
        return json.loads(response.read().decode())


def _save_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    preserved = []
    keys = set(values)
    for line in lines:
        if not any(line.startswith(f"{key}=") for key in keys):
            preserved.append(line)
    for key, value in values.items():
        preserved.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(preserved) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def _load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _pick_folder() -> str:
    if os.environ.get("DISPLAY") or sys.platform == "darwin":
        for command in (
            ["zenity", "--file-selection", "--directory", "--title=Choose a folder to link"],
            ["kdialog", "--getexistingdirectory", str(Path.home())],
        ):
            try:
                completed = subprocess.run(command, check=True, capture_output=True, text=True)
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
            selected = completed.stdout.strip()
            if selected:
                return selected
    raise RuntimeError("No folder picker is available. Run the helper on a desktop session.")


def _normalize_relative(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/").strip("/")
    if not raw:
        return ""
    parts = PurePosixPath(raw).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Unsafe path.")
    return PurePosixPath(raw).as_posix()


class MountStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text(json.dumps({"mounts": {}, "pending": {}}, indent=2), encoding="utf-8")

    def _load(self) -> dict[str, Any]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, payload: dict[str, Any]) -> None:
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self._path)

    def pick(self) -> dict[str, str]:
        host_path = str(Path(_pick_folder()).resolve())
        mount_id = secrets.token_hex(16)
        suggested_name = Path(host_path).name or "Folder"
        payload = self._load()
        payload.setdefault("pending", {})[mount_id] = {
            "hostPath": host_path,
            "suggestedName": suggested_name,
        }
        self._save(payload)
        return {
            "mountId": mount_id,
            "hostPath": host_path,
            "hostPathLabel": host_path,
            "suggestedName": suggested_name,
        }

    def register(self, *, mount_id: str, host_path: str, mount_name: str, permission: str) -> None:
        resolved = str(Path(host_path).resolve())
        if not Path(resolved).is_dir():
            raise ValueError("Host path must be an existing folder.")
        payload = self._load()
        pending = payload.setdefault("pending", {}).pop(mount_id, None)
        if pending and str(pending.get("hostPath")) != resolved:
            raise ValueError("Picked folder does not match the pending selection.")
        payload.setdefault("mounts", {})[mount_id] = {
            "hostPath": resolved,
            "mountName": mount_name,
            "permission": permission,
        }
        self._save(payload)

    def revoke(self, *, mount_id: str) -> None:
        payload = self._load()
        payload.setdefault("mounts", {}).pop(mount_id, None)
        payload.setdefault("pending", {}).pop(mount_id, None)
        self._save(payload)

    def get(self, mount_id: str) -> dict[str, Any]:
        payload = self._load()
        mount = payload.get("mounts", {}).get(mount_id)
        if mount is None:
            raise KeyError(mount_id)
        return mount

    def resolve(self, *, mount_id: str, relative: str) -> Path:
        mount = self.get(mount_id)
        root = Path(str(mount["hostPath"])).resolve()
        if root.is_symlink():
            raise ValueError("Linked folder root cannot be a symlink.")
        normalized = _normalize_relative(relative)
        candidate = root if not normalized else root.joinpath(*PurePosixPath(normalized).parts)
        current = root
        for part in PurePosixPath(normalized).parts if normalized else ():
            current = current / part
            if current.is_symlink():
                raise ValueError("Linked path cannot contain symlinks.")
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise ValueError("Linked path escapes the authorized folder.")
        return resolved

    def require_write(self, mount_id: str) -> None:
        if self.get(mount_id).get("permission") != "write":
            raise PermissionError("Write access is required.")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _error(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    _json_response(handler, status, {"error": {"message": message}})


class HelperHandler(BaseHTTPRequestHandler):
    store: MountStore
    credential: str

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return secrets.compare_digest(header.removeprefix("Bearer ").strip(), self.credential)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/health":
            _error(self, 404, "Not found.")
            return
        _json_response(self, 200, {"status": "ok"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            _error(self, 403, "Authorization required.")
            return
        try:
            payload = self._read_json()
            if self.path == "/v1/mounts/pick":
                _json_response(self, 200, self.store.pick())
                return
            if self.path == "/v1/mounts/register":
                self.store.register(
                    mount_id=str(payload["mountId"]),
                    host_path=str(payload["hostPath"]),
                    mount_name=str(payload["mountName"]),
                    permission=str(payload["permission"]),
                )
                _json_response(self, 200, {"status": "registered"})
                return
            if self.path == "/v1/mounts/revoke":
                self.store.revoke(mount_id=str(payload["mountId"]))
                _json_response(self, 200, {"status": "revoked"})
                return
            if self.path == "/v1/list":
                self._handle_list(payload)
                return
            if self.path == "/v1/read":
                self._handle_read(payload)
                return
            if self.path == "/v1/write":
                self._handle_write(payload)
                return
            if self.path == "/v1/directories":
                self._handle_directory(payload)
                return
            if self.path == "/v1/move":
                self._handle_move(payload)
                return
            if self.path == "/v1/delete":
                self._handle_delete(payload)
                return
            if self.path == "/v1/upload":
                self._handle_upload(payload)
                return
            _error(self, 404, "Not found.")
        except (KeyError, ValueError, PermissionError) as exc:
            _error(self, 400, str(exc))
        except FileNotFoundError as exc:
            _error(self, 404, str(exc))

    def _handle_list(self, payload: dict[str, Any]) -> None:
        mount_id = str(payload["mountId"])
        directory = _normalize_relative(str(payload.get("directory", "")))
        target = self.store.resolve(mount_id=mount_id, relative=directory)
        if not target.is_dir():
            raise FileNotFoundError("Directory was not found.")
        entries = []
        for child in sorted(target.iterdir(), key=lambda item: item.name.casefold()):
            if child.name.startswith("."):
                continue
            stat = child.stat()
            if child.is_dir():
                entries.append(
                    {
                        "kind": "directory",
                        "name": child.name,
                        "path": "/".join(part for part in (directory, child.name) if part),
                        "childCount": sum(1 for _ in child.iterdir()),
                    }
                )
            else:
                mime_type, _ = mimetypes.guess_type(child.name)
                entries.append(
                    {
                        "kind": "file",
                        "name": child.name,
                        "path": "/".join(part for part in (directory, child.name) if part),
                        "sizeBytes": stat.st_size,
                        "mimeType": mime_type or "application/octet-stream",
                        "editable": (mime_type or "").startswith("text/") or child.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml"},
                    }
                )
        parent = "/".join(directory.split("/")[:-1]) if directory else None
        _json_response(
            self,
            200,
            {
                "currentDirectory": directory,
                "parentDirectory": parent,
                "entries": entries,
            },
        )

    def _handle_read(self, payload: dict[str, Any]) -> None:
        mount_id = str(payload["mountId"])
        file_key = _normalize_relative(str(payload["fileKey"]))
        target = self.store.resolve(mount_id=mount_id, relative=file_key)
        if not target.is_file():
            raise FileNotFoundError("File was not found.")
        content = target.read_bytes()
        mime_type, _ = mimetypes.guess_type(target.name)
        text = content.decode("utf-8") if (mime_type or "").startswith("text/") or target.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml"} else ""
        _json_response(
            self,
            200,
            {
                "fileKey": file_key,
                "filename": target.name,
                "contentMarkdown": text,
                "contentBase64": base64.b64encode(content).decode("ascii"),
                "sizeBytes": len(content),
                "mimeType": mime_type or "application/octet-stream",
                "editable": bool(text) or (mime_type or "").startswith("text/"),
            },
        )

    def _handle_write(self, payload: dict[str, Any]) -> None:
        mount_id = str(payload["mountId"])
        self.store.require_write(mount_id)
        file_key = _normalize_relative(str(payload["fileKey"]))
        target = self.store.resolve(mount_id=mount_id, relative=file_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = base64.b64decode(str(payload["contentBase64"]).encode("ascii"))
        target.write_bytes(content)
        _json_response(self, 200, {"status": "completed", "path": file_key})

    def _handle_directory(self, payload: dict[str, Any]) -> None:
        mount_id = str(payload["mountId"])
        self.store.require_write(mount_id)
        directory = _normalize_relative(str(payload["directory"]))
        target = self.store.resolve(mount_id=mount_id, relative=directory)
        target.mkdir(parents=True, exist_ok=False)
        _json_response(self, 200, {"status": "completed", "path": directory})

    def _handle_move(self, payload: dict[str, Any]) -> None:
        mount_id = str(payload["mountId"])
        self.store.require_write(mount_id)
        source = self.store.resolve(mount_id=mount_id, relative=_normalize_relative(str(payload["sourcePath"])))
        destination = self.store.resolve(mount_id=mount_id, relative=_normalize_relative(str(payload["destinationPath"])))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        _json_response(self, 200, {"status": "completed"})

    def _handle_delete(self, payload: dict[str, Any]) -> None:
        mount_id = str(payload["mountId"])
        self.store.require_write(mount_id)
        target = self.store.resolve(mount_id=mount_id, relative=_normalize_relative(str(payload["path"])))
        recursive = bool(payload.get("recursive"))
        if target.is_dir():
            if recursive:
                shutil.rmtree(target)
            else:
                target.rmdir()
        else:
            target.unlink()
        _json_response(self, 200, {"status": "completed"})

    def _handle_upload(self, payload: dict[str, Any]) -> None:
        mount_id = str(payload["mountId"])
        self.store.require_write(mount_id)
        directory = _normalize_relative(str(payload.get("directory", "")))
        uploaded = []
        for item in payload.get("files", []):
            filename = Path(str(item["filename"])).name
            relative = "/".join(part for part in (directory, filename) if part)
            target = self.store.resolve(mount_id=mount_id, relative=relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(str(item["contentBase64"]).encode("ascii")))
            uploaded.append(relative)
        _json_response(self, 200, {"status": "completed", "paths": uploaded, "destinationPath": uploaded[0] if len(uploaded) == 1 else None})


def run_server(*, port: int, credential: str, state_dir: Path) -> None:
    store = MountStore(state_dir / "mounts.json")
    HelperHandler.store = store
    HelperHandler.credential = credential
    server = ThreadingHTTPServer(("127.0.0.1", port), HelperHandler)
    print(f"ReSono host filesystem helper listening on http://127.0.0.1:{port}")
    server.serve_forever()


def pair_helper(*, base_url: str, ca_file: str) -> None:
    env_path = STATE_DIR / "helper.env"
    credential = secrets.token_urlsafe(32)
    poll_token = secrets.token_urlsafe(32)
    context = ssl.create_default_context(cafile=ca_file or None)
    started = _post(
        base_url,
        "/host-filesystem/pairing/start",
        {
            "displayName": "Host filesystem helper",
            "adapterKind": "host-helper",
            "pollToken": poll_token,
            "runtimeTokenHash": hashlib.sha256(credential.encode()).hexdigest(),
            "outboundCredential": credential,
        },
        context=context,
    )
    approval_url = f"{base_url}/?hostFilesystemPairing={started['pairingCode']}"
    print(f"Opening Vault to connect the host helper. Pairing code: {started['pairingCode']}")
    webbrowser.open(approval_url)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        result = _post(
            base_url,
            "/host-filesystem/pairing/status",
            {"pairingId": started["pairingId"], "pollToken": poll_token},
            context=context,
        )
        if result.get("status") == "approved":
            _save_env(
                env_path,
                {
                    "RESONO_HOST_HELPER_CREDENTIAL": credential,
                    "RESONO_VAULT_URL": base_url,
                    "RESONO_VAULT_CA_FILE": ca_file,
                    "RESONO_HOST_HELPER_PORT": str(DEFAULT_PORT),
                },
            )
            print("Host filesystem helper paired. Start it with: python3 -m resono_vault_host_filesystem serve")
            return
        if result.get("status") == "expired":
            break
        time.sleep(2)
    raise SystemExit("Pairing expired before it was approved.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ReSono Vault host filesystem helper")
    subparsers = parser.add_subparsers(dest="command", required=True)
    pair_parser = subparsers.add_parser("pair", help="Pair this helper with Vault")
    pair_parser.add_argument("--vault-url", default=os.getenv("RESONO_VAULT_URL", "https://127.0.0.1:8765"))
    pair_parser.add_argument("--ca-file", default=os.getenv("RESONO_VAULT_CA_FILE", ""))
    serve_parser = subparsers.add_parser("serve", help="Run the helper service")
    serve_parser.add_argument("--port", type=int, default=int(os.getenv("RESONO_HOST_HELPER_PORT", DEFAULT_PORT)))
    args = parser.parse_args()
    if args.command == "pair":
        pair_helper(base_url=args.vault_url.rstrip("/"), ca_file=args.ca_file)
        return
    env = _load_env(STATE_DIR / "helper.env")
    credential = env.get("RESONO_HOST_HELPER_CREDENTIAL", "").strip()
    if not credential:
        raise SystemExit("Helper is not paired yet. Run: python3 -m resono_vault_host_filesystem pair")
    run_server(port=args.port, credential=credential, state_dir=STATE_DIR)


if __name__ == "__main__":
    main()
