"""Provider-neutral A2A connections for the two fixed Vault agents."""

from .service import A2AService
from .tools import register_a2a_tools

__all__ = ["A2AService", "register_a2a_tools"]
