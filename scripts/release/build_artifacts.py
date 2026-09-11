#!/usr/bin/env python3
"""Assemble user-facing Vault release archives outside the build sources."""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "release"
PACKAGING = ROOT / "packaging"


def run(*command: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, **kwargs)


def copy_template(name: str, destination: Path) -> None:
    shutil.copytree(PACKAGING / name, destination)
    for path in destination.rglob("*"):
        if path.name in {"vault", "install.sh", "resono-vault"}:
            path.chmod(0o755)


def archive_directory(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, Path(source.name) / path.relative_to(source))


def docker_release(version: str, work: Path) -> Path:
    image = f"resono-labs-vault:{version}"
    run("docker", "tag", "resono-labs-vault:local", image)
    package = work / f"resono-labs-vault-docker-{version}"
    copy_template("docker-release", package)
    env = package / "vault.env"
    env.write_text(env.read_text().replace("VAULT_VERSION=0.1.0", f"VAULT_VERSION={version}"))
    image_dir = package / "images"
    image_dir.mkdir()
    image_archive = image_dir / "resono-labs-vault.tar.zst"
    save = subprocess.Popen(["docker", "save", image], stdout=subprocess.PIPE)
    assert save.stdout is not None
    compression = subprocess.run(["zstd", "-T0", "-12", "-o", str(image_archive)], stdin=save.stdout, check=True)
    save.stdout.close()
    if save.wait() != 0 or compression.returncode != 0:
        raise RuntimeError("Docker image export failed")
    output = OUTPUT / f"{package.name}.zip"
    archive_directory(package, output)
    return output


def _docker_copy(container: str, source: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run("docker", "cp", f"{container}:{source}", str(destination))


def _docker_copy_tree(container: str, source: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    copy = subprocess.Popen(["docker", "cp", f"{container}:{source}", "-"], stdout=subprocess.PIPE)
    assert copy.stdout is not None
    extract = subprocess.run(
        ["tar", "--no-same-owner", "--no-same-permissions", "-xf", "-", "-C", str(destination)],
        stdin=copy.stdout,
        check=True,
    )
    copy.stdout.close()
    if copy.wait() != 0 or extract.returncode != 0:
        raise RuntimeError("Container payload extraction failed")


def linux_release(version: str, work: Path) -> Path:
    if platform.machine() not in {"x86_64", "AMD64"}:
        raise RuntimeError("The native release builder currently targets x86_64")
    package = work / f"resono-labs-vault-linux-x86_64-{version}"
    copy_template("linux-release", package)
    payload = package / "vault"
    payload.mkdir()
    container = subprocess.check_output(
        ["docker", "create", "--entrypoint", "/bin/true", "resono-labs-vault:local"], text=True,
    ).strip()
    try:
        _docker_copy_tree(container, "/opt/resono-vault/.", payload)
        runtime = payload / "runtime"
        (runtime / "bin").mkdir(parents=True)
        (runtime / "lib").mkdir(parents=True)
        _docker_copy(container, "/usr/local/bin/python3.12", runtime / "bin/python3")
        _docker_copy(container, "/usr/local/lib/python3.12", runtime / "lib/python3.12")
        _docker_copy(container, "/usr/local/lib/libpython3.12.so.1.0", runtime / "lib/libpython3.12.so.1.0")
    finally:
        run("docker", "rm", container)
    python = runtime / "bin/python3"
    python.chmod(0o755)
    for link in (payload / ".venv/bin/python", payload / ".venv/bin/python3", payload / ".venv/bin/python3.12"):
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to("/opt/resono-vault/runtime/bin/python3")
    launcher = runtime / "bin/python3"
    real_python = runtime / "bin/python3.12-real"
    launcher.rename(real_python)
    launcher.write_text(
        "#!/bin/sh\n"
        "runtime_root=$(CDPATH= cd -- \"$(dirname -- \"$0\")/..\" && pwd)\n"
        "application_root=$(dirname -- \"$runtime_root\")\n"
        "export LD_LIBRARY_PATH=$runtime_root/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}\n"
        "export PYTHONHOME=$runtime_root\n"
        "export PYTHONPATH=$application_root/.venv/lib/python3.12/site-packages:$application_root\n"
        "exec $runtime_root/bin/python3.12-real \"$@\"\n"
    )
    launcher.chmod(0o755)
    output = OUTPUT / f"{package.name}.zip"
    archive_directory(package, output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()
    OUTPUT.mkdir(exist_ok=True)
    for old in OUTPUT.glob(f"resono-labs-vault-*-{args.version}.zip"):
        old.unlink()
    with tempfile.TemporaryDirectory(prefix="resono-vault-release-") as temporary:
        work = Path(temporary)
        artifacts = [docker_release(args.version, work), linux_release(args.version, work)]
    manifest = OUTPUT / "SHA256SUMS"
    manifest.write_text("".join(f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts))
    for artifact in artifacts:
        print(f"{artifact} ({artifact.stat().st_size:,} bytes)")
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
