#!/usr/bin/env python3
"""Manage Vault's isolated Python and Docker PostgreSQL test environment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.test.yml"
ENV_FILE = ROOT / ".env.test"


def _settings() -> dict[str, str]:
    values = {
        "VAULT_TEST_POSTGRES_DB": "resono_vault_test",
        "VAULT_TEST_POSTGRES_USER": "vault_test",
        "VAULT_TEST_POSTGRES_PASSWORD": "vault_test_only",
        "VAULT_TEST_POSTGRES_PORT": "55436",
    }
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in values and value.strip():
                values[key] = value.strip()
    values.update({key: os.environ[key] for key in values if os.environ.get(key)})
    return values


def _compose(
    *arguments: str,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose"]
    if ENV_FILE.exists():
        command.extend(("--env-file", str(ENV_FILE)))
    command.extend(("-f", str(COMPOSE), *arguments))
    return subprocess.run(
        command, cwd=ROOT, check=check, text=True, capture_output=capture_output,
    )


def _sync() -> None:
    subprocess.run(
        ["uv", "sync", "--extra", "dev", "--frozen"], cwd=ROOT, check=True,
    )


def _up() -> None:
    _sync()
    _compose("up", "-d", "--wait", "postgres")


def _database_url() -> str:
    settings = _settings()
    return (
        f"postgresql://{settings['VAULT_TEST_POSTGRES_USER']}:"
        f"{settings['VAULT_TEST_POSTGRES_PASSWORD']}@127.0.0.1:"
        f"{settings['VAULT_TEST_POSTGRES_PORT']}/{settings['VAULT_TEST_POSTGRES_DB']}"
    )


def _test(*pytest_arguments: str, frontend: bool) -> None:
    _up()
    environment = os.environ.copy()
    environment["VAULT_TEST_DATABASE_URL"] = _database_url()
    subprocess.run(
        ["uv", "run", "--frozen", "pytest", *(pytest_arguments or ("-q",))],
        cwd=ROOT, env=environment, check=True,
    )
    if frontend:
        subprocess.run(["npm", "test", "--", "--run"], cwd=ROOT / "frontend", check=True)
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("up", "status", "test", "test-all", "stop", "reset"))
    arguments, pytest_arguments = parser.parse_known_args()
    if arguments.action == "up":
        _up()
    elif arguments.action == "status":
        _compose("ps")
    elif arguments.action in {"test", "test-all"}:
        _test(*pytest_arguments, frontend=arguments.action == "test-all")
    elif arguments.action == "stop":
        _compose("down")
    elif arguments.action == "reset":
        _compose("down", "--volumes", "--remove-orphans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
