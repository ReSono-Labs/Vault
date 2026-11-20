#!/usr/bin/env python3
"""Build and operate the production Vault Docker package."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
import shutil
import socket
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yml"
BACKUP_ROOT = ROOT / ".runtime" / "package-backups"
PACKAGE_ENV = ROOT / ".runtime" / "production-package.env"
FOLDERS_FILE = ROOT / ".runtime" / "compose.folders.yml"
FOLDERS_SCRIPT = ROOT / "packaging" / "docker-release" / "folders.sh"
MIGRATIONS = ROOT / "app" / "vault_runtime" / "migrations"
LOCAL_EMBEDDINGS = ROOT / "packaging" / "local-embeddings"
STAGE_LOCAL_EMBEDDINGS = ROOT / "scripts" / "stage_local_embeddings.py"
EMBEDDING_MODEL = "embeddinggemma:300m"
EMBEDDING_MANIFEST = Path("manifests/registry.ollama.ai/library/embeddinggemma/300m")


def _compose(*arguments: str, check: bool = True, capture: bool = False, text: bool = True):
    command = ["docker", "compose"]
    if PACKAGE_ENV.is_file():
        command.extend(("--env-file", str(PACKAGE_ENV)))
    command.extend(("-f", str(COMPOSE)))
    if FOLDERS_FILE.is_file():
        command.extend(("-f", str(FOLDERS_FILE)))
    command.extend(arguments)
    return subprocess.run(
        command,
        cwd=ROOT, check=check, capture_output=capture, text=text,
    )


def _configure(*, lan: bool) -> str:
    address = _lan_address() if lan else "127.0.0.1"
    PACKAGE_ENV.parent.mkdir(parents=True, exist_ok=True)
    PACKAGE_ENV.write_text(
        "VAULT_BIND_ADDRESS=" + ("0.0.0.0" if lan else "127.0.0.1") + "\n"
        f"VAULT_TLS_HOSTS=localhost,127.0.0.1{',' + address if lan else ''}\n"
        "VAULT_PORT=8765\n",
        encoding="utf-8",
    )
    PACKAGE_ENV.chmod(0o600)
    return address


def _lan_address() -> str:
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        connection.connect(("192.0.2.1", 9))
        return str(connection.getsockname()[0])
    finally:
        connection.close()


def _configure_folders() -> None:
    """Make the home folder and drives visible to Vault. Nothing is used until access is given."""
    FOLDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["sh", str(FOLDERS_SCRIPT), "compose", str(FOLDERS_FILE), "link_bridge"], check=True)


def _ollama_models() -> Path:
    configured = os.environ.get("OLLAMA_MODELS")
    candidates = [Path(configured)] if configured else [
        Path.home() / ".ollama" / "models",
        Path("/usr/share/ollama/.ollama/models"),
    ]
    return next((path for path in candidates if (path / EMBEDDING_MANIFEST).is_file()), candidates[0])


def stage_local_embeddings() -> None:
    """The image build needs packaging/local-embeddings; stage it from the local Ollama when it is missing."""
    if (LOCAL_EMBEDDINGS / "SHA256SUMS").is_file():
        return
    ollama = shutil.which("ollama")
    if ollama is None:
        raise SystemExit(
            "packaging/local-embeddings is missing and Ollama is not installed. Install Ollama "
            "(https://ollama.com/download), then run ./vault-package install again."
        )
    models = _ollama_models()
    if not (models / EMBEDDING_MANIFEST).is_file():
        print(f"Pulling the {EMBEDDING_MODEL} embedding model with Ollama.")
        subprocess.run([ollama, "pull", EMBEDDING_MODEL], check=True)
        models = _ollama_models()
    runtime = Path(ollama).resolve().parents[1]
    print(f"Staging packaging/local-embeddings from {runtime} and {models}.")
    subprocess.run(
        [sys.executable, str(STAGE_LOCAL_EMBEDDINGS), "--models", str(models), "--runtime", str(runtime)],
        cwd=ROOT, check=True,
    )


def install(*, lan: bool = False) -> None:
    stage_local_embeddings()
    address = _configure(lan=lan)
    _configure_folders()
    _compose("up", "-d", "--build", "--wait")
    print(f"Vault package is healthy at https://{address}:8765")
    print("Run `./vault-package setup` to display the one-time setup credential.")


def start() -> None:
    _configure_folders()
    _compose("up", "-d", "--wait")


def status() -> None:
    _compose("ps")


def logs() -> None:
    _compose("logs", "--tail", "200", "vault", "link_bridge", "postgres")


def setup() -> None:
    result = _compose("exec", "-T", "vault", "python", "-m", "app.vault_runtime.package_runtime", "show-setup", capture=True)
    credential = result.stdout.strip()
    address = "127.0.0.1"
    if PACKAGE_ENV.is_file():
        settings = dict(
            line.split("=", 1)
            for line in PACKAGE_ENV.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        )
        if settings.get("VAULT_BIND_ADDRESS") == "0.0.0.0":
            address = _lan_address()
    setup_url = (
        f"https://{address}:8765/identity/setup/start"
        f"?credential={quote(credential, safe='')}"
    )
    print("Open this one-time local setup link:")
    print(setup_url)


def stop() -> None:
    _compose("stop")


def latest_schema_version() -> int:
    """Newest migration this code ships (file names NNNN_name.py)."""
    return max((int(path.name[:4]) for path in MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.py")), default=0)


def _schema_version() -> int:
    """Newest migration applied to the running package database (0 before migrations existed)."""
    def query(sql: str) -> str:
        return _compose("exec", "-T", "postgres", "psql", "-U", "vault_runtime", "-d", "vault",
                        "-Atc", sql, capture=True).stdout.strip()
    if query("SELECT to_regclass('vault_private.schema_migrations') IS NOT NULL") != "t":
        return 0
    return int(query("SELECT coalesce(max(version), 0) FROM vault_private.schema_migrations"))


def backup() -> None:
    _compose("up", "-d", "--wait")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = (BACKUP_ROOT / stamp).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    database = _compose(
        "exec", "-T", "postgres", "pg_dump", "-U", "vault_runtime", "-d", "vault",
        "--format=custom", capture=True, text=False,
    ).stdout
    database_path = destination / "vault.dump"
    database_path.write_bytes(database)
    subprocess.run([
        "docker", "run", "--rm",
        "-v", "resono-vault-data:/source:ro",
        "-v", f"{destination}:/backup",
        "alpine:3.21", "tar", "czf", "/backup/vault-data.tar.gz",
        "--exclude=config/database-url", "--exclude=config/local-api-token",
        "-C", "/source", "keys", "private", "extensions", "config",
    ], check=True)
    files = {
        name: sha256((destination / name).read_bytes()).hexdigest()
        for name in ("vault.dump", "vault-data.tar.gz")
    }
    manifest = {
        "format": 1, "createdAt": datetime.now(UTC).isoformat(), "sha256": files,
        "schemaVersion": _schema_version(),
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(destination)


def restore(source: str, confirmation: str) -> None:
    if confirmation != "RESTORE VAULT BACKUP":
        raise SystemExit("Restore requires --confirm 'RESTORE VAULT BACKUP'.")
    backup_root = Path(source).expanduser().resolve()
    manifest_path = backup_root / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("Backup manifest is unavailable.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("sha256") if isinstance(manifest, dict) else None
    if not isinstance(expected, dict):
        raise SystemExit("Backup manifest is invalid.")
    for name in ("vault.dump", "vault-data.tar.gz"):
        path = backup_root / name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected.get(name):
            raise SystemExit(f"Backup artifact failed verification: {name}")
    schema_version = manifest.get("schemaVersion", 0)  # backups from before migrations: 0
    if type(schema_version) is not int or schema_version < 0:
        raise SystemExit("Backup manifest is invalid.")
    if schema_version > latest_schema_version():
        raise SystemExit(f"Backup has schema version {schema_version}, newer than this Vault "
                         f"({latest_schema_version()}). Restore it with the Vault version that made it.")
    _compose("stop", "vault")
    subprocess.run([
        "docker", "run", "--rm",
        "-v", "resono-vault-data:/target",
        "-v", f"{backup_root}:/backup:ro",
        "alpine:3.21", "sh", "-ec",
        "rm -rf /target/keys /target/private /target/extensions "
        "/target/config/setup-credential /target/config/setup-credential-hash "
        "/target/config/session-capability-secret; "
        "tar xzf /backup/vault-data.tar.gz -C /target",
    ], check=True)
    database = (backup_root / "vault.dump").read_bytes()
    # Same compose files as every other command (env file and folders override included).
    command = ["docker", "compose"]
    if PACKAGE_ENV.is_file():
        command.extend(("--env-file", str(PACKAGE_ENV)))
    command.extend(("-f", str(COMPOSE)))
    if FOLDERS_FILE.is_file():
        command.extend(("-f", str(FOLDERS_FILE)))
    subprocess.run([
        *command, "exec", "-T", "postgres",
        "pg_restore", "-U", "vault_runtime", "-d", "vault", "--clean", "--if-exists", "--no-owner",
    ], cwd=ROOT, input=database, check=True)
    _compose("up", "-d", "--wait")
    reconcile = _compose("exec", "-T", "vault", "python", "-m", "app.vault_runtime.package_runtime",
                         "reconcile-restore", check=False)
    if reconcile.returncode != 0:
        raise SystemExit("Backup data was restored, but the restore reconcile step failed "
                         f"(exit {reconcile.returncode}). Check './vault-package logs' before using Vault.")
    print("Vault backup restored and package health verified.")


def factory_reset(confirmation: str) -> None:
    if confirmation != "DELETE ALL VAULT DATA":
        raise SystemExit("Factory reset requires --confirm 'DELETE ALL VAULT DATA'.")
    _compose("down", "--volumes", "--remove-orphans")
    print("Removed the production Vault containers and both production data volumes.")


def uninstall(*, delete_data: bool, confirmation: str | None) -> None:
    if delete_data:
        factory_reset(confirmation or "")
        return
    _compose("down", "--remove-orphans")
    print("Removed package containers and network. Production data volumes were preserved.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--lan", action="store_true")
    for name in ("start", "status", "logs", "setup", "stop", "backup"):
        sub.add_parser(name)
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("backup")
    restore_parser.add_argument("--confirm", default="")
    reset = sub.add_parser("factory-reset")
    reset.add_argument("--confirm", default="")
    remove = sub.add_parser("uninstall")
    remove.add_argument("--delete-data", action="store_true")
    remove.add_argument("--confirm")
    args = parser.parse_args()
    actions = {
        "start": start, "status": status, "logs": logs,
        "setup": setup, "stop": stop, "backup": backup,
    }
    if args.command == "factory-reset":
        factory_reset(args.confirm)
    elif args.command == "restore":
        restore(args.backup, args.confirm)
    elif args.command == "uninstall":
        uninstall(delete_data=args.delete_data, confirmation=args.confirm)
    elif args.command == "install":
        install(lan=args.lan)
    else:
        actions[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
