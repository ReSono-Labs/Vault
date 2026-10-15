"""Transient authenticated Chat host for the existing VoiceMem preparation loop."""
import asyncio
from dataclasses import replace
from hashlib import sha256
import json
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

from app.vault_runtime.conversation.contracts import ConflictError, InputError, identifier
from app.vault_runtime.decision_routing.contracts import (
    CandidateChoice, EvidenceRef, InputIdentity, ScopedPrincipalRef, Selected, SelectionRequest,
)
from app.vault_runtime.decision_routing.openai_transport import OpenAIDecisionTransport
from app.vault_runtime.decision_routing.selector import DecisionSelector, candidate_set_fingerprint
from app.vault_runtime.memory_search.indexed import PgvectorMemorySearchBackend
from app.vault_runtime.memory_search.postgres import QueryOptions
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext
from .canonical_ports import CanonicalPreparationPorts
from .contracts import InputSnapshot, PreparedContext, StalePreparation
from .current_state import CurrentStateGuard, LiveStateLoader
from .preparation import ParallelPreparation, WorkerBudget
from .stream_registry import ScopedStreamRegistry
from .voicemem_stream import VoiceMemStream


# Tool families offered to live selection (goal, mode, skill and plugin tools are excluded).
_LIVE_TOOL_PREFIXES = ("memory_", "contacts_", "web_", "agent2agent_", "a2a_", "email_", "calendar_", "workspace_")
# Live tool selection runs while the user is still speaking, at most once per interval on the latest
# words, so a route is ready before the turn ends. Memory recall is not throttled.
SELECTION_INTERVAL_S = 1.0
SELECTION_DEADLINE_S = 4.0


