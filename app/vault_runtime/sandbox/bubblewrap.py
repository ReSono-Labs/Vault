from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import resource
import shutil
import subprocess
from time import perf_counter
from collections.abc import Mapping, Sequence

from app.vault_runtime.sandbox.policy import SandboxPolicy, SandboxPolicyError
from app.vault_runtime.sandbox.policy import SandboxIdentity
from app.vault_runtime.system_agents.inventory import AgentKind


class SandboxUnavailableError(RuntimeError):
    code = "sandbox_unavailable"


@dataclass(frozen=True, slots=True)
class SandboxCommandResult:
    status: str
    return_code: int | None
    duration_ms: float
    stdout: str
    stderr: str
    timed_out: bool = False


class BubblewrapSandbox:
    """Linux process boundary adapted from Voice, without Agent Package identity."""

    def __init__(self, *, executable: str | None = None) -> None:
        self._executable = executable

    def probe(self) -> dict[str, object]:
        system_python = Path("/usr/bin/python3")
        python = str(system_python) if system_python.is_file() and os.access(system_python, os.X_OK) else shutil.which("python3")
        if not python:
            return {"passed": False, "failureCode": "python_missing"}
        observed: dict[str, object] = {}
        result = None
        # Namespace creation can transiently return EAGAIN while another local
        # worker exits. Retry the identical fail-closed probe; never fall back
        # to unsandboxed execution.
        for _attempt in range(3):
            result = self.run(
                SandboxPolicy(
                    SandboxIdentity("probe", "probe", "probe", "probe", AgentKind.BACKGROUND),
                    Path("/tmp/resono-vault-sandbox-probe"),
                ),
                command=(python, "-c", "import json,pathlib; print(json.dumps({'home':pathlib.Path('/home').exists(),'passwd':pathlib.Path('/etc/passwd').exists()}))"),
                _probe=True,
            )
            try:
                decoded = json.loads(result.stdout.strip())
                observed = decoded if isinstance(decoded, dict) else {}
            except (ValueError, TypeError):
                observed = {}
            if result.status == "ok" and observed == {"home": False, "passwd": False}:
                return {"passed": True, "failureCode": None, "observed": observed}
        return {
            "passed": False, "failureCode": "probe_failed", "observed": observed,
            "returnCode": result.return_code if result else None,
        }

    def run(
        self, policy: SandboxPolicy, *, command: Sequence[str],
        read_only_mounts: Mapping[Path, str] | None = None,
        environment: Mapping[str, str] | None = None, stdin: str | None = None,
        _probe: bool = False,
    ) -> SandboxCommandResult:
        bwrap = self._resolved()
        if not bwrap:
            raise SandboxUnavailableError("Bubblewrap is required for executable capabilities on Linux.")
        if not command or any(not str(part) or "\x00" in str(part) for part in command):
            raise SandboxPolicyError("Sandbox command is invalid.")
        if _probe:
            timeout, limits = 5.0, None
            run_root = None
        else:
            timeout, limits, run_root = policy.limits.wall_clock_seconds, policy.limits, policy.run_root
            run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if run_root.is_symlink():
                raise SandboxPolicyError("Sandbox run root cannot be a symbolic link.")
        args = [bwrap, "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
                "--unshare-net", "--die-with-parent", "--new-session", "--clearenv",
                "--setenv", "PATH", "/usr/bin:/bin"]
        for source in ("/usr", "/lib", "/lib64"):
            if Path(source).exists(): args.extend(("--ro-bind", source, source))
        for name, value in sorted((environment or {}).items()):
            if not name.isupper() or not name.replace("_", "A").isalnum() or name == "PATH" or "\x00" in value:
                raise SandboxPolicyError("Sandbox environment is invalid.")
            args.extend(("--setenv", name, value))
        for source, target in (read_only_mounts or {}).items():
            resolved, destination = source.resolve(strict=True), PurePosixPath(target)
            if not destination.is_absolute() or str(destination) in {"/", "/home", "/root", "/etc"} or ".." in destination.parts:
                raise SandboxPolicyError("Sandbox mount target is denied.")
            if resolved.is_symlink() or str(resolved).startswith(("/var/run/docker.sock", "/var/lib/docker", "/var/lib/postgresql")):
                raise SandboxPolicyError("Sandbox mount source is denied.")
            args.extend(("--ro-bind", str(resolved), str(destination)))
        args.extend(("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"))
        if run_root is not None:
            args.extend(("--dir", "/workspace", "--bind", str(run_root), "/workspace", "--chdir", "/workspace"))
        else:
            args.extend(("--chdir", "/tmp"))
        args.extend(("--", *(str(part) for part in command)))
        started = perf_counter()
        try:
            completed = subprocess.run(
                args, capture_output=True, text=True, input=stdin, env={}, check=False,
                timeout=timeout, preexec_fn=_limit_process(limits) if limits else None,
            )
            return SandboxCommandResult(
                "ok" if completed.returncode == 0 else "failed", completed.returncode,
                (perf_counter() - started) * 1000, completed.stdout or "", completed.stderr or "",
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxCommandResult(
                "timeout", None, (perf_counter() - started) * 1000,
                exc.stdout if isinstance(exc.stdout, str) else "",
                exc.stderr if isinstance(exc.stderr, str) else "", True,
            )

    def _resolved(self) -> str | None:
        candidate = self._executable or shutil.which("bwrap")
        return candidate if candidate and os.access(candidate, os.X_OK) else None


def _limit_process(limits):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (limits.address_space_bytes, limits.address_space_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits.file_size_bytes, limits.file_size_bytes))
        # RLIMIT_NPROC is per host UID and can break unrelated concurrent Vault
        # sessions. PID caps belong to a delegated cgroup, not this child preexec.
        resource.setrlimit(resource.RLIMIT_NOFILE, (limits.open_file_count, limits.open_file_count))
    return apply
