"""Fast search inside a host folder with ripgrep.

ripgrep skips binary files, hidden entries (unless allowed), anything in .gitignore,
and never follows symlinks. It runs with an argument list (no shell), inside the
folder, with a time limit; every path it returns is checked again before use.
"""

from __future__ import annotations

import json
import os
import re
import selectors
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.vault_runtime.folders.errors import FolderError, FolderInvalidRequestError
from app.vault_runtime.folders.paths import resolve_inside

# Matched by name, never searched inside.
SKIP_DIRECTORIES = ("node_modules", "__pycache__", "site-packages", "venv", ".venv", ".git", "target", "dist", "build")
MAX_FILE_SIZE = "512K"
_GLOB_ALLOWED = re.compile(r"^[^\x00\n]{1,200}$")


@dataclass(frozen=True, slots=True)
class SearchOptions:
    """What agents can ask for, mirroring Grep/grep_search in other agent tools."""

    regex: bool = False
    case_sensitive: bool = False
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    context_lines: int = 0
    max_per_file: int = 1
    names_only: bool = False

    def __post_init__(self) -> None:
        for pattern in self.include + self.exclude:
            if not _GLOB_ALLOWED.fullmatch(pattern) or pattern.startswith("/") or ".." in pattern.split("/"):
                raise FolderInvalidRequestError("Include and exclude patterns must be relative globs like **/*.md.")
        if not 0 <= self.context_lines <= 3 or not 1 <= self.max_per_file <= 20:
            raise FolderInvalidRequestError("contextLines must be 0-3 and maxPerFile 1-20.")


@dataclass(frozen=True, slots=True)
class FolderSearchHit:
    relative_path: str
    kind: str  # "file" or "directory"
    snippet: str | None = None
    line: int | None = None
    context: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class FolderSearchResult:
    hits: list[FolderSearchHit]
    truncated: bool


_SEPARATORS = re.compile(r"[\s_.\-]+")


def name_words(query: str) -> list[str]:
    return [word for word in _SEPARATORS.split(query.casefold()) if word]


def name_matches(name: str, words: list[str]) -> bool:
    """'ReSono Link' matches 'ReSono-Labs-Link': every word appears; spaces, dashes, dots and _ are equal."""
    folded = name.casefold()
    return bool(words) and all(word in folded for word in words)


def ripgrep() -> str | None:
    return shutil.which("rg")


def _base_args(executable: str, include_hidden: bool, options: SearchOptions | None = None) -> list[str]:
    args = [executable, "--no-config", "--no-messages", "--max-filesize", MAX_FILE_SIZE]
    if include_hidden:
        args.append("--hidden")
    for name in SKIP_DIRECTORIES:
        args += ["--glob", f"!**/{name}/**"]
    if options is not None:
        for pattern in options.include:
            args += ["--glob", pattern]
        for pattern in options.exclude:
            args += ["--glob", f"!{pattern}"]
    return args


def _stream(args: list[str], cwd: Path, deadline: float):
    """Yield stdout lines until the process ends; yields None once if the deadline passes."""
    process = subprocess.Popen(
        args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C.UTF-8"},
    )
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer = b""
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                yield None
                return
            if not selector.select(timeout=min(remaining, 0.25)):
                if process.poll() is not None:
                    break
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            buffer += chunk
            *lines, buffer = buffer.split(b"\n")
            for line in lines:
                yield line
        if buffer:
            yield buffer
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


class _Collector:
    def __init__(self, base: Path, include_hidden: bool, limit: int) -> None:
        self.base = base
        self.include_hidden = include_hidden
        self.limit = limit
        self.hits: list[FolderSearchHit] = []
        self.seen: set[tuple[str, int | None]] = set()

    @property
    def full(self) -> bool:
        return len(self.hits) >= self.limit

    def allowed(self, relative: str) -> bool:
        try:  # Same rules as every other folder request: inside, no symlinks, hidden only if allowed.
            resolve_inside(self.base, relative, allow_hidden=self.include_hidden)
        except FolderError:
            return False
        return True

    def add(self, hit: FolderSearchHit) -> None:
        key = (hit.relative_path, hit.line)
        if self.full or key in self.seen or not self.allowed(hit.relative_path):
            return
        self.seen.add(key)
        self.hits.append(hit)


