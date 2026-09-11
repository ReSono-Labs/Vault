#!/usr/bin/env python3
"""Run Vault behind an authenticated HTTPS tunnel for internet testing."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import test_env

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "internet-test"
DATA_ROOT = RUNTIME / "vault-data"
LOCAL_URL = "https://127.0.0.1:8765"
NGROK_API = "http://127.0.0.1:4040/api/tunnels"
BROWSER_TEST_DATABASE = "resono_vault_browser_test"


def _private_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def _secret_file(name: str, *, bytes_count: int = 32) -> str:
    path = RUNTIME / name
    if not path.exists():
        _private_write(path, secrets.token_urlsafe(bytes_count))
    return path.read_text(encoding="utf-8").strip()


def _request(url: str, *, username: str | None = None, password: str | None = None) -> int:
    request = Request(url)
    if username is not None and password is not None:
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        request.add_header("Authorization", f"Basic {encoded}")
    try:
        context = None
        if url.startswith(LOCAL_URL):
            context = __import__("ssl")._create_unverified_context()
        with urlopen(request, timeout=15, context=context) as response:
            return response.status
    except HTTPError as error:
        return error.code


def _wait_for(url: str, *, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if _request(url) == 200:
                return
        except (OSError, URLError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}")


def _running(name: str, marker: str) -> bool:
    path = RUNTIME / f"{name}.pid"
    if not path.exists():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        return marker in command
    except (OSError, ValueError):
        return False


def _spawn(name: str, command: list[str], environment: dict[str, str], marker: str) -> None:
    if _running(name, marker):
        return
    RUNTIME.mkdir(parents=True, exist_ok=True)
    log = (RUNTIME / f"{name}.log").open("ab")
    process = subprocess.Popen(
        command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _private_write(RUNTIME / f"{name}.pid", str(process.pid))


def _public_url() -> str:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urlopen(NGROK_API, timeout=3) as response:
                tunnels = json.load(response).get("tunnels", [])
            urls = [item.get("public_url", "") for item in tunnels]
            https_urls = [url for url in urls if url.startswith("https://")]
            if https_urls:
                _private_write(RUNTIME / "public-url", https_urls[0])
                return https_urls[0]
        except (OSError, URLError, ValueError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Tunnel did not publish an HTTPS URL; inspect .runtime/internet-test/ngrok.log")


def _browser_database_url() -> str:
    """Provision and return the manual browser-test database.

    This must never share the pytest database: integration fixtures intentionally
    drop their schema during teardown.
    """
    settings = test_env._settings()
    check = test_env._compose(
        "exec", "-T", "postgres", "psql", "-U",
        settings["VAULT_TEST_POSTGRES_USER"], "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{BROWSER_TEST_DATABASE}'",
        check=False,
        capture_output=True,
    )
    if check.returncode != 0:
        raise RuntimeError("Could not inspect the browser-test PostgreSQL database")
    if check.stdout.strip() != "1":
        test_env._compose(
            "exec", "-T", "postgres", "createdb", "-U",
            settings["VAULT_TEST_POSTGRES_USER"], BROWSER_TEST_DATABASE,
        )
    return (
        f"postgresql://{settings['VAULT_TEST_POSTGRES_USER']}:"
        f"{settings['VAULT_TEST_POSTGRES_PASSWORD']}@127.0.0.1:"
        f"{settings['VAULT_TEST_POSTGRES_PORT']}/{BROWSER_TEST_DATABASE}"
    )


def _lan_address() -> str:
    override = os.getenv("RESONO_VAULT_LAN_ADDRESS", "").strip()
    if override:
        return override
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("1.1.1.1", 53))
        return str(probe.getsockname()[0])
    finally:
        probe.close()


def _ensure_lan_certificate(address: str) -> tuple[Path, Path, Path]:
    tls_root = RUNTIME / "tls"
    ca_key = tls_root / "vault-local-ca.key"
    ca_cert = tls_root / "vault-local-ca.crt"
    server_key = tls_root / "vault-lan.key"
    server_cert = tls_root / "vault-lan.crt"
    tls_root.mkdir(parents=True, exist_ok=True)
    if not ca_key.exists() or not ca_cert.exists():
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-nodes",
                        "-keyout", str(ca_key), "-out", str(ca_cert), "-days", "3650",
                        "-subj", "/CN=ReSono Vault Local CA"], check=True, capture_output=True)
    config = tls_root / "server-cert.cnf"
    config.write_text(
        "[req]\ndistinguished_name=dn\nprompt=no\nreq_extensions=ext\n"
        f"[dn]\nCN={address}\n[ext]\nsubjectAltName=IP:{address},IP:127.0.0.1\n"
        "extendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n",
        encoding="utf-8",
    )
    csr = tls_root / "vault-lan.csr"
    subprocess.run(["openssl", "req", "-new", "-newkey", "rsa:3072", "-nodes",
                    "-keyout", str(server_key), "-out", str(csr), "-config", str(config)],
                   check=True, capture_output=True)
    subprocess.run(["openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca_cert),
                    "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(server_cert),
                    "-days", "825", "-sha256", "-extfile", str(config), "-extensions", "ext"],
                   check=True, capture_output=True)
    ca_key.chmod(0o600)
    server_key.chmod(0o600)
    return ca_cert, server_cert, server_key


def start() -> None:
    if subprocess.run(["which", "ngrok"], capture_output=True).returncode:
        raise RuntimeError("ngrok is required for the internet test harness")
    test_env._up()
    subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    token = _secret_file("local-api-token")
    setup_credential = _secret_file("setup-credential")
    ingress_password = _secret_file("ingress-password", bytes_count=24)
    ingress_username = "vault-test"
    lan_address = _lan_address()
    ca_cert, server_cert, server_key = _ensure_lan_certificate(lan_address)
    shutil.copyfile(ca_cert, ROOT / "frontend" / "dist" / "vault-local-ca.crt")
    _private_write(RUNTIME / "ingress-username", ingress_username)
    _private_write(RUNTIME / "setup-credential-hash", hashlib.sha256(setup_credential.encode()).hexdigest())
    policy = {"on_http_request": [{"actions": [{"type": "basic-auth", "config": {
        "credentials": [f"{ingress_username}:{ingress_password}"]
    }}]}]}
    _private_write(RUNTIME / "traffic-policy.json", json.dumps(policy))

    environment = os.environ.copy()
    environment.update({
        "RESONO_VAULT_DATA_ROOT": str(DATA_ROOT),
        "RESONO_VAULT_DATABASE_URL": _browser_database_url(),
        "RESONO_VAULT_LOCAL_API_HOST": "0.0.0.0",
        "RESONO_VAULT_LOCAL_API_PORT": "8765",
        "RESONO_VAULT_LOCAL_API_TOKEN": token,
        "RESONO_VAULT_SETUP_CREDENTIAL_HASH_FILE": str(RUNTIME / "setup-credential-hash"),
        "RESONO_VAULT_WEB_ROOT": str(ROOT / "frontend" / "dist"),
        "RESONO_VAULT_LOCAL_API_TLS_CERTIFICATE_FILE": str(server_cert),
        "RESONO_VAULT_LOCAL_API_TLS_PRIVATE_KEY_FILE": str(server_key),
    })
    _spawn("vault", ["uv", "run", "--frozen", "python", "-m", "app.vault_runtime.local_api"], environment, "app.vault_runtime.local_api")
    _wait_for(f"{LOCAL_URL}/health")
    _spawn(
        "ngrok",
        ["ngrok", "http", f"https://{lan_address}:8765", "--upstream-tls-verify",
         "--upstream-tls-verify-cas", str(ca_cert), "--traffic-policy-file", str(RUNTIME / "traffic-policy.json"),
         "--log", "stdout", "--log-format", "json"],
        environment, "ngrok http",
    )
    url = _public_url()
    print(f"Vault internet test URL: {url}")
    print(f"Vault LAN URL: https://{lan_address}:8765")
    print(f"Ingress username: {RUNTIME / 'ingress-username'}")
    print(f"Ingress password: {RUNTIME / 'ingress-password'}")
    print(f"Initial owner setup credential: {RUNTIME / 'setup-credential'}")
    print("Secrets are local, ignored by Git, and mode 0600.")


def check() -> None:
    url_path = RUNTIME / "public-url"
    if not url_path.exists():
        raise RuntimeError("Internet test is not started")
    url = url_path.read_text(encoding="utf-8").strip()
    username = (RUNTIME / "ingress-username").read_text(encoding="utf-8").strip()
    password = (RUNTIME / "ingress-password").read_text(encoding="utf-8").strip()
    results = {
        "local Vault health": _request(f"{LOCAL_URL}/health") == 200,
        "public edge rejects anonymous request": _request(f"{url}/health") == 401,
        "public authenticated Vault health": _request(f"{url}/health", username=username, password=password) == 200,
        "outbound DNS/TLS/provider route": _request("https://api.openai.com/v1/models") in {401, 403, 429},
    }
    for label, passed in results.items():
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
    if not all(results.values()):
        raise RuntimeError("One or more internet connectivity checks failed")


def status() -> None:
    print(f"Vault: {'running' if _running('vault', 'app.vault_runtime.local_api') else 'stopped'}")
    print(f"Tunnel: {'running' if _running('ngrok', 'ngrok http') else 'stopped'}")
    if (RUNTIME / "public-url").exists():
        print(f"Public URL: {(RUNTIME / 'public-url').read_text(encoding='utf-8').strip()}")
    print(f"Credentials directory: {RUNTIME}")


def stop() -> None:
    for name, marker in (("ngrok", "ngrok http"), ("vault", "app.vault_runtime.local_api")):
        path = RUNTIME / f"{name}.pid"
        if _running(name, marker):
            pid = int(path.read_text(encoding="utf-8").strip())
            os.killpg(pid, signal.SIGTERM)
            print(f"Stopped {name} (PID {pid})")
        path.unlink(missing_ok=True)
    (RUNTIME / "public-url").unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "status", "check", "stop"))
    action = parser.parse_args().action
    {"start": start, "status": status, "check": check, "stop": stop}[action]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
