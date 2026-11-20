"""Which commands the Background Agent may run without asking.

Chat commands always need the user's approval first and run as written (through /bin/sh).
Background commands run unattended, so they must be a single read-only program from the list
below, with no shell features at all.
"""

from __future__ import annotations

import shlex

from app.vault_runtime.folders.errors import FolderInvalidRequestError

MAX_COMMAND_LENGTH = 2_000

_SHELL_CHARACTERS = set("|;&<>`$(){}\n\\*?[]!~#")

# program -> allowed first arguments (None: any arguments, still checked against _DENIED_ARGUMENTS)
_READ_ONLY: dict[str, frozenset[str] | None] = {
    "rg": None, "grep": None, "ls": None, "tree": None, "wc": None, "head": None, "tail": None,
    "cat": None, "file": None, "du": None, "stat": None, "find": None, "sort": None, "uniq": None,
    "diff": None, "jq": None, "fdfind": None, "fd": None, "realpath": None, "basename": None, "dirname": None,
    "git": frozenset({"status", "log", "diff", "show", "ls-files", "rev-parse", "blame", "branch", "tag",
                      "describe", "shortlog", "grep", "remote"}),
}
_DENIED_ARGUMENTS = {
    "find": ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"),
    "fd": ("-x", "--exec", "-X", "--exec-batch"),
    "fdfind": ("-x", "--exec", "-X", "--exec-batch"),
    "rg": ("--pre", "--search-zip", "-z"),
    "sort": ("-o", "--output"),
    "git": ("-c", "--exec-path", "--output", "--ext-diff", "--textconv", "-o", "--git-dir", "--work-tree"),
    "tree": ("-o",),
    "branch": ("-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy", "--set-upstream-to", "-u"),
    "tag": ("-d", "--delete", "-a", "-s", "-m", "-f"),
    "remote": ("add", "remove", "rm", "rename", "set-url", "set-head", "prune", "update"),
}


def validate_text(command: str) -> str:
    text = str(command or "").strip()
    if not text:
        raise FolderInvalidRequestError("A command is required.")
    if len(text) > MAX_COMMAND_LENGTH or "\x00" in text:
        raise FolderInvalidRequestError("That command is too long.")
    return text


def background_argv(command: str) -> list[str]:
    """Parse a Background Agent command, or explain why it needs a person's approval instead."""
    text = validate_text(command)
    if any(character in _SHELL_CHARACTERS for character in text):
        raise FolderInvalidRequestError(
            "Background commands can't use shell features (pipes, redirects, variables, wildcards). "
            "Run one read-only program, for example: rg -n TODO src"
        )
    try:
        argv = shlex.split(text)
    except ValueError as exc:
        raise FolderInvalidRequestError("That command couldn't be read.") from exc
    program = argv[0]
    if "/" in program or program not in _READ_ONLY:
        allowed = ", ".join(sorted(_READ_ONLY))
        raise FolderInvalidRequestError(
            f"The Background Agent can only run read-only programs without approval: {allowed}."
        )
    arguments = argv[1:]
    subcommands = _READ_ONLY[program]
    if subcommands is not None:
        subcommand = next((item for item in arguments if not item.startswith("-")), None)
        if subcommand not in subcommands:
            raise FolderInvalidRequestError(
                f"Only these {program} commands are allowed without approval: {', '.join(sorted(subcommands))}."
            )
        denied = _DENIED_ARGUMENTS.get(program, ()) + _DENIED_ARGUMENTS.get(subcommand or "", ())
    else:
        denied = _DENIED_ARGUMENTS.get(program, ())
    for argument in arguments:
        name = argument.split("=", 1)[0]
        if name in denied or (program == "git" and argument.startswith("--output")):
            raise FolderInvalidRequestError(f"`{argument}` can change files, so it needs approval in Chat.")
        if argument.startswith("/") or argument == ".." or argument.startswith("../") or "/../" in argument:
            raise FolderInvalidRequestError("Use paths inside the folder, like src/app.py.")
    return argv
