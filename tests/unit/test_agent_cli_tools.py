from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.vault_runtime.commands import policy
from app.vault_runtime.commands.repository import CommandRequest
from app.vault_runtime.commands.runner import available, plan_access, run_command
from app.vault_runtime.commands.service import CommandService
from app.vault_runtime.commands.tools import CHAT_ONLY_TOOL_NAMES, register_command_tools
from app.vault_runtime.folders.errors import (
    FolderAdminRequiredError,
    FolderInvalidRequestError,
    FolderUnavailableError,
)
from app.vault_runtime.folders.models import DeviceLocation
from app.vault_runtime.folders.search import SearchOptions
from app.vault_runtime.folders.service import FolderService
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.workspace_files.discovery import Budget, WorkspaceDiscovery
from app.vault_runtime.workspace_files.service import WorkspaceFileService
from app.vault_runtime.workspace_storage import WorkspaceStorage
from tests.support.folders import MemoryFolderRepository, _principal

needs_landlock = pytest.mark.skipif(not available(), reason="Linux Landlock is required")


class NoShares:
    def list_shares_for_grantee(self, **_kwargs):
        return []


class MemoryCommands:
    def __init__(self) -> None:
        self.settings: dict[str, object] = {}
        self.requests: dict[str, CommandRequest] = {}

    def get_setting(self, key):
        return self.settings.get(key)

    def set_setting(self, key, value, *, updated_by):
        self.settings[key] = value

    def create(self, *, user_id, workspace_id, agent, conversation_id, directory, command, state):
        now = datetime.now(UTC)
        item = CommandRequest(str(uuid4()), user_id, workspace_id, agent, conversation_id, directory, command, state,
                              None, now, None, None, now + timedelta(minutes=15))
        self.requests[item.request_id] = item
        return item

    def get(self, *, user_id, request_id):
        item = self.requests.get(request_id)
        return item if item and item.user_id == user_id else None

    def pending_for_conversation(self, *, user_id, conversation_id):
        return [r for r in self.requests.values()
                if r.user_id == user_id and r.conversation_id == conversation_id and r.state in {"pending", "approved"}]

    def decide(self, *, user_id, request_id, approve):
        item = self.get(user_id=user_id, request_id=request_id)
        if item is None or item.state != "pending":
            raise FolderUnavailableError("That command request is no longer waiting for a decision.")
        self.requests[request_id] = replace(item, state="approved" if approve else "denied")
        return self.requests[request_id]

    def claim_approved(self, *, user_id, request_id, conversation_id):
        item = self.get(user_id=user_id, request_id=request_id)
        if item is None or item.conversation_id != conversation_id or item.state != "approved":
            if item is not None and item.state == "pending":
                raise FolderInvalidRequestError("The person hasn't approved this command yet.")
            raise FolderUnavailableError("That command can't run.")
        self.requests[request_id] = replace(item, state="running")
        return self.requests[request_id]

    def finish(self, *, request_id, state, outcome):
        self.requests[request_id] = replace(self.requests[request_id], state=state, outcome=outcome)


@pytest.fixture
def world(tmp_path: Path):
    home = tmp_path / "home"
    project = home / "Documents" / "Projects" / "app"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.py").write_text("def main():\n    # TODO: ship\n    return 1\n")
    (project / "src" / "util.py").write_text("VALUE = 2\n")
    (project / "README.md").write_text("# App\n" + "".join(f"line {i}\n" for i in range(2, 101)))
    (project / "node_modules" / "dep").mkdir(parents=True)
    (project / "node_modules" / "dep" / "index.js").write_text("TODO in dependency")
    (project / ".env").write_text("SECRET=1")
    repo = MemoryFolderRepository({"admin", "kid"})
    folders = FolderService(repository=repo, locations=(DeviceLocation("home", "Home", home, "home"),),
                            documents_folder="Documents")
    admin, kid = _principal("admin", admin=True), _principal("kid")
    folders.admin_add_folder(principal=admin, location_id="home", path="Documents/Projects", name="Projects",
                             permission="write")
    storage = WorkspaceStorage(tmp_path / "private")
    storage.ensure_root()
    files = WorkspaceFileService(NoShares(), storage, folders=folders)  # type: ignore[arg-type]
    commands = CommandService(repository=MemoryCommands(), folders=folders, scratch_root=tmp_path / "scratch")  # type: ignore[arg-type]
    return {"home": home, "project": project, "folders": folders, "files": files, "admin": admin, "kid": kid,
            "commands": commands, "discovery": WorkspaceDiscovery(files)}


# Discovery