def live_tool_candidate(name):
    return name.startswith(_LIVE_TOOL_PREFIXES)


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ChatPreparationRuntime:
    def __init__(self, *, database_url, store, memories, preferences, credentials, catalog,
                 authority, user_ids, transport_factory=OpenAIDecisionTransport):
        self.store, self.memories, self.preferences = store, memories, preferences
        self.credentials, self.catalog, self.authority = credentials, catalog, authority
        self.transport_factory = transport_factory
        self.loader = LiveStateLoader(database_url=database_url, memories=memories._repository,
                                      preferences=preferences)
        self.search = PgvectorMemorySearchBackend(memories=memories._repository,
            options=QueryOptions(timeout_ms=1500, ef_search=100, max_scan_tuples=20000))
        self.registry = ScopedStreamRegistry(capacity=16)
        self._entries, self._fences = {}, {}
        self._user_ids = user_ids
        self.maintenance = None
        self.learned_queries = None
        self._loop = asyncio.new_event_loop()
        self._started, self._closed = Event(), False
        self._thread = Thread(target=self._run, name="vault-live-preparation", daemon=True)
        self._thread.start()
        self._started.wait(5)

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self.workers = WorkerBudget(global_limit=4, user_limits={u: 2 for u in self._user_ids} or {"startup": 2})
        self._started.set()
        self._loop.run_forever()
        self._loop.close()

    def _call(self, coroutine):
        if self._closed:
            coroutine.close()
            raise ConflictError("Live preparation is stopping.")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=10)
        except TimeoutError:
            future.cancel()
            raise ConflictError("Live preparation is busy.") from None

    @staticmethod
    def _key(principal, conversation_id):
        return (principal.user_id, principal.workspace_id, principal.session_id, conversation_id)

    def _tools(self, principal):
        context = ToolInvocationContext(agent=AgentKind.VOICE, user_id=principal.user_id,
            workspace_id=principal.workspace_id, local_session_id=principal.session_id,
            tool_call_id="preparation-only")
        definitions = tuple(d for d in self.catalog.definitions_for(AgentKind.VOICE,
            user_id=principal.user_id, workspace_id=principal.workspace_id)
            if d.tool_id != "builtin.voice.mode-switch.v1"
            and live_tool_candidate(d.name))
        return self.authority.authorized_definitions(definitions, context)

    def _tool_fingerprint(self, principal):
        definitions = self.catalog.metadata_for(AgentKind.VOICE, user_id=principal.user_id,
                                                workspace_id=principal.workspace_id)
        context = ToolInvocationContext(agent=AgentKind.VOICE,user_id=principal.user_id,
            workspace_id=principal.workspace_id,local_session_id=principal.session_id,tool_call_id="preparation-only")
        authorized = self.authority.authorized_definitions(definitions,context)
        return fingerprint([[(d.tool_id,d.name,d.description,d.effect_class,d.input_schema) for d in definitions],
                            [d.tool_id for d in authorized]])

    async def _remove(self, key):
        entry = self._entries.pop(key, None)
        if entry and entry.stream is not None and entry.last_snapshot is not None:
            # Content-free per-utterance diagnostic: what live preparation actually did.
            entry.stream.preparation.emit("utterance_summary", entry.last_snapshot, summary=dict(entry.counts))
        if entry:
            if entry.registry_key:
                self.registry.unregister(entry.registry_key)
            entry.stream.invalidate()
            # Underlying jobs remain counted by WorkerBudget until completion.
            task = asyncio.create_task(entry.stream.wait_closed())
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())

    async def _expire(self):
        now = monotonic()
        for key, entry in tuple(self._entries.items()):
            if now-entry.touched > 90:
                await self._remove(key)
        self._fences = {k: v for k, v in self._fences.items() if now-v[1] < 120}

    def update(self, principal, conversation_id, payload):
        return self._call(self._update(principal, conversation_id, payload))

    async def _update(self, principal, conversation_id, payload):
        self.workers.register_user(principal.user_id, limit=2)
        if set(payload) != {"utteranceId", "revision", "text", "composing"}:
            raise InputError("Invalid draft fields.")
        utterance, revision, text, composing = (payload[k] for k in ("utteranceId", "revision", "text", "composing"))
        utterance = identifier(utterance)
        if (type(revision) is not int or not 0 <= revision <= 2**31-1 or type(composing) is not bool
                or type(text) is not str or "\0" in text or len(text.encode("utf-8")) > 32768):
            raise InputError("Invalid bounded draft revision.")
        await self._expire()
        key = self._key(principal, conversation_id)
        if self._fences.get((*key, utterance)):
            raise ConflictError("This draft has been submitted or discarded.")
        conversation = await self.workers.run(principal.user_id, self.store.load, principal, conversation_id)
        if self.maintenance is not None and not self.maintenance.ready.is_set():
            return {"revision": revision, "state": self.maintenance.state}
        segment = next((s for s in reversed(conversation.segments) if s.state == "open"), None)
        if conversation.state != "open" or segment is None:
            raise ConflictError("Conversation is not open.")
        entry = self._entries.get(key)
        if entry and entry.stream and entry.stream._closed:
            await self._remove(key)
            entry = None
        if entry and entry.utterance != utterance:
            self._fences[(*key, entry.utterance)] = (True, monotonic())
            await self._remove(key)
            entry = None
        if entry and revision <= entry.revision:
            if revision == entry.revision and text == entry.text and composing == entry.composing:
                return {"revision": revision, "state": "accepted"}
            raise ConflictError("Out-of-order or conflicting draft revision.")
        if entry is None:
            if len(self._entries) >= 16:
                raise ConflictError("Live preparation capacity reached.")
            # memory_view/tool_view: last authorized result for this utterance. They survive new
            # revisions (live speech outruns lookups) until replaced, emptied input or new utterance.
            entry = SimpleNamespace(utterance=utterance, revision=-1, text="", composing=False,
                touched=monotonic(), stream=None, registry_key=None, tool_status="waiting",
                memory_view=None, tool_view=None, last_snapshot=None, publishable=None,
                next_selection=0.0, last_selection=None,
                counts=dict(revisions=0, memory_updates=0, tool_updates=0, selections=0, deliveries=0))
            self._entries[key] = entry
        entry.revision, entry.text, entry.composing, entry.touched = revision, text, composing, monotonic()
        entry.counts["revisions"] += 1
        if not text.strip():
            entry.memory_view = entry.tool_view = None  # Deleted input keeps nothing.
            entry.tool_status = "waiting"
        entry.learned = None
        entry.decision_vector = None
        # Immediately invalidate ready state before any potentially blocking reads.
        if entry.stream:
            entry.stream._last_memory = None
            entry.stream._current = None
        scope = ScopedPrincipalRef(*key[:3])
        identity = InputIdentity(conversation_id, segment.segment_id, utterance, revision, None,
                                 sha256(text.encode()).hexdigest())
        state = await self.workers.run(principal.user_id, self.loader.capture, scope, identity)
        # Prepare the upcoming input. Canonical history version remains a validity
        # fence, but old turn text must not become the live search query.
        sources = ()
        tool_fp = await self.workers.run(principal.user_id, self._tool_fingerprint, principal)
        if self._entries.get(key) is not entry or entry.revision != revision:
            return {"revision": revision, "state": "stale"}
        context_fp = fingerprint([state.history_version, tool_fp])
        snapshot = InputSnapshot(scope, identity, text, sources, context_fp, state.fingerprint)
        entry.last_snapshot = snapshot
        if entry.stream is None:
            def external_current(candidate, prepared):
                current = (self._entries.get(key) is entry and entry.revision == candidate.identity.revision
                    and entry.text == candidate.text and entry.context_fp == candidate.context_fingerprint
                    and self._tool_fingerprint(principal) == entry.tool_fp)
                learned = getattr(entry,"learned",None)
                if current and learned is not None and learned[0]==replace(candidate.identity,turn_id=learned[0].turn_id):
                    try:
                        fresh = self.learned_queries.retrieve(principal,vector=learned[1],
                            example_limit=20,decision_limit=5)
                        current = fresh==learned[2]
                    except Exception:
                        current = False
                    if prepared is not None:
                        return current and all(c in learned[2].choices for c in prepared.decisions)
                if not current or prepared is None:
                    return current
                metadata = {d.tool_id:d for d in self.catalog.metadata_for(AgentKind.VOICE,
                    user_id=principal.user_id,workspace_id=principal.workspace_id)}
                return all(c.definition_id in metadata and metadata[c.definition_id].visible_in(
                    user_id=principal.user_id,workspace_id=principal.workspace_id) for c in prepared.decisions)
            guard = CurrentStateGuard(loader=self.loader, external_current=external_current)
            def decisions(candidate, memories, retained):
                definitions = self._tools(principal)
                if len(definitions) > 100:
                    entry.tool_status = "catalog_too_large"
                    return ()
                choices = tuple(CandidateChoice(d.name, d.tool_id, 1,
                    f"Propose {d.name} ({d.effect_class}): {d.description}") for d in definitions)
                generation_id = None
                capability_fp = entry.tool_fp
                contextual = ()
                request = SelectionRequest(str(uuid4()), candidate.scope, candidate.identity, "provisional",
                    candidate.text, contextual, candidate.context_fingerprint, choices,
                    candidate_set_fingerprint(choices), capability_fp, generation_id, 1, True)
                selector = DecisionSelector(transport=self.transport_factory(
                    credential_resolver=self.credentials, principal=principal), clock=SimpleNamespace(now=monotonic))
                entry.counts["selections"] += 1
                if entry.tool_view is None:
                    entry.tool_status = "choosing"
                try:
                    # Same utterance and current authority are required; newer words are not. Speech
                    # outruns selection, and the next throttled call refreshes the route.
                    result = selector.choose(request, deadline=monotonic()+SELECTION_DEADLINE_S,
                        cancellation=SimpleNamespace(is_cancelled=False),
                        is_current=lambda _: sticky_guard.is_current(candidate, None))
                except Exception:
                    entry.last_selection = "failed"
                    return ()
                if isinstance(result, Selected):
                    entry.tool_status = entry.last_selection = "proposed"
                    return tuple(c for c in choices if c.definition_id == result.definition_id)
                entry.last_selection = result.reason
                if result.reason == "no_supported_choice":
                    entry.tool_status = "no_tool"
                return ()
            ports = CanonicalPreparationPorts(guard=guard, search_backend=self.search, limit=8,
                query_builder=lambda s: s.text,
                decision_retriever=decisions, embedder_factory=self._embedder,
                decisions_depend_on_memory=False)
            # Authority-only check for the sticky views: same live entry and utterance, plus the
            # canonical scope/preference/memory-version checks. Exact text/revision is not required.
            sticky_guard = CurrentStateGuard(loader=self.loader, external_current=lambda candidate, _prepared:
                self._entries.get(key) is entry and entry.utterance == candidate.identity.utterance_id
                and entry.stream is not None and not entry.stream._closed)
            entry.publishable = lambda prepared: sticky_guard.is_current(prepared.snapshot, prepared)
            def publish_memory(prepared):
                old = entry.memory_view
                if not prepared.memories or (old is not None
                        and old.snapshot.identity.revision > prepared.snapshot.identity.revision):
                    return  # An empty or older lookup never erases a newer good result.
                if old is None or [m.memory.memory_id for m in old.memories] != [m.memory.memory_id for m in prepared.memories]:
                    entry.counts["memory_updates"] += 1
                entry.memory_view = prepared
            def publish_tools(prepared):
                old = entry.tool_view
                if old is not None and old.snapshot.identity.revision > prepared.snapshot.identity.revision:
                    return
                if not prepared.decisions and entry.last_selection != "no_supported_choice":
                    return  # A failed, timed-out or superseded call keeps the last good route.
                if old is None or old.decisions != prepared.decisions:
                    entry.counts["tool_updates"] += 1
                entry.tool_view = prepared
            async def throttle(candidate):
                # At most one selection per interval per utterance. A revision superseded while it
                # waits is skipped (no paid call); the newest one runs as soon as the interval allows,
                # so the final words of a turn are always evaluated.
                if candidate.identity.turn_id is None:
                    while monotonic() < entry.next_selection:
                        await asyncio.sleep(0.05)
                        if self._entries.get(key) is not entry or entry.revision != candidate.identity.revision:
                            raise StalePreparation()
                entry.next_selection = monotonic() + SELECTION_INTERVAL_S
            entry.stream = VoiceMemStream(ParallelPreparation(ports=ports, workers=self.workers,
                on_memory=publish_memory, on_decisions=publish_tools,
                publishable=entry.publishable, decision_gate=throttle),
                debounce_s=.1, max_wait_s=.8,
                meaningful=lambda s: len(s.text.strip()) >= 12 and len(s.text.split()) >= 3)
        entry.context_fp, entry.tool_fp = context_fp, tool_fp
        await entry.stream.feed_partial(snapshot, composing=composing, enabled=state.preference.enabled)
        if state.preference.enabled and entry.registry_key is None:
            entry.registry_key = self.registry.register(state, utterance, entry.stream)
        return {"revision": revision, "state": "accepted", "enabled": state.preference.enabled}

    def _embedder(self, user_id, workspace_id):
        factory = self.memories._embedder_factory
        if factory is None:
            return None
        embedder = factory(user_id, workspace_id)
        # Local long inputs require multiple tokenizer-bounded windows. The
        # stream's existing finalization deadline still protects Chat latency;
        # its bounded worker may finish preparation while the user pauses.
        if getattr(embedder, "provider_key", None) == "ollama":
            return embedder
        return embedder.with_timeout(2) if callable(getattr(embedder,"with_timeout",None)) else embedder

    def status(self, principal, conversation_id, utterance, revision):
        return self._call(self._status(principal, conversation_id, utterance, revision))

    async def _current_view(self, principal, entry, attribute):
        view = getattr(entry, attribute)
        if view is None or entry.publishable is None:
            return None
        if not await self.workers.run(principal.user_id, entry.publishable, view):
            setattr(entry, attribute, None)  # Revoked, forgotten or out of scope: drop it.
            return None
        return getattr(entry, attribute)

    async def _status(self, principal, conversation_id, utterance, revision):
        self.workers.register_user(principal.user_id, limit=2)
        await self.workers.run(principal.user_id, self.store.load, principal, conversation_id)
        if self.maintenance is not None and not self.maintenance.ready.is_set():
            return dict(revision=revision,state=self.maintenance.state,memories=[],tools=[])
        key = self._key(principal, conversation_id)
        entry = self._entries.get(key)
        # "stale" only answers a superseded revision or utterance; clients poll their latest.
        empty = dict(revision=revision, state="stale", memories=[], tools=[])
        if not entry or entry.utterance != utterance or entry.revision != revision or entry.stream is None:
            return empty
        entry.touched = monotonic()
        stream = entry.stream
        prepared = await stream.ready()
        if prepared:
            state = "ready"
            publish = prepared.memories and (entry.memory_view is None
                or entry.memory_view.snapshot.identity.revision <= prepared.snapshot.identity.revision)
            if publish:
                entry.memory_view = prepared
            entry.tool_view = prepared
        elif stream._closed:
            state = "off"
        elif stream.failure:
            state = stream.failure
        elif (not entry.text.strip() or entry.composing or len(entry.text.strip()) < 12
                or len(entry.text.split()) < 3):
            state = "waiting"
        elif stream._spec is None or not stream._spec.done():
            state = "searching"
        else:
            state = "settled"  # No more work for this revision; showing the last good result.
        memory_view = await self._current_view(principal, entry, "memory_view")
        tool_view = await self._current_view(principal, entry, "tool_view")
        learned = getattr(entry, "learned", None)
        return dict(revision=revision, state=state, toolState=entry.tool_status,
            memories=[dict(id=m.memory.memory_id, text=m.memory.content_text, methods=m.match_methods)
                      for m in (memory_view.memories if memory_view else ())],
            tools=[dict(id=c.definition_id, name=c.value, description=c.applicability_description,
                        kind="learned_rule" if learned and learned[0] == tool_view.snapshot.identity
                        and c in learned[2].choices else "catalog_proposal")
                   for c in (tool_view.decisions if tool_view else ())])

    def delivered(self, principal, conversation_id, utterance, memory_count, tool_count=0):
        return self._call(self._delivered(principal, conversation_id, utterance, memory_count, tool_count))

    async def _delivered(self, principal, conversation_id, utterance, memory_count, tool_count=0):
        """Client report that live memory/tool route was applied to the agent; counted, never content."""
        if (type(memory_count) is not int or not 0 <= memory_count <= 64
                or type(tool_count) is not int or not 0 <= tool_count <= 8):
            raise InputError("Invalid delivered counts.")
        entry = self._entries.get(self._key(principal, conversation_id))
        if entry and entry.utterance == identifier(utterance) and entry.last_snapshot is not None:
            entry.counts["deliveries"] += 1
            tool = entry.tool_view.decisions[0].definition_id if tool_count and entry.tool_view and entry.tool_view.decisions else None
            entry.stream.preparation.emit("memory_delivered", entry.last_snapshot, memory_count=memory_count,
                decision_count=tool_count, definition_id=tool)
        return {}

    def discard(self, principal, conversation_id, utterance=None):
        return self._call(self._discard(principal, conversation_id, utterance))

    def take_final(self, principal, turn, *, utterance=None):
        return self._call(self._take_final(principal, turn,utterance))

    async def _take_final(self, principal, turn,utterance=None):
        key = self._key(principal, turn.conversation_id)
        entry = self._entries.get(key)
        if entry is None or (utterance is not None and entry.utterance!=utterance):
            return None
        self._fences[(*key, entry.utterance)] = (True, monotonic())
        try:
            snapshot = entry.stream._current if entry.stream else None
            if snapshot is None or snapshot.text != turn.input_text or snapshot.identity.segment_id != turn.segment_id:
                return None
            final = replace(snapshot, identity=replace(snapshot.identity, turn_id=turn.turn_id))
            # Existing guard verifies actual immutable final fingerprint, pre-submit
            # history, memory epochs, current preference/session and current grants.
            result = await entry.stream.finalize(final, timeout_s=1.5)
            if result is not None and result.decisions:
                return result
            # Send often lands before a fresh selection finishes. Hand the model the route chosen
            # while the user typed (same utterance, authority rechecked) as a provisional hint.
            view = entry.tool_view
            if (view is None or not view.decisions or entry.publishable is None
                    or not await self.workers.run(principal.user_id, entry.publishable, view)):
                return result
            return (replace(result, decisions=view.decisions) if result is not None
                    else PreparedContext(final, (), view.decisions))
        finally:
            await self._remove(key)

    async def _discard(self, principal, conversation_id, utterance):
        self.workers.register_user(principal.user_id, limit=2)
        await self.workers.run(principal.user_id, self.store.load, principal, conversation_id)
        key = self._key(principal, conversation_id)
        entry = self._entries.get(key)
        if utterance:
            self._fences[(*key, identifier(utterance))] = (True, monotonic())
        if entry and (utterance is None or utterance == entry.utterance):
            self._fences[(*key, entry.utterance)] = (True, monotonic())
            await self._remove(key)
        return {}

    def close(self):
        if self.maintenance is not None:
            self.maintenance.close()
        async def drain():
            for key in tuple(self._entries):
                await self._remove(key)
            await self.workers.drain()
        if not self._closed:
            self._closed = True
            future = asyncio.run_coroutine_threadsafe(drain(), self._loop)
            try:
                future.result(timeout=10)
            finally:
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._thread.join(timeout=2)
