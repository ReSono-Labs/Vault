import shutil
from pathlib import Path

import pytest

from app.vault_runtime.extensions.filesystem import (
    ExtensionFilesystem,
    ExtensionFilesystemError,
    extension_relative_path,
)


def _candidate(root: Path, name: str, content: str) -> Path:
    candidate = root / name
    candidate.mkdir()
    (candidate / "SKILL.md").write_text(content, encoding="utf-8")
    return candidate


def test_replace_preserves_previous_and_rollback_swaps_versions(tmp_path: Path) -> None:
    filesystem = ExtensionFilesystem(tmp_path / "extensions")
    first = filesystem.replace(category="skills", identity="demo", candidate_root=_candidate(tmp_path, "one", "one"))
    assert (first.current / "SKILL.md").read_text() == "one"
    second = filesystem.replace(category="skills", identity="demo", candidate_root=_candidate(tmp_path, "two", "two"))
    assert (second.current / "SKILL.md").read_text() == "two"
    assert second.previous and (second.previous / "SKILL.md").read_text() == "one"
    rolled = filesystem.rollback(category="skills", identity="demo")
    assert (rolled.current / "SKILL.md").read_text() == "one"
    assert rolled.previous and (rolled.previous / "SKILL.md").read_text() == "two"


def test_filesystem_accepts_nested_and_human_readable_identities(tmp_path: Path) -> None:
    filesystem = ExtensionFilesystem(tmp_path / "extensions")
    candidate = _candidate(tmp_path, "one", "one")
    tree = filesystem.replace(category="mcps", identity="test.plugin/crm", candidate_root=candidate)
    assert tree.current.is_dir()
    assert (tmp_path / "extensions" / "mcps" / "test.plugin" / "crm" / "current" / "SKILL.md").is_file()
    filesystem.remove(category="mcps", identity="test/mcp")
    filesystem.replace(category="mcps", identity="test/mcp", candidate_root=candidate)
    assert (tmp_path / "extensions" / "mcps" / "test" / "mcp" / "current" / "SKILL.md").is_file()
    filesystem.replace(category="skills", identity="Work", candidate_root=candidate)
    assert (tmp_path / "extensions" / "skills" / "Work" / "current" / "SKILL.md").is_file()


def test_filesystem_rejects_traversal_and_missing_previous(tmp_path: Path) -> None:
    filesystem = ExtensionFilesystem(tmp_path / "extensions")
    candidate = _candidate(tmp_path, "one", "one")
    with pytest.raises(ExtensionFilesystemError, match="unsafe"):
        filesystem.replace(category="skills", identity="../escape", candidate_root=candidate)
    with pytest.raises(ExtensionFilesystemError, match="unsafe"):
        filesystem.replace(category="skills", identity="foo/../bar", candidate_root=candidate)
    with pytest.raises(ExtensionFilesystemError, match="no previous"):
        filesystem.rollback(category="skills", identity="demo")


def test_extension_relative_path_allows_normal_path_segments() -> None:
    assert str(extension_relative_path("test.plugin/crm")) == "test.plugin/crm"
    assert str(extension_relative_path("Work")) == "Work"
    with pytest.raises(ExtensionFilesystemError):
        extension_relative_path("/absolute")


def test_revert_removes_tree_without_previous_version(tmp_path: Path) -> None:
    filesystem = ExtensionFilesystem(tmp_path / "extensions")
    filesystem.replace(category="skills", identity="demo", candidate_root=_candidate(tmp_path, "one", "one"))
    filesystem.revert(category="skills", identity="demo", had_active_install=False)
    assert not (tmp_path / "extensions" / "skills" / "demo").exists()


def test_revert_falls_back_to_remove_when_previous_missing(tmp_path: Path) -> None:
    filesystem = ExtensionFilesystem(tmp_path / "extensions")
    filesystem.replace(category="skills", identity="demo", candidate_root=_candidate(tmp_path, "one", "one"))
    base = tmp_path / "extensions" / "skills" / "demo"
    shutil.rmtree(base / "previous", ignore_errors=True)
    filesystem.revert(category="skills", identity="demo", had_active_install=True)
    assert not base.exists()


def test_recover_restores_previous_after_interrupted_move(tmp_path: Path) -> None:
    extensions = tmp_path / "extensions"
    base = extensions / "skills" / "demo"
    previous = base / "previous"
    previous.mkdir(parents=True)
    (previous / "SKILL.md").write_text("stable", encoding="utf-8")
    staged = base / ".staged-op1"
    staged.mkdir()
    recovery = extensions / "recovery"
    recovery.mkdir()
    (recovery / "op1.json").write_text(
        '{"operationId":"op1","category":"skills","identity":"demo","state":"previous-moved","hadCurrent":true}',
        encoding="utf-8",
    )
    assert ExtensionFilesystem(extensions).recover() == ("op1",)
    assert (base / "current" / "SKILL.md").read_text() == "stable"
    assert not staged.exists()
    assert not (recovery / "op1.json").exists()