def test_glob_tree_and_line_reads(world) -> None:
    d, admin = world["discovery"], world["admin"]
    found = d.glob(principal=admin, pattern="**/*.py", directory="local/Projects", budget=Budget(5, 100))
    assert sorted(found["matches"]) == ["local/Projects/app/src/main.py", "local/Projects/app/src/util.py"]
    tree = d.tree(principal=admin, directory="local/Projects/app", depth=2, budget=Budget(5, 100))
    names = {node["name"]: node for node in tree["tree"]}
    assert set(names) == {"README.md", "node_modules", "src"}
    assert names["node_modules"]["skipped"] and [c["name"] for c in names["src"]["children"]] == ["main.py", "util.py"]
    part = d.read_lines(principal=admin, file_key="local/Projects/app/README.md", start_line=10, end_line=12,
                        head=None, tail=None)
    assert part["contentMarkdown"] == "line 10\nline 11\nline 12" and part["totalLines"] == 100
    tail = d.read_lines(principal=admin, file_key="local/Projects/app/README.md", start_line=None, end_line=None,
                        head=None, tail=2)
    assert tail["contentMarkdown"] == "line 99\nline 100" and tail["startLine"] == 99


def test_read_many_info_and_copy(world) -> None:
    d, admin, project = world["discovery"], world["admin"], world["project"]
    many = d.read_many(principal=admin, file_keys=["local/Projects/app/src/util.py", "local/Projects/app/missing.py"])
    assert many["files"][0]["contentMarkdown"] == "VALUE = 2\n" and "error" in many["files"][1]
    info = d.info(principal=admin, path="local/Projects/app/src/main.py")
    assert info["kind"] == "file" and info["lineCount"] == 3
    d.copy(principal=admin, source="local/Projects/app/src/util.py", destination="local/Projects/app/src/util_copy.py")
    assert (project / "src" / "util_copy.py").read_text() == "VALUE = 2\n"
    with pytest.raises(Exception):
        d.copy(principal=admin, source="local/Projects/app/src/util.py", destination="local/Projects/app/src/util_copy.py")


def test_search_options(world) -> None:
    files, admin = world["files"], world["admin"]
    regex = files.search_files(principal=admin, query=r"TODO:\s+\w+", directory="local/Projects",
                               options=SearchOptions(regex=True, context_lines=1))
    assert [(m["fileKey"], m["line"]) for m in regex["matches"]] == [("local/Projects/app/src/main.py", 2)]
    assert regex["matches"][0]["contextBefore"] == ["def main():"]
    only_md = files.search_files(principal=admin, query="line 5", directory="local/Projects",
                                 options=SearchOptions(include=("**/*.md",)))
    assert {m["fileKey"] for m in only_md["matches"]} == {"local/Projects/app/README.md"}
    names = files.search_files(principal=admin, query="util", directory="local/Projects",
                               options=SearchOptions(names_only=True))
    assert {m["fileKey"] for m in names["matches"]} == {"local/Projects/app/src/util.py"}


# Background command policy


@pytest.mark.parametrize("command", [
    "rg -n TODO src", "ls -la", "git log --oneline -5", "wc -l README.md", "find src -name '*.py'".replace("'*.py'", "src"),
])
def test_read_only_commands_are_allowed(command: str) -> None:
    assert policy.background_argv(command)


@pytest.mark.parametrize("command", [
    "rm -rf src", "rg TODO | head", "cat README.md > out", "find . -delete", "git push", "git -c core.pager=x log",
    "sh -c ls", "/usr/bin/ls", "cat ../../etc/passwd", "ls $HOME", "git branch -D main", "rg --pre=cat x",
])
def test_unsafe_background_commands_are_refused(command: str) -> None:
    with pytest.raises(FolderInvalidRequestError):
        policy.background_argv(command)


# Sandbox


@needs_landlock
def test_commands_stay_inside_the_folder(world, tmp_path: Path) -> None:
    project = world["project"]
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    out = run_command(argv=["/bin/sh", "-c", f"cat src/util.py; cat {outside}; echo hi > made.txt; ls"],
                      root=project, cwd=project, writable=True, include_hidden=True, scratch_parent=tmp_path / "s")
    assert "VALUE = 2" in out.stdout and "private" not in out.stdout
    assert "Permission denied" in out.stderr
    assert (project / "made.txt").read_text() == "hi\n"
    read_only = run_command(argv=["/bin/sh", "-c", "echo x > other.txt"], root=project, cwd=project,
                            writable=False, include_hidden=True, scratch_parent=tmp_path / "s")
    assert read_only.exit_code != 0 and not (project / "other.txt").exists()
    assert not list((tmp_path / "s").iterdir()), "scratch home is deleted after each command"


@needs_landlock
def test_hidden_files_stay_unreadable_when_hidden(world, tmp_path: Path) -> None:
    project = world["project"]
    plan = plan_access(project, writable=False, include_hidden=False)
    assert plan.limited and (str(project), "list") in plan.rules
    out = run_command(argv=["/bin/sh", "-c", "cat .env; cat README.md | head -1"], root=project, cwd=project,
                      writable=False, include_hidden=False, scratch_parent=tmp_path / "s")
    assert "SECRET" not in out.stdout and "# App" in out.stdout and out.note
    visible = run_command(argv=["cat", ".env"], root=project, cwd=project, writable=False, include_hidden=True,
                          scratch_parent=tmp_path / "s")
    assert visible.stdout == "SECRET=1"


