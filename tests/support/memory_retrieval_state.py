"""Shared test helpers moved out of test modules (TST-01)."""

from dataclasses import replace

from tests.support.memory import _candidate, _entry


def create(memories, principal, *, key="drink", visibility="private", confidence="high"):
    entry = _entry(memories, principal, session=key, index=0, text="Remember tea")
    return memories.reconcile_memory(
        user_id=principal.user_id, workspace_id=principal.workspace_id,
        voice_session_id=key,
        candidate=replace(_candidate(content="Prefers tea", visibility=visibility),
                          memory_key=key, confidence=confidence),
        evidence=((entry.entry_id, "user_statement", "user_asserted", entry.text_content),),
    )
