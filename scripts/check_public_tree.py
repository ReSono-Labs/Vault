#!/usr/bin/env python3
"""Fail when the public repository tracks a machine-specific path or a maintainer-only record.

Checks every file `git ls-files` reports:
- no absolute home-directory path of a real account (`/home/<name>/`, `/Users/<name>/`,
  `C:\\Users\\<name>\\`); placeholder names such as `me`, `user` or `<user>` are allowed;
- no tracked file under a folder that is kept out of the public repository.

Run from anywhere inside the checkout: `python3 scripts/check_public_tree.py`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Maintainer records stay on the maintainers' machines (see .gitignore).
PRIVATE_PATHS = (
    ".dci/", ".kiro/", ".runtime/", "release/",
    "docs/archive/", "docs/assets/", "docs/cleanup/", "docs/contracts/", "docs/protocols/",
    "docs/prompts/", "docs/reviews/", "docs/development/provenance/",
    "GROUNDING.md", "SKILLS.MD", "INDEX.MD", "docs/CHANGE-INDEX.md",
)
PLACEHOLDER_USERS = {"me", "user", "username", "you", "your-name", "name", "vault", "runner", "example"}
HOME_PATH = re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\\\?Users\\\\?)([A-Za-z0-9._-]+)")


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True,
    )
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def main() -> int:
    problems: list[str] = []
    for name in tracked_files():
        if name.startswith(PRIVATE_PATHS) or name in PRIVATE_PATHS:
            problems.append(f"{name}: maintainer-only path is tracked")
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable files cannot carry a readable path
        for number, line in enumerate(text.splitlines(), start=1):
            for match in HOME_PATH.finditer(line):
                if match.group(1).lower() not in PLACEHOLDER_USERS:
                    problems.append(f"{name}:{number}: machine-specific path {match.group(0)!r}")
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} problem(s). Use repository-relative paths or a placeholder such as ~/ or <checkout>/.")
        return 1
    print("Public tree check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
