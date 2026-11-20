from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.vault_runtime.external_memory.repository import ExternalMemoryRepository
from app.vault_runtime.memory.pipeline import FinalizeResult
from app.vault_runtime.memory.contracts import MemoryCandidate
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.service import MemoryService


@dataclass(frozen=True, slots=True)
class ExternalProposalResult:
    request_id: str
    result: FinalizeResult


class ExternalMemoryService:
    """Credential-derived scope for external search and proposal-only ingestion."""

    def __init__(self, *, integrations: ExternalMemoryRepository, memories: MemoryRepository,
                 memory_service: MemoryService,
                 finalize: Callable[[str, str, str], FinalizeResult]) -> None:
        self._integrations = integrations
        self._memories = memories
        self._memory_service = memory_service
        self._finalize = finalize

    def search(self, *, credential: str, request_id: str, query: str, limit: int = 8):
        text = query.strip()
        if not text or len(text) > 1024:
            raise ValueError("query must contain 1 to 1024 characters")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 25:
            raise ValueError("limit must be between 1 and 25")
        identity = self._integrations.authorize(
            credential=credential, operation="search", request_id=request_id,
        )
        return self._memory_service.search(
            user_id=identity.user_id, workspace_id=identity.workspace_id,
            query=text, limit=limit,
        )

    def get(self, *, credential: str, request_id: str, memory_id: str):
        identifier = memory_id.strip()
        if not identifier or len(identifier) > 128:
            raise ValueError("memoryId must contain 1 to 128 characters")
        identity = self._integrations.authorize(
            credential=credential, operation="search", request_id=request_id,
        )
        return self._memories.memory(
            user_id=identity.user_id, workspace_id=identity.workspace_id,
            memory_id=identifier,
        )

    def startup(self, *, credential: str, request_id: str, limit: int = 8):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 32:
            raise ValueError("limit must be between 1 and 32")
        identity = self._integrations.authorize(
            credential=credential, operation="search", request_id=request_id,
        )
        return self._memories.profile_memories(
            user_id=identity.user_id, workspace_id=identity.workspace_id, limit=limit,
        )

    def propose(self, *, credential: str, request_id: str, content: str,
                evidence: str = "") -> ExternalProposalResult:
        text = content.strip()
        proof = evidence.strip()
        if not text or len(text) > 4096 or len(proof) > 4096:
            raise ValueError("content must contain 1 to 4096 characters and evidence at most 4096")
        identity = self._integrations.authorize(
            credential=credential, operation="propose", request_id=request_id,
        )
        session_id = f"external:{identity.integration_id}:{request_id}"
        combined = text if not proof else f"Proposed memory: {text}\nSupporting evidence: {proof}"
        self._memories.append_transcript(
            user_id=identity.user_id, workspace_id=identity.workspace_id,
            voice_session_id=session_id, entry_index=0, role="user",
            event_type="external_memory_proposal", text_content=combined,
            metadata={"integrationId": identity.integration_id,
                      "adapterKind": identity.adapter_kind, "requestId": request_id},
        )
        return ExternalProposalResult(
            request_id, self._finalize(identity.user_id, identity.workspace_id, session_id)
        )

    def apply_action(
        self, *, credential: str, request_id: str, action_kind: str,
        memory_id: str, proposed_content: str | None = None,
    ) -> str:
        if action_kind not in {"correct", "forget"}:
            raise ValueError("action kind must be correct or forget")
        identifier = memory_id.strip()
        content = proposed_content.strip() if proposed_content is not None else None
        if not identifier or len(identifier) > 128:
            raise ValueError("memoryId must contain 1 to 128 characters")
        if action_kind == "correct" and (not content or len(content) > 4096):
            raise ValueError("newContent must contain 1 to 4096 characters")
        identity = self._integrations.authorize(
            credential=credential, operation=action_kind, request_id=request_id,
        )
        memory = self._memories.memory(
            user_id=identity.user_id, workspace_id=identity.workspace_id,
            memory_id=identifier,
        )
        session_id = f"external-action:{identity.integration_id}:{request_id}"
        description = (
            f"{identity.display_name} requests correction of memory {memory.memory_id} "
            f"from {memory.content_text!r} to {content!r}."
            if action_kind == "correct" else
            f"{identity.display_name} requests forgetting memory {memory.memory_id}: {memory.content_text!r}."
        )
        entry = self._memories.append_transcript(
            user_id=identity.user_id, workspace_id=identity.workspace_id,
            voice_session_id=session_id, entry_index=0, role="tool",
            event_type="external_memory_action", text_content=description,
            metadata={"integrationId": identity.integration_id, "requestId": request_id,
                      "actionKind": action_kind},
        )
        if action_kind == "forget":
            self._memories.delete_memory(
                user_id=identity.user_id, workspace_id=identity.workspace_id,
                memory_id=identifier,
            )
            return "forgotten"
        updated = self._memories.reconcile_memory(
            user_id=identity.user_id, workspace_id=identity.workspace_id,
            voice_session_id=session_id,
            candidate=MemoryCandidate(
                subject_id=memory.subject_id, domain=memory.domain,
                memory_type=memory.memory_type, memory_key=memory.memory_key,
                content_text=content or "", source_authority="model_derived",
                confidence="medium", sensitivity=memory.sensitivity,
                intent="correct", visibility=memory.visibility,
            ),
            evidence=((entry.entry_id, "tool_result", "model_derived", entry.text_content),),
        )
        return updated.memory_id