@needs_landlock
def test_timeouts_and_output_caps(world, tmp_path: Path) -> None:
    project = world["project"]
    slow = run_command(argv=["sleep", "10"], root=project, cwd=project, writable=False, include_hidden=True,
                       scratch_parent=tmp_path / "s", timeout=1)
    assert slow.timed_out and slow.exit_code is None and slow.duration_ms < 5000
    big = run_command(argv=["/bin/sh", "-c", "yes | head -c 200000"], root=project, cwd=project, writable=False,
                      include_hidden=True, scratch_parent=tmp_path / "s")
    assert big.output_truncated and len(big.stdout) == 64 * 1024


# Approval flow


@needs_landlock
def test_chat_commands_need_a_click_and_background_is_read_only(world) -> None:
    commands, admin, kid, project = world["commands"], world["admin"], world["kid"], world["project"]
    with pytest.raises(FolderInvalidRequestError):  # Off by default.
        commands.prepare_chat(principal=admin, conversation_id="c1", directory="local/Projects", command="ls")
    with pytest.raises(FolderAdminRequiredError):
        commands.set_enabled(principal=kid, enabled=True)
    commands.set_enabled(principal=admin, enabled=True)

    # src has no hidden files, so it is fully writable even with hidden files off.
    prepared = commands.prepare_chat(principal=admin, conversation_id="c1", directory="local/Projects/app/src",
                                     command="echo built > out.txt && cat out.txt")
    assert prepared["approvalRequired"] is True and not (project / "src" / "out.txt").exists()
    with pytest.raises(FolderInvalidRequestError):  # The model can't run it before the click.
        commands.run_approved_chat(principal=admin, conversation_id="c1", request_id=prepared["requestId"])
    assert [p["requestId"] for p in commands.pending(principal=admin, conversation_id="c1")] == [prepared["requestId"]]
    commands.decide(principal=admin, request_id=prepared["requestId"], approve=True)
    with pytest.raises(FolderUnavailableError):  # Another chat can't use it.
        commands.run_approved_chat(principal=admin, conversation_id="other", request_id=prepared["requestId"])
    ran = commands.run_approved_chat(principal=admin, conversation_id="c1", request_id=prepared["requestId"])
    assert ran["exitCode"] == 0 and ran["stdout"] == "built\n" and (project / "src" / "out.txt").exists()
    with pytest.raises(FolderUnavailableError):  # Runs once.
        commands.run_approved_chat(principal=admin, conversation_id="c1", request_id=prepared["requestId"])

    denied = commands.prepare_chat(principal=admin, conversation_id="c1", directory="local/Projects", command="ls")
    commands.decide(principal=admin, request_id=denied["requestId"], approve=False)
    with pytest.raises(Exception):
        commands.run_approved_chat(principal=admin, conversation_id="c1", request_id=denied["requestId"])

    background = commands.run_background(principal=admin, directory="local/Projects/app", command="rg -n TODO src")
    assert "TODO: ship" in background["stdout"] and background["folderPermission"] == "read"
    with pytest.raises(FolderInvalidRequestError):
        commands.run_background(principal=admin, directory="local/Projects/app", command="rm -rf src")
    with pytest.raises(FolderUnavailableError):  # Not their folder.
        commands.run_background(principal=kid, directory="local/Projects", command="ls")


def test_voice_never_sees_command_tools(world) -> None:
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    world["commands"].set_enabled(principal=world["admin"], enabled=available())
    register_command_tools(catalog=catalog, service=world["commands"])
    voice = ToolInvocationContext(agent=AgentKind.VOICE, user_id="admin", workspace_id="ws-admin",
                                  tool_call_id="t", local_session_id="s", voice_session_id="v")
    result = catalog.invoke("command_run", {"directory": "local/Projects", "command": "ls"}, context=voice)
    assert result.is_error and "Chat" in result.text
    assert {"command_run", "command_run_approved"} == CHAT_ONLY_TOOL_NAMES
    background_names = {d.name for d in catalog.definitions_for(AgentKind.BACKGROUND, user_id="admin",
                                                                  workspace_id="ws-admin")}
    # The Background Agent gets only read-only command tools.
    assert background_names <= {"command_run_read_only", "git_repo_info"}


def test_tool_errors_go_back_to_the_agent_instead_of_failing_the_turn(world) -> None:
    from app.vault_runtime.workspace_files.tools import register_workspace_file_tools

    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    register_workspace_file_tools(catalog=catalog, service=world["files"])
    chat = ToolInvocationContext(agent=AgentKind.VOICE, user_id="admin", workspace_id="ws-admin",
                                 tool_call_id="t", local_session_id="s", conversation_id="c", turn_id="t1")
    result = catalog.invoke("workspace_list_directory", {"directory": "local/No such folder"}, context=chat)
    assert result.is_error and json.loads(result.text)["code"] == "folder_unavailable"
