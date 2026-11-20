"""Commands plan access from the directory they run in, refuse before approval, and read Git safely."""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.vault_runtime.commands import runner
from app.vault_runtime.commands.runner import CommandUnavailableError, check_runnable, plan_for
from app.vault_runtime.commands.service import CommandService, _strip_credentials
from app.vault_runtime.folders.errors import FolderInvalidRequestError


def _crowded(root: Path) -> None:
    """A big sibling project full of hidden entries, like node_modules and .git trees under Projects."""
    for index in range(30):
        package = root / "big" / f"pkg{index}"
        package.mkdir(parents=True)
        (package / ".hidden").write_text("x")
        for leaf in range(5):
            (package / f"file{leaf}.txt").write_text("x")


def test_plan_covers_the_command_directory_not_the_whole_folder(tmp_path: Path, monkeypatch) -> None:
    _crowded(tmp_path)
    small = tmp_path / "small"
    small.mkdir()
    (small / "a.txt").write_text("a")
    monkeypatch.setattr(runner, "_PLAN_MAX_RULES", 50)
    with pytest.raises(CommandUnavailableError, match="Don't retry the same directory"):
        plan_for(root=tmp_path, cwd=tmp_path, writable=False, include_hidden=False)
    plan = plan_for(root=tmp_path, cwd=small, writable=False, include_hidden=False)
    assert plan.rules == [(str(small), "read")]
    # With hidden files shown the whole folder is granted (Git finds .git above the directory).
    assert plan_for(root=tmp_path, cwd=small, writable=False, include_hidden=True).rules == [(str(tmp_path), "read")]


class _Repo:
    def __init__(self) -> None:
        self.created = 0

    def get_setting(self, _key):
        return True

    def create(self, **_kwargs):
        self.created += 1
        return SimpleNamespace(request_id="r1")


class _Folders:
    def __init__(self, root: Path, relative: str, include_hidden: bool = False) -> None:
        self.access = SimpleNamespace(root=root, relative_path=relative, include_hidden=include_hidden, can_write=False)

    def resolve(self, **_kwargs):
        return self.access


def _service(root: Path, relative: str, scratch: Path, include_hidden: bool = False) -> tuple[CommandService, _Repo]:
    repo = _Repo()
    return CommandService(repository=repo, folders=_Folders(root, relative, include_hidden), scratch_root=scratch), repo  # type: ignore[arg-type]


def test_chat_command_that_cannot_run_is_refused_before_asking_for_approval(tmp_path: Path, monkeypatch) -> None:
    _crowded(tmp_path)
    monkeypatch.setattr(runner, "_PLAN_MAX_RULES", 50)
    monkeypatch.setattr("app.vault_runtime.commands.service.check_runnable",
                        lambda **kwargs: (runner.plan_for(**kwargs), None)[1])
    service, repo = _service(tmp_path, "", tmp_path / "scratch")
    with pytest.raises(FolderInvalidRequestError, match="too many hidden"):
        service.prepare_chat(principal=SimpleNamespace(user_id="u", workspace_id="w"), conversation_id="c",
                             directory="local/Projects", command="git remote -v")
    assert repo.created == 0   # nobody was asked to approve it


def test_credentials_are_removed_from_remote_urls() -> None:
    assert _strip_credentials("https://user:ghp_secret@github.com/a/b.git") == "https://github.com/a/b.git"
    assert _strip_credentials("https://github.com/a/b.git") == "https://github.com/a/b.git"
    assert _strip_credentials("git@github.com:a/b.git") == "git@github.com:a/b.git"


needs_sandbox = pytest.mark.skipif(not runner.available(), reason="Linux Landlock is required")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True)


@needs_sandbox
def test_git_summary_reads_dot_git_but_other_hidden_files_stay_hidden(tmp_path: Path) -> None:
    project = tmp_path / "Projects" / "app"
    project.mkdir(parents=True)
    _git(project, "init", "-q", "-b", "main")
    (project / "README.md").write_text("hello\n")
    (project / ".env").write_text("SECRET=1\n")
    (project / ".gitignore").write_text(".env\n")
    _git(project, "add", "README.md", ".gitignore")
    _git(project, "commit", "-q", "-m", "First commit")
    _git(project, "remote", "add", "origin", "https://bob:ghp_token@github.com/acme/app.git")
    (project / "README.md").write_text("changed\n")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    service, _repo = _service(tmp_path / "Projects", "app/src" if False else "app", scratch)
    info = service.git_info(principal=SimpleNamespace(user_id="u", workspace_id="w"), directory="local/Projects/app")
    assert info["remotes"] == [{"name": "origin", "url": "https://github.com/acme/app.git"}]
    assert info["branch"] == "main"
    assert [commit["subject"] for commit in info["recentCommits"]] == ["First commit"]
    assert any("README.md" in line for line in info["changedFiles"])
    assert "ghp_token" not in str(info)
    # The same sandbox still can't open other hidden files.
    outcome = runner.run_command(argv=["/bin/sh", "-c", "cat .env"], root=tmp_path / "Projects", cwd=project,
                                 writable=False, include_hidden=False, scratch_parent=scratch, extra_read=(project / ".git",))
    assert outcome.exit_code != 0 and "SECRET" not in outcome.stdout


@needs_sandbox
def test_git_summary_outside_a_repository_says_so(tmp_path: Path) -> None:
    (tmp_path / "Projects" / "notes").mkdir(parents=True)
    service, _repo = _service(tmp_path / "Projects", "notes", tmp_path)
    with pytest.raises(FolderInvalidRequestError, match="isn't inside a Git repository"):
        service.git_info(principal=SimpleNamespace(user_id="u", workspace_id="w"), directory="local/Projects/notes")
