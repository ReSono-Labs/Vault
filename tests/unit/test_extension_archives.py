from io import BytesIO
from pathlib import Path
import stat
import tarfile
import zipfile

import pytest

from app.vault_runtime.extensions.archives import ArchiveInspector, ArchiveRejected


def _zip(files: dict[str, bytes]) -> bytes:
    target = BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return target.getvalue()


def test_archive_is_quarantined_under_one_root_and_hash_is_deterministic(tmp_path: Path) -> None:
    payload = _zip({"demo/plugin.json": b"{}", "demo/skills/hello/SKILL.md": b"hello"})
    first = ArchiveInspector(tmp_path / "q").inspect(payload, "demo.zip", required_root_file="plugin.json")
    second = ArchiveInspector(tmp_path / "q").inspect(payload, "demo.zip", required_root_file="plugin.json")
    assert first.content_root == first.candidate_root / "demo"
    assert first.content_hash == second.content_hash
    assert (first.content_root / "plugin.json").read_bytes() == b"{}"
    first.discard()
    assert not first.candidate_root.exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "root/../escape", "C:/escape"])
def test_archive_rejects_unsafe_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(ArchiveRejected):
        ArchiveInspector(tmp_path / "q").inspect(
            _zip({name: b"x", "root/plugin.json": b"{}"}), "bad.zip",
            required_root_file="plugin.json",
        )


def test_archive_rejects_casefold_collision_and_multiple_roots(tmp_path: Path) -> None:
    inspector = ArchiveInspector(tmp_path / "q")
    with pytest.raises(ArchiveRejected, match="duplicate"):
        inspector.inspect(_zip({"root/plugin.json": b"{}", "root/A": b"1", "root/a": b"2"}), "x.zip", required_root_file="plugin.json")
    with pytest.raises(ArchiveRejected, match="one root"):
        inspector.inspect(_zip({"one/plugin.json": b"{}", "two/x": b"2"}), "x.zip", required_root_file="plugin.json")


def test_archive_rejects_zip_symlink_and_tar_special_entry(tmp_path: Path) -> None:
    zipped = BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("root/plugin.json", b"{}")
        link = zipfile.ZipInfo("root/link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"target")
    with pytest.raises(ArchiveRejected, match="special"):
        ArchiveInspector(tmp_path / "q").inspect(zipped.getvalue(), "x.zip", required_root_file="plugin.json")

    tarred = BytesIO()
    with tarfile.open(fileobj=tarred, mode="w") as archive:
        manifest = tarfile.TarInfo("root/plugin.json")
        manifest.size = 2
        archive.addfile(manifest, BytesIO(b"{}"))
        link = tarfile.TarInfo("root/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "target"
        archive.addfile(link)
    with pytest.raises(ArchiveRejected, match="non-regular"):
        ArchiveInspector(tmp_path / "q").inspect(tarred.getvalue(), "x.tar", required_root_file="plugin.json")


def test_large_archive_preflight_json_uses_http_body_budget() -> None:
    import base64
    import json

    from app.vault_runtime.extensions.archives import DEFAULT_LOCAL_API_MAX_BODY_BYTES
    from app.vault_runtime.tools.strict_json import parse_json_object_bytes

    raw = b"x" * (2 * 1024 * 1024)
    body = json.dumps(
        {
            "archiveBase64": base64.b64encode(raw).decode("ascii"),
            "filename": "demo.zip",
            "audience": ["voice", "background"],
        },
    ).encode("utf-8")
    parsed = parse_json_object_bytes(body, max_bytes=DEFAULT_LOCAL_API_MAX_BODY_BYTES)
    assert parsed["filename"] == "demo.zip"
