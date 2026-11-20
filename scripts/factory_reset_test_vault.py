#!/usr/bin/env python3
"""Factory-reset only the isolated manual Browser Voice test Vault."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

import internet_test_env
import test_env


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DATABASE = "resono_vault_browser_test"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm", required=True,
        help="Must be exactly RESET-TEST-VAULT; prevents accidental data loss.",
    )
    args = parser.parse_args()
    if args.confirm != "RESET-TEST-VAULT":
        raise SystemExit("Refusing reset: pass --confirm RESET-TEST-VAULT")
    if internet_test_env.BROWSER_TEST_DATABASE != EXPECTED_DATABASE:
        raise SystemExit("Refusing reset: browser-test database identity changed")

    internet_test_env.stop()
    test_env._up()
    settings = test_env._settings()
    compose = ["docker", "compose"]
    if test_env.ENV_FILE.exists():
        compose.extend(("--env-file", str(test_env.ENV_FILE)))
    compose.extend(("-f", str(test_env.COMPOSE), "exec", "-T", "postgres"))
    user = settings["VAULT_TEST_POSTGRES_USER"]
    subprocess.run(
        [*compose, "psql", "-U", user, "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c",
         f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{EXPECTED_DATABASE}';"],
        cwd=ROOT, check=True,
    )
    subprocess.run(
        [*compose, "dropdb", "-U", user, "--if-exists", EXPECTED_DATABASE],
        cwd=ROOT, check=True,
    )
    subprocess.run(
        [*compose, "createdb", "-U", user, EXPECTED_DATABASE],
        cwd=ROOT, check=True,
    )
    for path in (internet_test_env.DATA_ROOT, internet_test_env.RUNTIME):
        if path.exists():
            shutil.rmtree(path)
    print("Factory reset complete for the isolated Browser Voice test Vault.")
    print("Run: .venv/bin/python scripts/internet_test_env.py start")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
