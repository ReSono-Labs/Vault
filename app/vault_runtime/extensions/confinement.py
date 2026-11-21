"""Kernel-enforced file confinement for hosted extension processes.

Uses the same Linux Landlock code as agent commands (``commands/landlock.py``). Vault
starts every supervised process through a small launcher that applies the rules, sets
no_new_privs and replaces itself with the package's command, so the threaded Vault server
never runs code between fork and exec. The rules hold for the command and everything it
starts and cannot be lifted from inside. Landlock also stops a confined process from
reading other processes' ``/proc`` entries (ptrace checks), so Vault's environment stays
out of reach.

The launcher runs in Python's isolated mode with an explicit path to Vault's code: a
package's own files can never stand in for the launcher.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from app.vault_runtime.commands.landlock import LandlockError, abi_version, restrict_self

_ROOT = str(Path(__file__).resolve().parents[3])
_SYSTEM_READ = ("/usr", "/etc", "/lib", "/lib64", "/bin", "/sbin", "/proc", "/dev", "/sys/devices/system/cpu")
_SYSTEM_WRITE = ("/dev/null", "/dev/zero", "/dev/tty")


def landlock_abi() -> int:
    return abi_version()


def _real(paths: tuple[str, ...] | list[str]) -> list[str]:
    """Landlock can't use a symlink: system locations like /lib -> /usr/lib are resolved."""
    seen: list[str] = []
    for path in paths:
        if path and os.path.exists(path):
            real = os.path.realpath(path)
            if real not in seen:
                seen.append(real)
    return seen


def rules_for(*, install_root: Path, data_dir: Path, extra_read: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """Its own package read only, its own data folder read and write, plus system files and
    the Python that Vault and package virtual environments link to."""
    python_homes = (sys.base_prefix, os.path.dirname(os.path.dirname(os.path.realpath(sys.executable))), sys.prefix)
    return [*((path, "read") for path in _real([*_SYSTEM_READ, *python_homes, *extra_read])),
            *((path, "write") for path in _real(_SYSTEM_WRITE)),
            (str(install_root), "read"), (str(data_dir), "write")]


def launcher_command(command: list[str], *, rules: list[tuple[str, str]]) -> list[str]:
    bootstrap = (f"import sys; sys.path.insert(0, {_ROOT!r}); "
                 "from app.vault_runtime.extensions.confinement import main; raise SystemExit(main(sys.argv[1:]))")
    return [sys.executable, "-I", "-c", bootstrap, json.dumps({"rules": rules}), "--", *command]


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "--":
        print("confinement: usage: SPEC -- COMMAND ...", file=sys.stderr)
        return 2
    rules = [(str(path), str(kind)) for path, kind in json.loads(argv[0])["rules"]]
    command = argv[2:]
    try:
        restrict_self(rules)
    except LandlockError as exc:
        print(f"Vault couldn't start this extension safely: {exc}", file=sys.stderr)
        return 126
    try:
        os.execvp(command[0], command)
    except OSError as exc:
        print(f"Vault couldn't start {command[0]}: {exc}", file=sys.stderr)
        return 127
    return 0
