"""The memory and CPUs this Vault may actually use, wherever it runs.

Docker: the container's cgroup limits (``mem_limit``, ``cpus``). A native install under
systemd: the service's cgroup limits when set (``MemoryMax=``, ``CPUQuota=``), otherwise
the machine's memory and the CPUs this process may run on. Percentages in settings are taken
of these numbers, so the same defaults fit a small home box and a large server.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path

_CGROUP_ROOT = Path("/sys/fs/cgroup")


@dataclass(frozen=True, slots=True)
class HostResources:
    memory_bytes: int
    cpus: float               # may be fractional under a CPU quota
    cpu_ids: tuple[int, ...]  # CPUs this process may run on
    memory_source: str        # "cgroup" or "system"
    cpu_source: str           # "cgroup", "affinity" or "system"


def _own_cgroup_dir(proc_cgroup: Path, root: Path) -> Path | None:
    """The cgroup v2 directory of this process (``0::/path``), or None (v1 or unknown)."""
    try:
        for line in proc_cgroup.read_text().splitlines():
            if line.startswith("0::"):
                return root / line[3:].lstrip("/")
    except OSError:
        return None
    return None


def _cgroup_memory_limit(directory: Path | None, root: Path) -> int | None:
    """The tightest memory.max on the way from this cgroup up to the root."""
    limits: list[int] = []
    current = directory
    while current is not None and (current == root or root in current.parents):
        try:
            value = (current / "memory.max").read_text().strip()
            if value != "max":
                limits.append(int(value))
        except (OSError, ValueError):
            pass
        if current == root:
            break
        current = current.parent
    if not limits:
        try:                                   # cgroup v1
            value = int((root / "memory" / "memory.limit_in_bytes").read_text().strip())
            if value < 1 << 60:
                limits.append(value)
        except (OSError, ValueError):
            pass
    return min(limits) if limits else None


def _cgroup_cpu_limit(directory: Path | None, root: Path) -> float | None:
    limits: list[float] = []
    current = directory
    while current is not None and (current == root or root in current.parents):
        try:
            quota, period = (current / "cpu.max").read_text().split()
            if quota != "max":
                limits.append(int(quota) / int(period))
        except (OSError, ValueError):
            pass
        if current == root:
            break
        current = current.parent
    if not limits:
        try:                                   # cgroup v1
            quota = int((root / "cpu" / "cpu.cfs_quota_us").read_text())
            period = int((root / "cpu" / "cpu.cfs_period_us").read_text())
            if quota > 0 and period > 0:
                limits.append(quota / period)
        except (OSError, ValueError):
            pass
    return min(limits) if limits else None


def _system_memory(meminfo: Path) -> int:
    try:
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 1 << 30


def detect(*, cgroup_root: Path = _CGROUP_ROOT, proc: Path = Path("/proc")) -> HostResources:
    directory = _own_cgroup_dir(proc / "self" / "cgroup", cgroup_root)
    system_memory = _system_memory(proc / "meminfo")
    cgroup_memory = _cgroup_memory_limit(directory, cgroup_root)
    if cgroup_memory is not None and cgroup_memory < system_memory:
        memory, memory_source = cgroup_memory, "cgroup"
    else:
        memory, memory_source = system_memory, "system"
    try:
        cpu_ids = tuple(sorted(os.sched_getaffinity(0)))
        cpu_source = "affinity" if len(cpu_ids) < (os.cpu_count() or len(cpu_ids)) else "system"
    except (AttributeError, OSError):
        cpu_ids = tuple(range(os.cpu_count() or 1))
        cpu_source = "system"
    cpus: float = float(len(cpu_ids))
    quota = _cgroup_cpu_limit(directory, cgroup_root)
    if quota is not None and quota < cpus:
        cpus, cpu_source = quota, "cgroup"
    return HostResources(memory, cpus, cpu_ids, memory_source, cpu_source)


def share_of_cpus(resources: HostResources, percent: int) -> tuple[int, ...]:
    """At least one CPU; taken from the end of the list so Vault's busiest CPUs stay freer."""
    count = max(1, min(len(resources.cpu_ids), math.floor(resources.cpus * percent / 100 + 1e-9) or 1))
    return resources.cpu_ids[-count:]


def share_of_memory(resources: HostResources, percent: int) -> int:
    return max(128 * 1024 * 1024, resources.memory_bytes * percent // 100)
