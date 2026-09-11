from __future__ import annotations

from app.vault_runtime.memory.evidence import bounded_tool_evidence
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.tools.definitions import ToolInvocationContext, ToolInvocationResult


class VoiceToolEvidenceObserver:
    """R1 evidence recorder adapted to scoped Phase 3 transcript storage."""

    def __init__(self, *, memories: MemoryRepository) -> None:
        self._memories = memories

    def __call__(
        self,
        context: ToolInvocationContext,
        name: str,
        arguments: dict[str, object],
        result: ToolInvocationResult,
    ) -> None:
        if not context.voice_session_id:
            return
        payload = bounded_tool_evidence(
            name=name,
            arguments=arguments,
            result=result.structured_content if result.structured_content is not None else result.text,
            is_error=result.is_error,
        )
        self._memories.append_transcript_next(
            user_id=context.user_id,
            workspace_id=context.workspace_id,
            voice_session_id=context.voice_session_id,
            role="tool",
            event_type=f"tool.{name}.{'failed' if result.is_error else 'completed'}",
            text_content=payload,
        )
