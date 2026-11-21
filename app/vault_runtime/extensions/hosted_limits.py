"""Limits for hosted extension processes, chosen by the device owner (device-wide).

Defaults are shares of what this Vault may use (``host_resources``), so they fit any
hardware: each package may use 25% of the memory and half of the CPUs, at most 64
processes, and connect only to standard web ports plus its own workspace's packages.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

SETTING_KEY = "hostedLimits"


@dataclass(frozen=True, slots=True)
class HostedLimits:
    memory_percent: int = 25
    cpu_percent: int = 50
    max_processes: int = 64
    network: str = "standard"            # "standard" (allowlisted ports) or "open"
    extra_ports: tuple[int, ...] = ()    # also allowed in standard mode (SMTP 587, IMAP 993, ...)

    def to_json(self) -> dict[str, object]:
        value = asdict(self)
        return {"memoryPercent": value["memory_percent"], "cpuPercent": value["cpu_percent"],
                "maxProcesses": value["max_processes"], "network": value["network"],
                "extraPorts": list(value["extra_ports"])}


def _int(value: object, name: str, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ValueError(f"{name} must be a whole number from {low} to {high}.")
    return value


def parse(value: object, *, base: HostedLimits | None = None) -> HostedLimits:
    """Validate an owner's choice; missing fields keep ``base`` (or the defaults)."""
    base = base or HostedLimits()
    if not isinstance(value, dict):
        raise ValueError("Limits must be an object.")
    network = value.get("network", base.network)
    if network not in ("standard", "open"):
        raise ValueError("network must be standard or open.")
    ports = value.get("extraPorts", list(base.extra_ports))
    if not isinstance(ports, list) or len(ports) > 32:
        raise ValueError("extraPorts must be a list of at most 32 ports.")
    return HostedLimits(
        memory_percent=_int(value.get("memoryPercent", base.memory_percent), "memoryPercent", 5, 90),
        cpu_percent=_int(value.get("cpuPercent", base.cpu_percent), "cpuPercent", 10, 100),
        max_processes=_int(value.get("maxProcesses", base.max_processes), "maxProcesses", 4, 4096),
        network=network,
        extra_ports=tuple(sorted({_int(port, "port", 1, 65535) for port in ports})),
    )


def stored(value: object) -> HostedLimits:
    """The stored setting, or the defaults when absent or unreadable."""
    try:
        return parse(value) if isinstance(value, dict) else HostedLimits()
    except ValueError:
        return HostedLimits()
