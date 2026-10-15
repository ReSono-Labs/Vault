"""Bounded handles to the existing loop-owned streams; never another input buffer."""
import asyncio
from dataclasses import dataclass
from threading import Lock

from .current_state import CurrentLiveState
from .preferences import LiveMemoryPreference
from .voicemem_stream import VoiceMemStream


@dataclass(frozen=True, slots=True)
class _Handle:
    stream: VoiceMemStream
    loop: asyncio.AbstractEventLoop
    epoch: int


class ScopedStreamRegistry:
    def __init__(self, *, capacity: int):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Explicit positive stream capacity required.")
        self.capacity = capacity
        self._lock = Lock()
        self._handles: dict[tuple[str, ...], _Handle] = {}

    @staticmethod
    def _key(state: CurrentLiveState, utterance_id: str):
        if (not isinstance(utterance_id, str) or not utterance_id
                or utterance_id != utterance_id.strip()):
            raise ValueError("Utterance identity required.")
        scope = state.scope
        return (scope.user_id, scope.workspace_id, scope.local_session_id,
                state.conversation_id, state.segment_id, utterance_id)

    def register(self, state: CurrentLiveState, utterance_id: str, stream: VoiceMemStream):
        loop = asyncio.get_running_loop()
        if (not state.preference.enabled or state.preference.user_id != state.scope.user_id
                or state.preference.workspace_id != state.scope.workspace_id):
            raise ValueError("Current enabled scoped preference required.")
        key = self._key(state, utterance_id)
        owner = (state.scope, state.conversation_id, state.segment_id, utterance_id)
        if not isinstance(stream, VoiceMemStream) or stream._owner != owner or stream._closed:
            raise ValueError("Stream must already be bound to this live input owner.")
        if stream._spec is not None and stream._spec.get_loop() is not loop:
            raise ValueError("Only the owning loop may register a running stream.")
        with self._lock:
            if key in self._handles or any(handle.stream is stream for handle in self._handles.values()):
                raise ValueError("Stream already registered.")
            if len(self._handles) >= self.capacity:
                raise ValueError("Stream capacity reached.")
            self._handles[key] = _Handle(stream, loop, state.preference.epoch)
        return key

    def unregister(self, key):
        loop = asyncio.get_running_loop()
        with self._lock:
            handle = self._handles.get(key)
            if handle is not None and handle.loop is not loop:
                raise ValueError("Only the owning loop may unregister a stream.")
            return self._handles.pop(key, None) is not None

    def preference_changed(self, preference: LiveMemoryPreference):
        with self._lock:
            affected = [key for key, handle in self._handles.items()
                        if key[:2] == (preference.user_id, preference.workspace_id)
                        and (not preference.enabled or handle.epoch != preference.epoch)]
            handles = [self._handles.pop(key) for key in affected]
        failed = False
        for handle in handles:
            try:
                handle.loop.call_soon_threadsafe(handle.stream.invalidate)
            except RuntimeError:
                failed = True
        if failed:
            raise RuntimeError("An owning live-input loop is unavailable.")
