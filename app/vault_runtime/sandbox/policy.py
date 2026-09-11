from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from app.vault_runtime.system_agents.inventory import AgentKind

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class SandboxPolicyError(RuntimeError):
    code = "sandbox_policy_denied"


@dataclass(frozen=True, slots=True)
class SandboxIdentity:
    user_id: str
    workspace_id: str
    local_session_id: str
    run_id: str
    agent: AgentKind

    def __post_init__(self) -> None:
        for name, value in (("user_id", self.user_id), ("workspace_id", self.workspace_id),
                            ("local_session_id", self.local_session_id), ("run_id", self.run_id)):
            if not _IDENTIFIER.fullmatch(value):
                raise SandboxPolicyError(f"Sandbox {name} is invalid.")
        if self.agent not in {AgentKind.VOICE, AgentKind.BACKGROUND}:
            raise SandboxPolicyError("Only fixed Voice and Background system agents may use this sandbox.")


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    cpu_seconds: int = 10
    address_space_bytes: int = 256 * 1024 * 1024
    file_size_bytes: int = 10 * 1024 * 1024
    process_count: int = 64
    open_file_count: int = 128
    wall_clock_seconds: float = 30.0

    def __post_init__(self) -> None:
        bounds = {
            "cpu_seconds": (1, 120), "address_space_bytes": (64 * 1024 * 1024, 4 * 1024**3),
            "file_size_bytes": (1024 * 1024, 256 * 1024 * 1024), "process_count": (1, 512),
            "open_file_count": (16, 1024), "wall_clock_seconds": (1, 600),
        }
        for name, (minimum, maximum) in bounds.items():
            value = getattr(self, name)
            if not minimum <= value <= maximum:
                raise SandboxPolicyError(f"Sandbox {name} is outside the accepted limit.")


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    identity: SandboxIdentity
    run_root: Path
    limits: SandboxLimits = SandboxLimits()

    def __post_init__(self) -> None:
        root = self.run_root.resolve()
        if not root.is_absolute() or root == Path("/"):
            raise SandboxPolicyError("Sandbox run root must be a bounded absolute path.")
        object.__setattr__(self, "run_root", root)
