"""Docker Vault reaches Link Agent Network through this companion, not a user proxy.

The packaged compose host-gateway is the only hop. Peer URLs stay Link hostnames.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from app.vault_runtime.extensions.runtime_port_forwarder import runtime_port_publish_enabled

COMPANION_DOCKER_GATEWAY = "http://host.docker.internal:8769"


def link_agent_network_host(hostname: str) -> bool:
    host = hostname.strip().lower().rstrip(".")
    if not host.endswith(".agents.resonolink.com"):
        return False
    labels = host.split(".")
    return len(labels) >= 4 and labels[0].startswith("agent-")


def companion_docker_gateway() -> str | None:
    if not runtime_port_publish_enabled():
        return None
    return COMPANION_DOCKER_GATEWAY


def companion_request_options(url: str) -> dict[str, str]:
    parsed = urlsplit(url)
    if not parsed.hostname or not link_agent_network_host(parsed.hostname):
        return {}
    gateway = companion_docker_gateway()
    if not gateway:
        return {}
    return {"proxy": gateway}
