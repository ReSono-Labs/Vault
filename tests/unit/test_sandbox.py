from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from app.vault_runtime.sandbox import BubblewrapSandbox, SandboxIdentity, SandboxLimits, SandboxPolicy
from app.vault_runtime.sandbox.policy import SandboxPolicyError
from app.vault_runtime.system_agents.inventory import AgentKind


def _policy(tmp_path: Path, run: str = "run-1") -> SandboxPolicy:
    return SandboxPolicy(
        SandboxIdentity("user-1", "workspace-1", "session-1", run, AgentKind.BACKGROUND),
        tmp_path / run,
        SandboxLimits(wall_clock_seconds=2),
    )


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="Bubblewrap is unavailable")
def test_bubblewrap_hides_host_network_and_environment(tmp_path: Path) -> None:
    sandbox = BubblewrapSandbox()
    assert sandbox.probe()["passed"] is True
    result = sandbox.run(
        _policy(tmp_path),
        command=("/usr/bin/python3", "-c", (
            "import json,os,pathlib,socket; "
            "s=socket.socket(); s.settimeout(.1); "
            "\ntry: s.connect(('127.0.0.1',1)); network=True"
            "\nexcept OSError: network=False"
            "\nprint(json.dumps({'home':pathlib.Path('/home').exists(),"
            "'passwd':pathlib.Path('/etc/passwd').exists(),'secret':os.getenv('VAULT_SECRET'),"
            "'network':network,'workspace':pathlib.Path('/workspace').exists()}))"
        )),
    )
    assert result.status == "ok"
    assert result.stdout.strip() == '{"home": false, "passwd": false, "secret": null, "network": false, "workspace": true}'


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="Bubblewrap is unavailable")
def test_one_sandbox_timeout_does_not_damage_another(tmp_path: Path) -> None:
    sandbox = BubblewrapSandbox()
    slow = SandboxPolicy(
        SandboxIdentity("user-1", "workspace-1", "session-1", "slow", AgentKind.BACKGROUND),
        tmp_path / "slow", SandboxLimits(wall_clock_seconds=1),
    )
    timed_out = sandbox.run(slow, command=("/usr/bin/python3", "-c", "import time; time.sleep(3)"))
    healthy = sandbox.run(_policy(tmp_path, "healthy"), command=("/usr/bin/python3", "-c", "print('ok')"))
    assert timed_out.status == "timeout" and timed_out.timed_out is True
    assert healthy.status == "ok" and healthy.stdout == "ok\n"


def test_policy_rejects_non_system_identity_and_broad_root(tmp_path: Path) -> None:
    with pytest.raises(SandboxPolicyError):
        SandboxPolicy(
            SandboxIdentity("user", "workspace", "session", "run", "build"),  # type: ignore[arg-type]
            tmp_path / "run",
        )
    with pytest.raises(SandboxPolicyError):
        SandboxPolicy(
            SandboxIdentity("user", "workspace", "session", "run", AgentKind.VOICE), Path("/"),
        )
