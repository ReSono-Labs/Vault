"""Local extension imports; capabilities only, never agent identities."""

from .models import ExtensionAudience, ExtensionKind, ExtensionState

__all__ = ["ExtensionAudience", "ExtensionKind", "ExtensionState"]
