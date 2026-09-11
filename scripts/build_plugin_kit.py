#!/usr/bin/env python3
"""Assemble deterministic public Vault Plugin Kit downloads."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"
OUTPUT = ROOT / "release" / "plugin-kit"


def _zip_tree(source: Path, output: Path, root_name: str) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(f"{root_name}/{path.relative_to(source).as_posix()}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT.glob("*.zip"):
        old.unlink()
    with tempfile.TemporaryDirectory(prefix="vault-plugin-kit-") as temporary:
        staged = Path(temporary) / f"resono-labs-vault-plugin-kit-{VERSION}"
        shutil.copytree(ROOT / "plugin-kit", staged)
        shutil.copy2(ROOT / "docs/VAULT-PLUGIN-KIT.md", staged / "GUIDE.md")
        _zip_tree(staged, OUTPUT / f"resono-labs-vault-plugin-kit-{VERSION}.zip", staged.name)
        for language in ("python", "typescript"):
            starter = staged / "starters" / language
            _zip_tree(starter, OUTPUT / f"resono-labs-vault-plugin-{language}-starter-{VERSION}.zip", "starter.example")
    archives = sorted(OUTPUT.glob("*.zip"))
    checksums = "".join(f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in archives)
    (OUTPUT / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    print(f"Built {len(archives)} Plugin Kit downloads in {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
