"""DB-05: updates back up first, backups record the schema version, restore refuses newer schemas."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "packaging" / "docker-release"


def _load_vault_package():
    spec = importlib.util.spec_from_file_location("vault_package_under_test", ROOT / "scripts" / "vault_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def vault_package(tmp_path, monkeypatch):
    module = _load_vault_package()
    monkeypatch.setattr(module, "BACKUP_ROOT", tmp_path / "backups")
    monkeypatch.setattr(module, "PACKAGE_ENV", tmp_path / "missing.env")
    monkeypatch.setattr(module, "FOLDERS_FILE", tmp_path / "missing.yml")
    return module


def _fake_run(calls, *, has_table: bool, version: int = 1):
    def run(command, **kwargs):
        calls.append(command)
        if "pg_dump" in command:
            return SimpleNamespace(stdout=b"dump", returncode=0)
        if "psql" in command:
            sql = command[-1]
            out = ("t" if has_table else "f") if "to_regclass" in sql else str(version)
            return SimpleNamespace(stdout=out + "\n", returncode=0)
        if "tar" in command and "czf" in command:
            backup_dir = next(arg.split(":")[0] for arg in command if arg.endswith(":/backup"))
            Path(backup_dir, "vault-data.tar.gz").write_bytes(b"data")
        return SimpleNamespace(stdout="", returncode=0)
    return run


@pytest.mark.parametrize(("has_table", "expected"), [(True, 1), (False, 0)])
def test_backup_manifest_records_schema_version(vault_package, monkeypatch, has_table, expected) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(vault_package.subprocess, "run", _fake_run(calls, has_table=has_table))
    vault_package.backup()
    (destination,) = vault_package.BACKUP_ROOT.iterdir()
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["schemaVersion"] == expected
    assert manifest["sha256"]["vault.dump"] == sha256(b"dump").hexdigest()


def _backup(tmp_path: Path, **manifest_extra) -> Path:
    folder = tmp_path / "backup"
    folder.mkdir()
    files = {"vault.dump": b"dump", "vault-data.tar.gz": b"data"}
    for name, content in files.items():
        (folder / name).write_bytes(content)
    manifest = {"format": 1, "sha256": {n: sha256(c).hexdigest() for n, c in files.items()}, **manifest_extra}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


def test_latest_schema_version_reads_the_shipped_migrations(vault_package) -> None:
    assert vault_package.latest_schema_version() >= 1


def test_restore_refuses_a_newer_schema_before_touching_anything(vault_package, monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(vault_package.subprocess, "run", _fake_run(calls, has_table=True))
    folder = _backup(tmp_path, schemaVersion=vault_package.latest_schema_version() + 1)
    with pytest.raises(SystemExit, match="newer than this Vault"):
        vault_package.restore(str(folder), "RESTORE VAULT BACKUP")
    assert calls == []


@pytest.mark.parametrize("extra", [{}, {"schemaVersion": 0}, {"schemaVersion": 1}])
def test_restore_accepts_same_older_or_pre_migration_backups(vault_package, monkeypatch, tmp_path, extra) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(vault_package.subprocess, "run", _fake_run(calls, has_table=True))
    vault_package.restore(str(_backup(tmp_path, **extra)), "RESTORE VAULT BACKUP")
    assert any("pg_restore" in call for call in calls)


# The release script: a fake `docker` records every call, so the order of the decisions is checked.
FAKE_DOCKER = """#!/bin/sh
printf '%s\\n' "$*" >> "$DOCKER_LOG"
case "$*" in
  "volume inspect"*) [ "$FAKE_EXISTING" = 1 ] ;;
  *"to_regclass"*) echo t ;;
  *"max(version)"*) echo 1 ;;
  *" cp postgres:"*) for last; do :; done; printf x > "$last" ;;
  *) exit 0 ;;
esac
"""


def _run_release_script(tmp_path: Path, *, existing: bool, command: str = "update"):
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)
    (package / "vault.env").write_text("")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    log = tmp_path / "docker.log"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "DOCKER_LOG": str(log),
           "FAKE_EXISTING": "1" if existing else "0", "VAULT_LAN_ADDRESS": "192.168.1.50", "HOME": str(tmp_path)}
    result = subprocess.run(["sh", str(package / "vault"), command], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return package, log.read_text().splitlines()


def test_update_backs_up_existing_data_before_starting_the_new_image(tmp_path) -> None:
    package, calls = _run_release_script(tmp_path, existing=True)
    compose = [call.split(" -f ")[-1].split(" ", 1)[-1] for call in calls if call.startswith("compose")]
    assert compose[0] == "stop vault"
    assert compose[1] == "up -d --wait --no-deps postgres"
    dump = next(i for i, call in enumerate(calls) if "pg_dump" in call)  # inside the exec script
    postgres = calls.index(next(call for call in calls if call.endswith("up -d --wait --no-deps postgres")))
    assert postgres < dump < len(calls) - 1 and compose[-1] == "up -d --wait" and calls[-1].endswith(compose[-1])
    (backup,) = (package / "backups").iterdir()
    manifest = json.loads((backup / "manifest.json").read_text())
    assert manifest["schemaVersion"] == 1
    assert manifest["sha256"]["vault.dump"] == sha256(b"x").hexdigest()


def test_first_install_has_nothing_to_back_up(tmp_path) -> None:
    package, calls = _run_release_script(tmp_path, existing=False, command="install")
    assert not any("pg_dump" in call for call in calls)
    assert not (package / "backups").exists()
    assert calls[-1].endswith("up -d --wait")


def test_release_script_syntax() -> None:
    assert subprocess.run(["bash", "-n", str(PACKAGE / "vault")]).returncode == 0


def test_install_stages_local_embeddings_when_missing(vault_package, monkeypatch, tmp_path) -> None:
    """PKG-02: a fresh clone has no packaging/local-embeddings; install stages it before the build."""
    models = tmp_path / "models"
    (models / vault_package.EMBEDDING_MANIFEST).parent.mkdir(parents=True)
    (models / vault_package.EMBEDDING_MANIFEST).write_text("{}")
    monkeypatch.setattr(vault_package, "LOCAL_EMBEDDINGS", tmp_path / "local-embeddings")
    monkeypatch.setenv("OLLAMA_MODELS", str(models))
    monkeypatch.setattr(vault_package.shutil, "which", lambda name: "/opt/ollama/bin/ollama")
    calls: list[list[str]] = []
    monkeypatch.setattr(vault_package.subprocess, "run", lambda command, **kwargs: calls.append(command))
    vault_package.stage_local_embeddings()
    (stage,) = calls
    assert stage[1:] == [str(vault_package.STAGE_LOCAL_EMBEDDINGS), "--models", str(models), "--runtime", "/opt/ollama"]

    calls.clear()
    (tmp_path / "local-embeddings").mkdir()
    (tmp_path / "local-embeddings" / "SHA256SUMS").write_text("")
    vault_package.stage_local_embeddings()
    assert calls == []


def test_install_without_ollama_explains_the_missing_step(vault_package, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(vault_package, "LOCAL_EMBEDDINGS", tmp_path / "local-embeddings")
    monkeypatch.setattr(vault_package.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="Ollama"):
        vault_package.stage_local_embeddings()
