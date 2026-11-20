"""Child launcher: apply limits and Landlock, then exec the command.

Runs as `python -m app.vault_runtime.commands.launch` with a JSON spec on stdin, so the
threaded Vault server never runs code between fork and exec. Nothing from the spec is
interpreted by a shell unless the spec asks for `/bin/sh -c` (approved commands only).
"""

from __future__ import annotations

import json
import os
import resource
import sys

from app.vault_runtime.commands.landlock import LandlockError, restrict_self


def main() -> int:
    spec = json.loads(sys.stdin.read())
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    # The runner already started this process in its own session (start_new_session).
    limits = spec["limits"]
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpuSeconds"], limits["cpuSeconds"]))
    resource.setrlimit(resource.RLIMIT_AS, (limits["addressSpaceBytes"], limits["addressSpaceBytes"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits["fileSizeBytes"], limits["fileSizeBytes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (limits["openFiles"], limits["openFiles"]))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        restrict_self([(str(path), str(kind)) for path, kind in spec["rules"]])
    except LandlockError as exc:
        print(f"Vault couldn't start the command safely: {exc}", file=sys.stderr)
        return 126
    os.chdir(spec["cwd"])
    argv = spec["argv"]
    try:
        os.execvpe(argv[0], argv, spec["env"])
    except FileNotFoundError:
        print(f"Command not found: {argv[0]}", file=sys.stderr)
        return 127
    except PermissionError:
        print(f"Not allowed to run: {argv[0]}", file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
