"""Run one command inside a user's folder, confined with Landlock.

The command sees system programs (read-only), a scratch home that is deleted afterwards, and
the folder itself. When hidden files are off for the folder, only non-hidden entries are
reachable: directories that contain hidden entries are listed but not opened up, and Vault grants
access to their non-hidden children one by one. Network is allowed (owner decision).
"""

from __future__ import annotations

import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.vault_runtime.commands.landlock import abi_version

_SYSTEM_READ = ("/usr", "/etc", "/lib", "/lib64", "/bin", "/sbin", "/proc", "/dev")
_SYSTEM_WRITE = ("/dev/null", "/dev/zero")
OUTPUT_LIMIT = 64 * 1024
DEFAULT_TIMEOUT = 60.0
_PLAN_TIME_LIMIT = 3.0
_PLAN_MAX_RULES = 4_000


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    output_truncated: bool
    note: str | None = None


class CommandUnavailableError(RuntimeError):
    code = "commands_unavailable"


def available() -> bool:
    return sys.platform.startswith("linux") and abi_version() >= 1


@dataclass(slots=True)
class _Plan:
    rules: list[tuple[str, str]]
    limited: bool  # Hidden entries kept some directories names-only.


def _has_hidden(directory: Path, cache: dict[Path, bool], deadline: float) -> bool:
    if directory in cache:
        return cache[directory]
    if time.monotonic() > deadline:
        raise CommandUnavailableError(
            "This directory is too large to run commands in while hidden files are hidden. "
            "Run the command in a smaller directory inside it (for example the project's own subfolder), "
            "or ask for Show hidden files on this folder."
        )
    found = False
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.startswith("."):
                    found = True
                    break
                if entry.is_dir(follow_symlinks=False) and _has_hidden(Path(entry.path), cache, deadline):
                    found = True
                    break
    except OSError:
        found = True  # Unreadable: never grant it whole.
    cache[directory] = found
    return found


def plan_access(root: Path, *, writable: bool, include_hidden: bool) -> _Plan:
    """Landlock rules for the folder.

    A rule covers a whole tree, so with hidden files off, a directory that contains hidden
    entries (anywhere below it) only gets "list" (names, no contents), and its non-hidden
    children get their own rules. Hidden files themselves can never be opened.
    """
    kind = "write" if writable else "read"
    if include_hidden:
        return _Plan([(str(root), kind)], limited=False)
    deadline = time.monotonic() + _PLAN_TIME_LIMIT
    cache: dict[Path, bool] = {}
    rules: list[tuple[str, str]] = []
    limited = False
    pending = [root]
    while pending:
        directory = pending.pop()
        if not _has_hidden(directory, cache, deadline):
            rules.append((str(directory), kind))
            continue
        limited = True
        rules.append((str(directory), "list"))
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.startswith(".") or entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                else:
                    rules.append((entry.path, kind))
        if len(rules) > _PLAN_MAX_RULES:
            raise CommandUnavailableError(
                "This directory has too many hidden files and folders below it to run commands in while "
                "they're hidden. Run the command in a smaller directory inside it, or ask for Show hidden "
                "files on this folder. Don't retry the same directory."
            )
    return _Plan(rules, limited)


def _system_paths(paths: tuple[str, ...]) -> list[str]:
    """System locations (trusted): follow symlinks like /lib -> /usr/lib; Landlock can't use a symlink."""
    seen: list[str] = []
    for path in paths:
        if os.path.exists(path):
            real = os.path.realpath(path)
            if real not in seen:
                seen.append(real)
    return seen


def plan_for(*, root: Path, cwd: Path, writable: bool, include_hidden: bool) -> _Plan:
    """Access for one command. With hidden files shown it gets the whole folder (Git finds .git
    above cwd); otherwise only the directory it runs in, so a smaller directory really is smaller."""
    return plan_access(root if include_hidden else cwd, writable=writable, include_hidden=include_hidden)


