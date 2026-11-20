"""Canonical freshness only; relevance and source/procedure eligibility stay explicit."""
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from app.vault_runtime.conversation.contracts import identifier
from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.decision_routing.contracts import InputIdentity, ScopedPrincipalRef
from app.vault_runtime.local_identity.authority import has_current_session_scope
from app.vault_runtime.local_identity.repository import LocalSessionError
from app.vault_runtime.memory.models import MemoryRetrievalSnapshot
from app.vault_runtime.memory.repository import MemoryRepository
from .contracts import InputSnapshot, PreparedContext
from .preferences import LiveMemoryPreference, LiveMemoryPreferenceRepository


@dataclass(frozen=True, slots=True)
class CurrentLiveState:
    scope: ScopedPrincipalRef
    conversation_id: str
    segment_id: str
    history_version: int
    preference: LiveMemoryPreference
    memory: MemoryRetrievalSnapshot

    @property
    def fingerprint(self) -> str:
        payload = [1, self.scope.user_id, self.scope.workspace_id,
                   self.scope.local_session_id, self.conversation_id, self.segment_id,
                   self.history_version, self.preference.enabled,
                   self.preference.epoch, self.memory.fingerprint]
        return sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


class LiveStateLoader:
    def __init__(self, *, database_url: str, memories: MemoryRepository,
                 preferences: LiveMemoryPreferenceRepository,
                 connector: Callable[..., AbstractContextManager[Any]] | None = None):
        self._database_url, self._connector = database_url, connector
        self.memories, self.preferences = memories, preferences
        self.context_identity = ConversationRepository.context_identity_in_transaction

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def capture(self, scope: ScopedPrincipalRef, identity: InputIdentity,
                *, memory_ids: Iterable[str] = ()) -> CurrentLiveState:
        # Authentication refreshes the canonical session row during polling.
        # Keep the coherent snapshot/authority locks, retry only aborted SQL
        # snapshots, never embedding/model/tool work. Materialize once for retries.
        ids = tuple(memory_ids)
        for attempt in range(3):
            try:
                return self._capture(scope, identity, memory_ids=ids)
            except Exception as error:
                if getattr(error, "sqlstate", None) != "40001" or attempt == 2:
                    raise

    def _capture(self, scope: ScopedPrincipalRef, identity: InputIdentity,
                 *, memory_ids: Iterable[str] = ()) -> CurrentLiveState:
        ids = self.memories._retrieval_ids(memory_ids)
        values = [scope.user_id, scope.workspace_id, scope.local_session_id,
                  identity.conversation_id, identity.segment_id, identity.utterance_id]
        if identity.turn_id is not None:
            values.append(identity.turn_id)
        if any(identifier(value) != value for value in values):
            raise ValueError("Live identities must be canonical identifiers.")
        if type(identity.revision) is not int or identity.revision < 0:
            raise ValueError("Expected a nonnegative integer revision.")
        if (not isinstance(identity.input_fingerprint, str)
                or len(identity.input_fingerprint) != 64
                or any(char not in "0123456789abcdef" for char in identity.input_fingerprint)):
            raise ValueError("Expected an exact SHA256 input fingerprint.")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                # Every authenticated request touches the session row (last_seen_at). A row lock inside
                # this REPEATABLE READ snapshot then fails with a serialization error whenever a poll
                # lands concurrently, which made live preparation report "stale" at random. Provisional
                # checks read without locking (revocation is caught at the next check); a final turn
                # handoff keeps the lock.
                if not has_current_session_scope(cursor, user_id=scope.user_id,
                        workspace_id=scope.workspace_id, local_session_id=scope.local_session_id,
                        lock=identity.turn_id is not None):
                    raise LocalSessionError("Current local session scope is required.")
                history = self.context_identity(cursor, scope, identity)
                preference = self.preferences._get_cursor(cursor, user_id=scope.user_id,
                                                          workspace_id=scope.workspace_id)
                memory = self.memories._retrieval_snapshot_cursor(cursor, user_id=scope.user_id,
                    workspace_id=scope.workspace_id, memory_ids=ids)
        return CurrentLiveState(scope, identity.conversation_id, identity.segment_id,
                                history, preference, memory)


class CurrentStateGuard:
    def __init__(self, *, loader: LiveStateLoader,
                 external_current: Callable[[InputSnapshot, PreparedContext | None], bool]):
        if not callable(external_current):
            raise ValueError("Current source/procedural eligibility guard is required.")
        self.loader, self.external_current = loader, external_current

    def is_current(self, snapshot: InputSnapshot, prepared: PreparedContext | None) -> bool:
        if prepared is not None and prepared.snapshot != snapshot:
            return False
        try:
            if self.external_current(snapshot, prepared) is not True:
                return False
            matches = prepared.memories if prepared is not None else ()
            state = self.loader.capture(snapshot.scope, snapshot.identity,
                                        memory_ids=(match.memory.memory_id for match in matches))
            if not state.preference.enabled or state.fingerprint != snapshot.validity_fingerprint:
                return False
            current = {record.memory.memory_id: record.memory for record in state.memory.records}
            if any(current.get(match.memory.memory_id) != match.memory for match in matches):
                return False
            return True
        except Exception:
            return False  # No raw draft/database/provider payload logging.
