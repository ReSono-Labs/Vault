"""Shared test helpers moved out of test modules (TST-01)."""

from hashlib import sha256

from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.decision_routing.contracts import InputIdentity, ScopedPrincipalRef
from app.vault_runtime.live_memory.contracts import InputSnapshot
from app.vault_runtime.live_memory.current_state import LiveStateLoader
from app.vault_runtime.live_memory.preferences import LiveMemoryPreferenceRepository


def setup(memory_context):
    url, identity, owner, second, memories = memory_context
    conversations = ConversationRepository(database_url=url)
    conversations.ensure_schema()
    conversation = conversations.create(owner.principal, "live-test")
    preferences = LiveMemoryPreferenceRepository(database_url=url)
    preferences.ensure_schema()
    scope = ScopedPrincipalRef(owner.principal.user_id, owner.principal.workspace_id, owner.principal.session_id)
    text = "Remember tea"
    item = InputIdentity(conversation.conversation_id, conversation.segments[0].segment_id,
                         "utterance", 1, None, sha256(text.encode()).hexdigest())
    loader = LiveStateLoader(database_url=url, memories=memories, preferences=preferences)
    captured = loader.capture(scope, item)
    snap = InputSnapshot(scope, item, text, (), "synthetic-source-context", captured.fingerprint)
    return url, identity, owner, second, memories, conversations, preferences, loader, snap
