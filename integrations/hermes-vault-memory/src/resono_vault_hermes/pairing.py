from __future__ import annotations

import hashlib
import argparse
import json
import os
import secrets
import ssl
import time
import webbrowser
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen


def _post(
    base_url: str, path: str, payload: dict[str, object], context: ssl.SSLContext,
    *, credential: str = "",
) -> dict[str, object]:
    headers = {"content-type": "application/json"}
    if credential:
        headers["authorization"] = f"Bearer {credential}"
    request = Request(
        base_url + path, data=json.dumps(payload).encode(), method="POST",
        headers=headers,
    )
    with urlopen(request, timeout=10, context=context) as response:
        return json.loads(response.read().decode())


def _save_env(path: Path, credential: str) -> None:
    key = "RESONO_VAULT_MEMORY_CREDENTIAL"
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith(key + "=")]
    lines.append(f"{key}={credential}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def _remove_credential(path: Path) -> None:
    if not path.exists():
        return
    key = "RESONO_VAULT_MEMORY_CREDENTIAL="
    lines = [line for line in path.read_text().splitlines() if not line.startswith(key)]
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + ("\n" if lines else ""))
    temporary.chmod(0o600)
    temporary.replace(path)


def _env_value(path: Path, key: str, default: str = "") -> str:
    if path.exists():
        prefix = key + "="
        for line in path.read_text().splitlines():
            if line.startswith(prefix):
                return line.removeprefix(prefix).strip()
    return default


def main() -> None:
    parser = argparse.ArgumentParser(description="Pair or disconnect Hermes from Vault Memory")
    parser.add_argument("--disconnect", action="store_true")
    parser.add_argument("--local-only", action="store_true", help="Clear local setup when Vault is unavailable")
    args = parser.parse_args()
    env_path = Path.home() / ".hermes" / ".env"
    base_url = os.getenv("RESONO_VAULT_MEMORY_URL", _env_value(env_path, "RESONO_VAULT_MEMORY_URL", "https://127.0.0.1:8765")).rstrip("/")
    ca_file = os.getenv("RESONO_VAULT_CA_FILE", _env_value(env_path, "RESONO_VAULT_CA_FILE", "")).strip()
    context = ssl.create_default_context(cafile=ca_file or None)
    if args.disconnect:
        credential = os.getenv("RESONO_VAULT_MEMORY_CREDENTIAL", _env_value(env_path, "RESONO_VAULT_MEMORY_CREDENTIAL", "")).strip()
        if credential and not args.local_only:
            _post(base_url, "/external-memory/v1/disconnect", {
                "requestId": secrets.token_hex(16),
            }, context, credential=credential)
        _remove_credential(env_path)
        subprocess.run(["hermes", "memory", "off"], check=True)
        print("Hermes is disconnected from Vault Memory. Built-in memory remains enabled.")
        return
    credential = secrets.token_urlsafe(32)
    poll_token = secrets.token_urlsafe(32)
    started = _post(base_url, "/external-memory/pairing/start", {
        "displayName": "Hermes", "adapterKind": "hermes",
        "grants": ["search", "propose", "correct", "forget"],
        "pollToken": poll_token,
        "runtimeTokenHash": hashlib.sha256(credential.encode()).hexdigest(),
    }, context)
    approval_url = f"{base_url}/?memoryPairing={started['pairingCode']}"
    print(f"Opening Vault to connect Hermes. Pairing code: {started['pairingCode']}")
    webbrowser.open(approval_url)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        result = _post(base_url, "/external-memory/pairing/status", {
            "pairingId": started["pairingId"], "pollToken": poll_token,
        }, context)
        if result.get("status") == "approved":
            _save_env(env_path, credential)
            subprocess.run(
                ["hermes", "config", "set", "memory.provider", "resono-vault"],
                check=True,
            )
            print("Hermes is connected to Vault Memory. Restart Hermes to load it.")
            return
        if result.get("status") == "expired":
            break
        time.sleep(2)
    raise SystemExit("Pairing expired before it was approved.")


if __name__ == "__main__":
    main()