def check_runnable(*, root: Path, cwd: Path, writable: bool, include_hidden: bool) -> None:
    """Raise CommandUnavailableError now, before anyone is asked to approve a command that can't run."""
    if not available():
        raise CommandUnavailableError("Commands can't run on this computer (Linux Landlock is required).")
    plan_for(root=root, cwd=cwd, writable=writable, include_hidden=include_hidden)


def run_command(
    *, argv: list[str], root: Path, cwd: Path, writable: bool, include_hidden: bool,
    scratch_parent: Path, timeout: float = DEFAULT_TIMEOUT, extra_read: tuple[Path, ...] = (),
) -> CommandOutcome:
    if not available():
        raise CommandUnavailableError("Commands can't run on this computer (Linux Landlock is required).")
    plan = plan_for(root=root, cwd=cwd, writable=writable, include_hidden=include_hidden)
    # Read-only extras chosen by Vault itself (a repository's .git for git_repo_info), never by the model.
    plan.rules.extend((str(path), "read") for path in extra_read)
    scratch = scratch_parent / f"cmd-{uuid.uuid4().hex}"
    (scratch / "tmp").mkdir(parents=True, mode=0o700)
    spec = {
        "argv": argv,
        "cwd": str(cwd),
        "env": {
            "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(scratch), "TMPDIR": str(scratch / "tmp"),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TERM": "dumb", "GIT_PAGER": "cat", "PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "NO_COLOR": "1",
        },
        "rules": [*((path, "read") for path in _system_paths(_SYSTEM_READ)),
                  *((path, "write") for path in _system_paths(_SYSTEM_WRITE)),
                  (str(scratch), "write"), *plan.rules],
        "limits": {"cpuSeconds": int(timeout) + 5, "addressSpaceBytes": 4 * 1024**3,
                   "fileSizeBytes": 1024**3, "openFiles": 1024},
    }
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, "-m", "app.vault_runtime.commands.launch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(Path(__file__).resolve().parents[3]), env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        start_new_session=True,
    )
    assert process.stdin and process.stdout and process.stderr
    process.stdin.write(json.dumps(spec).encode())
    process.stdin.close()
    outputs = {process.stdout: bytearray(), process.stderr: bytearray()}
    truncated = timed_out = False
    selector = selectors.DefaultSelector()
    for stream in outputs:
        selector.register(stream, selectors.EVENT_READ)
    try:
        while selector.get_map():
            remaining = started + timeout - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            for key, _ in selector.select(timeout=min(remaining, 0.5)):
                chunk = os.read(key.fileobj.fileno(), 65536)  # type: ignore[union-attr]
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffer = outputs[key.fileobj]  # type: ignore[index]
                room = OUTPUT_LIMIT - len(buffer)
                if room > 0:
                    buffer.extend(chunk[:room])
                if len(chunk) > room:
                    truncated = True
    finally:
        selector.close()
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for stream in outputs:
            stream.close()
        shutil.rmtree(scratch, ignore_errors=True)
    note = None
    if plan.limited and any(PurePosixPath(part).name == "git" for part in argv[:1]) or (
        plan.limited and argv[:2] == ["/bin/sh", "-c"] and " git " in f" {argv[2]} "
    ):
        note = ("Git needs the hidden .git folder, and hidden files are hidden in this folder. "
                "Ask the master account (or turn it on yourself if you made the folder in Vault) to show hidden files.")
    elif plan.limited:
        note = ("Hidden files are hidden in this folder, so the command couldn't open them, and couldn't "
                "create new items in folders that contain hidden files. Ask for Show hidden files for full access.")
    return CommandOutcome(
        exit_code=None if timed_out else process.returncode,
        stdout=outputs[process.stdout].decode("utf-8", "replace"),
        stderr=outputs[process.stderr].decode("utf-8", "replace"),
        duration_ms=int((time.monotonic() - started) * 1000),
        timed_out=timed_out, output_truncated=truncated, note=note,
    )
