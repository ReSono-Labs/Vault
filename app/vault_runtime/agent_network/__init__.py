"""Provider-neutral A2A connections for the two fixed Vault agents."""

from .service import A2AService
from .tools import register_a2a_tools
from .inbound import A2AInboundApp, A2AInboundHttpServer

__all__ = ["A2AService", "register_a2a_tools", "A2AInboundApp", "A2AInboundHttpServer"]
