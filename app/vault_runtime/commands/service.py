"""Agents running commands inside a person's folders.

- One Vault-wide switch, controlled by the master account; off by default.
- Chat: every command needs the person's click on Run first. The model can't approve.
- Background Agent: read-only programs from an allow-list run without asking.
- Voice: no commands (no screen to review them, and answers must be fast).
- Commands run inside the folder only, confined with Landlock; network is allowed.
"""

from __future__ import annotations

import shlex
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.vault_runtime.commands import policy
from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
from app.vault_runtime.commands.repository import CommandRepository, CommandRequest
from app.vault_runtime.commands.runner import CommandUnavailableError, available, check_runnable, run_command
from app.vault_runtime.folders.errors import (
    FolderAdminRequiredError,
    FolderInvalidRequestError,
    FolderWriteNotAllowedError,
)
from app.vault_runtime.folders.paths import resolve_inside
from app.vault_runtime.folders.service import FolderService
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.local_paths import parse_local_view_path

SETTING_KEY = "commands.enabled"
_CACHE_SECONDS = 5.0


class CommandService:
    def __init__(self, *, repository: CommandRepository, folders: FolderService, scratch_root: Path) -> None:
        self._repository = repository
        self._folders = folders
        self._scratch_root = scratch_root
        self._cache: tuple[float, bool] | None = None
        self._lock = threading.Lock()

    # Switch

    @staticmethod
    def platform_ready() -> bool:
        return available()

    def enabled(self) -> bool:
        with self._lock:
            if self._cache is not None and time.monotonic() - self._cache[0] < _CACHE_SECONDS:
                return self._cache[1]
        value = bool(self._repository.get_setting(SETTING_KEY)) and self.platform_ready()
        with self._lock:
            self._cache = (time.monotonic(), value)
        return value

    def settings(self) -> dict[str, Any]:
        return {"enabled": self.enabled(), "available": self.platform_ready()}

    def set_enabled(self, *, principal: LocalPrincipal, enabled: bool) -> dict[str, Any]:
        if not principal.is_device_owner:
            raise FolderAdminRequiredError("Only the master account can turn commands on or off.")
        if enabled and not self.platform_ready():
            raise FolderInvalidRequestError("Commands can't run on this computer (Linux Landlock is required).")
        self._repository.set_setting(SETTING_KEY, bool(enabled), updated_by=principal.user_id)
        with self._lock:
            self._cache = None
        return self.settings()

    # Shared

    def _require_enabled(self) -> None:
        if not self.enabled():
            raise FolderInvalidRequestError("Commands are turned off. The master account can turn them on in Settings.")

    def _place(self, principal: LocalPrincipal, directory: str):
        parsed = parse_local_view_path(directory)
        if parsed is None or not parsed.mount_name:
            raise FolderInvalidRequestError(
                "Commands run inside one of your folders. Use a directory like local/Projects or local/Projects/app."
            )
        access = self._folders.resolve(principal=principal, view_path=directory)
        cwd = resolve_inside(access.root, access.relative_path, allow_hidden=access.include_hidden)
        if not cwd.is_dir():
            raise FolderInvalidRequestError("Commands need a directory to run in, not a file.")
        return access, cwd

    def _execute(self, *, request: CommandRequest, argv: list[str], principal: LocalPrincipal,
                 writable: bool) -> dict[str, Any]:
        access, cwd = self._place(principal, request.directory)
        if writable and not access.can_write:
            writable = False
        try:
            outcome = run_command(
                argv=argv, root=access.root, cwd=cwd, writable=writable,
                include_hidden=access.include_hidden, scratch_parent=self._scratch_root,
            )
        except CommandUnavailableError as exc:
            self._repository.finish(request_id=request.request_id, state="failed", outcome={"error": str(exc)})
            raise FolderInvalidRequestError(str(exc)) from exc
        result = {
            "requestId": request.request_id, "directory": request.directory, "command": request.command,
            **{key: value for key, value in asdict(outcome).items()},
            "folderPermission": "write" if writable else "read",
        }
        self._repository.finish(request_id=request.request_id, state="completed", outcome={
            key: result[key] for key in ("exit_code", "duration_ms", "timed_out", "output_truncated")
        })
        return _camel(result)

    # Chat

    def prepare_chat(self, *, principal: LocalPrincipal, conversation_id: str, directory: str,
                     command: str) -> dict[str, Any]:
        self._require_enabled()
        text = policy.validate_text(command)
        access, cwd = self._place(principal, directory)
        # Refuse now if the command could never run here, instead of after the person clicked Run.
        try:
            check_runnable(root=access.root, cwd=cwd, writable=access.can_write, include_hidden=access.include_hidden)
        except CommandUnavailableError as exc:
            raise FolderInvalidRequestError(str(exc)) from exc
        request = self._repository.create(
            user_id=principal.user_id, workspace_id=principal.workspace_id, agent="chat",
            conversation_id=conversation_id, directory=directory, command=text, state="pending",
        )
        return {
            "approvalRequired": True,
            "requestId": request.request_id,
            "directory": directory,
            "command": text,
            "canChangeFiles": access.can_write,
            "instructions": (
                "Waiting for the person. Tell them in one or two sentences what this command does and why. "
                "They will click Run or Don't run below the chat. After they click Run, call command_run_approved "
                "with this requestId. Never claim it ran before that."
            ),
        }

    def run_approved_chat(self, *, principal: LocalPrincipal, conversation_id: str, request_id: str) -> dict[str, Any]:
        self._require_enabled()
        request = self._repository.claim_approved(
            user_id=principal.user_id, request_id=request_id, conversation_id=conversation_id,
        )
        return self._execute(
            request=request, argv=["/bin/sh", "-c", request.command], principal=principal, writable=True,
        )

    def pending(self, *, principal: LocalPrincipal, conversation_id: str) -> list[dict[str, Any]]:
        return [
            {"requestId": item.request_id, "directory": item.directory, "command": item.command,
             "state": item.state, "expiresAt": item.expires_at.isoformat()}
            for item in self._repository.pending_for_conversation(
                user_id=principal.user_id, conversation_id=conversation_id,
            )
        ]

    def decide(self, *, principal: LocalPrincipal, request_id: str, approve: bool) -> dict[str, Any]:
        request = self._repository.decide(user_id=principal.user_id, request_id=request_id, approve=approve)
        return {"requestId": request.request_id, "state": request.state, "command": request.command,
                "directory": request.directory}

    # Background Agent

    def run_background(self, *, principal: "LocalPrincipal | OwnerScope", directory: str, command: str) -> dict[str, Any]:
        self._require_enabled()
        argv = policy.background_argv(command)
        self._place(principal, directory)
        request = self._repository.create(
            user_id=principal.user_id, workspace_id=principal.workspace_id, agent="background",
            conversation_id=None, directory=directory, command=shlex.join(argv), state="running",
        )
        return self._execute(request=request, argv=argv, principal=principal, writable=False)


    # Git summary (read-only, no approval)

    def git_info(self, *, principal: "LocalPrincipal | OwnerScope", directory: str) -> dict[str, Any]:
        """Remotes (credentials removed), branch, upstream, recent commits and changed files.

        Git needs the hidden .git folder; Vault opens only that folder for these fixed read-only
        commands, so other hidden files (.env, keys) stay hidden. Runs in the same sandbox as commands.
        """
        self._require_enabled()
        access, cwd = self._place(principal, directory)
        repo = next((path for path in (cwd, *cwd.parents) if (path / ".git").exists()
                     and (path == access.root or access.root in path.parents)), None)
        if repo is None:
            raise FolderInvalidRequestError("This directory isn't inside a Git repository in this folder.")
        git_dir = repo / ".git"
        if not git_dir.is_dir():
            raise FolderInvalidRequestError(
                "This repository keeps its Git data outside the folder (a worktree), so Vault can't read it.")
        git = "git -c safe.directory='*' -c core.fsmonitor=false -c core.hooksPath=/dev/null --no-optional-locks"
        steps = [
            f"echo @@remotes; {git} remote -v",
            f"echo @@branch; {git} rev-parse --abbrev-ref HEAD",
            f"echo @@upstream; {git} rev-parse --abbrev-ref --symbolic-full-name @{{upstream}} 2>/dev/null",
            f"echo @@counts; {git} rev-list --left-right --count HEAD...@{{upstream}} 2>/dev/null",
            f"echo @@log; {git} log -5 --format=%h%x09%cI%x09%s",
        ]
        status_note = None
        try:
            outcome = run_command(
                argv=["/bin/sh", "-c", "; ".join([*steps, f"echo @@status; {git} status --porcelain=v1 --untracked-files=normal 2>&1 | head -n 51"])],
                root=access.root, cwd=repo, writable=False, include_hidden=access.include_hidden,
                scratch_parent=self._scratch_root, timeout=30.0,
                extra_read=(git_dir, *([repo / ".gitignore"] if (repo / ".gitignore").is_file() else [])),
            )
        except CommandUnavailableError:
            # Too big to open the working files with hidden files hidden: read .git alone (no changed files).
            try:
                outcome = run_command(
                    argv=["/bin/sh", "-c", "; ".join(steps)], root=access.root, cwd=git_dir, writable=False,
                    include_hidden=False, scratch_parent=self._scratch_root, timeout=30.0,
                )
            except CommandUnavailableError as exc:
                raise FolderInvalidRequestError(str(exc)) from exc
            status_note = ("Changed files aren't listed: this repository is too large to open while hidden "
                           "files are hidden. Everything else was read from .git.")
        sections: dict[str, list[str]] = {}
        current = None
        for line in outcome.stdout.splitlines():
            if line.startswith("@@"):
                current = line[2:]
                sections[current] = []
            elif current is not None and line.strip():
                sections[current].append(line)
        remotes: dict[str, str] = {}
        for line in sections.get("remotes", []):
            parts = line.split()
            if len(parts) >= 2:
                remotes.setdefault(parts[0], _strip_credentials(parts[1]))
        counts = (sections.get("counts") or [""])[0].split()
        raw_status = sections.get("status", [])
        status = [line for line in raw_status if not line.startswith(("warning:", "fatal:", "error:"))]
        if status_note is None and len(status) != len(raw_status):
            status_note = ("Some .gitignore files in subfolders are hidden, so a few ignored files may be "
                           "listed as untracked.")
        relative = str(repo.relative_to(access.root)) if repo != access.root else ""
        return {
            "repository": "/".join(part for part in ("local", parse_local_view_path(directory).mount_name, relative) if part),
            "remotes": [{"name": name, "url": url} for name, url in remotes.items()],
            "branch": (sections.get("branch") or [None])[0],
            "upstream": (sections.get("upstream") or [None])[0],
            "ahead": int(counts[0]) if len(counts) == 2 and counts[0].isdigit() else None,
            "behind": int(counts[1]) if len(counts) == 2 and counts[1].isdigit() else None,
            "recentCommits": [dict(zip(("hash", "date", "subject"), line.split("\t", 2))) for line in sections.get("log", [])],
            "changedFiles": None if status_note else status[:50],
            "changedFilesTruncated": len(status) > 50,
            "changedFilesNote": status_note,
            "note": ("Read from the repository's .git folder only; other hidden files stay hidden. "
                     "This runs inside Vault, so it says nothing about programs or logins on the computer itself (gh, SSH keys)."),
        }


def _strip_credentials(url: str) -> str:
    """https://user:token@host/x -> https://host/x; scp-style git@host:x is kept (no secret in it)."""
    import re
    return re.sub(r"^([a-z][a-z0-9+.-]*://)[^/@]*@", r"\1", url, flags=re.I)


def _camel(value: dict[str, Any]) -> dict[str, Any]:
    def convert(key: str) -> str:
        head, *rest = key.split("_")
        return head + "".join(part.title() for part in rest)
    return {convert(key): item for key, item in value.items()}


__all__ = ["CommandService", "FolderWriteNotAllowedError"]