def list_files(
    *, base: Path, include_hidden: bool, deadline: float, executable: str, options: SearchOptions | None = None,
):
    """Yield relative file paths ripgrep would search (None once if time ran out)."""
    for line in _stream(_base_args(executable, include_hidden, options) + ["--files"], base, deadline):
        yield None if line is None else line.decode("utf-8", "replace").removeprefix("./")


def search_folder(
    *, base: Path, query: str, include_hidden: bool, limit: int, deadline: float, executable: str,
    options: SearchOptions | None = None,
) -> FolderSearchResult:
    """Names first (files and the folders that contain them), then text inside files."""
    options = options or SearchOptions()
    folded = query.casefold()
    path_query = "/" in folded
    words = name_words(query)
    collector = _Collector(base, include_hidden, limit)
    truncated = False

    if not options.regex:
        names_deadline = deadline if options.names_only else time.monotonic() + max(0.0, (deadline - time.monotonic()) * 0.5)
        for relative in list_files(base=base, include_hidden=include_hidden, deadline=names_deadline,
                                   executable=executable, options=options):
            if relative is None:
                truncated = True
                break
            parts = PurePosixPath(relative).parts
            if path_query:
                if folded in relative.casefold():
                    collector.add(FolderSearchHit(relative, "file"))
            else:
                for depth, part in enumerate(parts[:-1]):
                    if name_matches(part, words):
                        collector.add(FolderSearchHit("/".join(parts[: depth + 1]), "directory"))
                if parts and name_matches(parts[-1], words):
                    collector.add(FolderSearchHit(relative, "file"))
            if collector.full:
                return FolderSearchResult(collector.hits, True)
    if options.names_only:
        return FolderSearchResult(collector.hits, truncated)

    content_args = _base_args(executable, include_hidden, options) + [
        "--json", "--max-count", str(options.max_per_file), "--max-columns", "300",
    ]
    if not options.regex:
        content_args.append("--fixed-strings")
    if not options.case_sensitive:
        content_args.append("--ignore-case")
    if options.context_lines:
        content_args += ["--context", str(options.context_lines)]
    content_args += ["-e", query, "--", "."]
    pending_before: list[str] = []
    for line in _stream(content_args, base, deadline):
        if line is None:
            truncated = True
            break
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        data = event.get("data", {})
        text = str(data.get("lines", {}).get("text", "")).rstrip("\n")
        if kind == "context":
            pending_before = (pending_before + [text[:300]])[-options.context_lines:]
            continue
        if kind != "match":
            continue
        relative = str(data.get("path", {}).get("text", "")).removeprefix("./")
        collector.add(FolderSearchHit(
            relative, "file", text.strip()[:300] or None, data.get("line_number"), tuple(pending_before),
        ))
        pending_before = []
        if collector.full:
            truncated = True
            break
    return FolderSearchResult(collector.hits, truncated)


def glob_folder(
    *, base: Path, pattern: str, include_hidden: bool, limit: int, deadline: float, executable: str,
) -> FolderSearchResult:
    """Files matching a glob like **/*.md, plus folders whose path matches it."""
    options = SearchOptions(include=(pattern,))
    collector = _Collector(base, include_hidden, limit)
    truncated = False
    for relative in list_files(base=base, include_hidden=include_hidden, deadline=deadline,
                               executable=executable, options=options):
        if relative is None:
            truncated = True
            break
        collector.add(FolderSearchHit(relative, "file"))
        if collector.full:
            truncated = True
            break
    return FolderSearchResult(collector.hits, truncated)
