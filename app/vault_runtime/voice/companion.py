"""Link Companion live voice: Vault creates the OpenAI call and controls it over the call_id sideband.

The phone only carries audio (WebRTC, directly to OpenAI) and shows what Vault reports. Vault keeps the
credential, builds the session (instructions, memory context, tools, modes), runs tools locally, records
transcript evidence through the same capture path as browser Voice, enforces caps and closes the call.
Nothing provider-specific, secret or internal reaches the phone; phone events are display-only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

SIDEBAND_URL = "wss://api.openai.com/v1/realtime?call_id={call_id}"
HANGUP_URL = "https://api.openai.com/v1/realtime/calls/{call_id}/hangup"
MAX_SECONDS = 30 * 60
IDLE_SECONDS = 5 * 60
MAX_PHONE_EVENTS = 500
USER_FINAL = {"conversation.item.input_audio_transcription.completed",
              "conversation.item.input_audio_transcript.completed"}
ASSISTANT_FINAL = {"response.audio_transcript.done", "response.output_audio_transcript.done"}


class CompanionVoiceError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code, self.retryable = code, retryable


@dataclass
class CompanionCall:
    session_id: str
    principal: Any
    call_id: str
    token: str = field(repr=False)
    greeting: dict[str, Any] | None
    max_seconds: int
    idle_seconds: int
    started: float = field(default_factory=monotonic)
    last_activity: float = field(default_factory=monotonic)
    events: list[dict[str, Any]] = field(default_factory=list)
    sequence: int = 0
    closing: str | None = None
    closed: bool = False
    entry_index: int = 0
    last_utterance: tuple[str, int] | None = None
    condition: threading.Condition = field(default_factory=threading.Condition)
    done: threading.Event = field(default_factory=threading.Event)
    loop: asyncio.AbstractEventLoop | None = None
    sender: Callable[[dict[str, Any]], Any] | None = None

    def emit(self, kind: str, **fields: Any) -> None:
        with self.condition:
            self.sequence += 1
            self.events.append({"seq": self.sequence, "type": kind, **fields})
            del self.events[:-MAX_PHONE_EVENTS]
            self.condition.notify_all()

    def wait(self, after: int, timeout: float) -> tuple[list[dict[str, Any]], int]:
        with self.condition:
            if self.sequence <= after and not self.closed:
                self.condition.wait(timeout)
            return [e for e in self.events if e["seq"] > after], self.sequence

    def send(self, event: dict[str, Any]) -> bool:
        """Thread-safe send on the sideband (False when the control connection is gone)."""
        loop, sender = self.loop, self.sender
        if loop is None or sender is None or loop.is_closed():
            return False
        asyncio.run_coroutine_threadsafe(sender(event), loop)
        return True


async def _default_connect(call_id: str, token: str):
    import websockets
    return await websockets.connect(SIDEBAND_URL.format(call_id=call_id),
                                    additional_headers={"Authorization": f"Bearer {token}"},
                                    open_timeout=10, max_size=8 * 1024 * 1024)


def _default_hangup(call_id: str, token: str) -> None:
    import httpx
    httpx.post(HANGUP_URL.format(call_id=call_id), headers={"Authorization": f"Bearer {token}"}, timeout=10)


class CompanionVoiceService:
    def __init__(self, *, coordinator: Any, credential_resolver: Callable[..., Any], credential_status: Callable[..., dict],
                 voice_tools: Any, voice_learning: Any, recent_session_open: Callable[[Any], bool],
                 finish_close: Callable[[Any, str], Any], greeting: Callable[[str], dict | None],
                 connect: Callable[[str, str], Any] = _default_connect,
                 hangup: Callable[[str, str], None] = _default_hangup,
                 max_seconds: int = MAX_SECONDS, idle_seconds: int = IDLE_SECONDS) -> None:
        self._coordinator, self._resolve, self._status = coordinator, credential_resolver, credential_status
        self._tools, self._learning, self._recent_open = voice_tools, voice_learning, recent_session_open
        self._finish_close, self._greeting = finish_close, greeting
        self._connect, self._hangup = connect, hangup
        self.max_seconds, self.idle_seconds = max_seconds, idle_seconds
        self._calls: dict[str, CompanionCall] = {}
        self._lock = threading.Lock()

    # ── account rules ──────────────────────────────────────────────────────────
    def active_for(self, user_id: str, workspace_id: str) -> CompanionCall | None:
        with self._lock:
            return next((c for c in self._calls.values() if not c.closed
                         and (c.principal.user_id, c.principal.workspace_id) == (user_id, workspace_id)), None)

    def readiness(self, principal: Any) -> str | None:
        """None when live voice can start, else a safe reason code."""
        try:
            status = self._status(principal, "openai")
        except Exception:
            return "not_ready"
        if not status.get("configured"):
            return "not_ready"
        if not (status.get("apiKeyConnected") or status.get("oauthConnected")):
            return "not_ready"
        return None

    # ── lifecycle ──────────────────────────────────────────────────────────────
    def start(self, principal: Any, *, offer_sdp: str) -> dict[str, Any]:
        reason = self.readiness(principal)
        if reason:
            raise CompanionVoiceError(reason)
        with self._lock:
            if any(not c.closed and (c.principal.user_id, c.principal.workspace_id)
                   == (principal.user_id, principal.workspace_id) for c in self._calls.values()):
                raise CompanionVoiceError("busy", retryable=True)
            if self._recent_open(principal):
                raise CompanionVoiceError("busy", retryable=True)
            reservation = f"reserved-{uuid4()}"
            self._calls[reservation] = CompanionCall(reservation, principal, "", "", None, 0, 0)
        try:
            status = self._status(principal, "openai")
            credential = self._resolve(principal, "openai")
            started = self._coordinator.start(principal=principal, provider_key="openai",
                model_key=str(status.get("modelKey") or "gpt-realtime"), connection_mode="webrtc",
                credential=credential, voice=str(status.get("voice") or "marin"),
                offer_sdp=offer_sdp, server_controlled=True)
        except CompanionVoiceError:
            raise
        except Exception as exc:
            code = "provider_refused" if "rejected" in str(exc).lower() or "401" in str(exc) or "403" in str(exc) else "provider_unavailable"
            logger.warning("companion_voice_start_failed", extra={"code": code})
            raise CompanionVoiceError(code, retryable=code == "provider_unavailable") from None
        finally:
            with self._lock:
                self._calls.pop(reservation, None)
        call = CompanionCall(started.session.voice_session_id, principal, started.provider.call_id or "",
                             credential.value, self._greeting(started.context.display_name),
                             self.max_seconds, self.idle_seconds)
        with self._lock:
            self._calls[call.session_id] = call
        threading.Thread(target=self._run, args=(call,), name=f"companion-voice-{call.session_id[:8]}",
                         daemon=True).start()
        return {"sessionId": call.session_id, "sdpAnswer": started.provider.sdp_answer,
                "maxSeconds": call.max_seconds, "idleSeconds": call.idle_seconds}

    def call(self, principal: Any, session_id: str) -> CompanionCall:
        with self._lock:
            call = self._calls.get(session_id)
        if call is None or (call.principal.user_id, call.principal.workspace_id) != (principal.user_id, principal.workspace_id):
            raise CompanionVoiceError("not_found")
        return call

    def connected(self, principal: Any, session_id: str) -> None:
        """The phone's media path is up: speak the greeting once (audio before this would be lost)."""
        call = self.call(principal, session_id)
        call.last_activity = monotonic()
        greeting, call.greeting = call.greeting, None
        if greeting and not call.closing:
            call.send(greeting)

    def close(self, principal: Any, session_id: str, *, reason: str = "ended", wait: float = 8.0) -> str:
        call = self.call(principal, session_id)
        call.closing = call.closing or reason
        call.done.wait(wait)
        return "closed" if call.done.is_set() else "closing"

    def shutdown(self) -> None:
        with self._lock:
            calls = list(self._calls.values())
        for call in calls:
            call.closing = call.closing or "vault_stopping"
        for call in calls:
            call.done.wait(5)

    # ── control loop ───────────────────────────────────────────────────────────
    def _run(self, call: CompanionCall) -> None:
        try:
            asyncio.run(self._control(call))
        except Exception:
            logger.warning("companion_voice_control_failed")  # No content or provider detail.
            call.closing = call.closing or "provider_unavailable"
        finally:
            self._finish(call)

    async def _control(self, call: CompanionCall) -> None:
        try:
            ws = await self._connect(call.call_id, call.token)
        except Exception:
            call.closing = call.closing or "provider_unavailable"
            return
        tools: asyncio.Queue = asyncio.Queue()
        call.loop = asyncio.get_running_loop()
        async def send(event: dict[str, Any]) -> None:
            await ws.send(json.dumps(event))
        call.sender = send
        worker = asyncio.create_task(self._tool_worker(call, tools, send))
        try:
            while not call.closing:
                now = monotonic()
                if now - call.started > call.max_seconds:
                    call.closing = "max_duration"
                    break
                if now - call.last_activity > call.idle_seconds:
                    call.closing = "idle"
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), 0.5)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    call.closing = call.closing or "provider_closed"
                    break
                try:
                    event = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if isinstance(event, dict):
                    await self._handle(call, event, tools)
        finally:
            worker.cancel()
            call.sender = None
            try:
                await ws.close()
            except Exception:
                pass

    async def _handle(self, call: CompanionCall, event: dict[str, Any], tools: asyncio.Queue) -> None:
        kind = str(event.get("type") or "")
        if kind == "session.updated" and not any(e["type"] == "ready" for e in call.events):
            call.emit("ready")
        elif kind == "input_audio_buffer.speech_started":
            call.last_activity = monotonic()
            call.emit("state", state="listening")
        elif kind in {"input_audio_buffer.speech_stopped", "response.created"}:
            call.last_activity = monotonic()
            call.emit("state", state="responding")
        if kind in {"response.done", "response.function_call_arguments.done"}:
            call.last_activity = monotonic()
            await self._capture(call, event, kind, "assistant")
            if kind == "response.done":
                call.emit("state", state="listening")
        if kind == "response.function_call_arguments.done":
            await tools.put(event)
        text = event.get("transcript") if isinstance(event.get("transcript"), str) else None
        if text and (kind in USER_FINAL or kind in ASSISTANT_FINAL):
            role = "user" if kind in USER_FINAL else "assistant"
            index = call.entry_index
            call.entry_index += 1
            if role == "user":
                call.last_utterance = (text, index)
            await self._capture(call, event, kind, role, text=text, index=index)
            call.emit("transcript", role=role, text=text)
        if kind == "error":
            code = (event.get("error") or {}).get("code") if isinstance(event.get("error"), dict) else None
            logger.info("companion_voice_provider_error", extra={"code": str(code or "unknown")[:64]})

    async def _capture(self, call: CompanionCall, event: dict, kind: str, role: str, *,
                       text: str | None = None, index: int | None = None) -> None:
        try:
            await asyncio.to_thread(self._learning.capture, principal=call.principal,
                voice_session_id=call.session_id,
                provider_event_id=str(event.get("event_id") or uuid4()), event_type=kind, role=role,
                transcript_text=text, transcript_entry_index=index, payload=event)
        except Exception:
            logger.warning("companion_voice_capture_failed", extra={"event_type": kind[:80]})

    async def _tool_worker(self, call: CompanionCall, tools: asyncio.Queue, send) -> None:
        from app.vault_runtime.system_agents.inventory import AgentKind
        from app.vault_runtime.tools.definitions import ToolInvocationContext
        while True:
            event = await tools.get()
            name, call_id = str(event.get("name") or ""), str(event.get("call_id") or "")
            if not name or not call_id:
                continue
            call.emit("tool", name=name, state="running")
            try:
                raw = event.get("arguments")
                arguments = json.loads(raw) if isinstance(raw, str) and raw.strip() else (raw if isinstance(raw, dict) else {})
                if not isinstance(arguments, dict):
                    raise ValueError("arguments")
                utterance = call.last_utterance
                context = ToolInvocationContext(agent=AgentKind.VOICE, user_id=call.principal.user_id,
                    workspace_id=call.principal.workspace_id, local_session_id=call.principal.session_id,
                    voice_session_id=call.session_id, tool_call_id=call_id,
                    user_utterance=utterance[0] if utterance else None,
                    user_utterance_id=utterance[1] if utterance else None)
                result = (await asyncio.to_thread(self._tools.invoke, name=name, arguments=arguments,
                                                  context=context)).mcp_result()
            except Exception:
                logger.warning("companion_voice_tool_failed", extra={"tool": name[:80]})
                result = {"isError": True, "content": [{"type": "text", "text": "The tool could not be completed."}]}
            update = result.pop("resonoSessionUpdate", None) if isinstance(result, dict) else None
            if isinstance(update, dict):
                await send(update)
                call.emit("mode")
            await send({"type": "conversation.item.create",
                        "item": {"type": "function_call_output", "call_id": call_id, "output": json.dumps(result)}})
            await send({"type": "response.create"})
            call.emit("tool", name=name, state="failed" if result.get("isError") else "completed")
            call.last_activity = monotonic()

    def _finish(self, call: CompanionCall) -> None:
        try:
            self._hangup(call.call_id, call.token)
        except Exception:
            logger.info("companion_voice_hangup_failed")
        try:
            self._finish_close(call.principal, call.session_id)
        except Exception:
            logger.warning("companion_voice_finalize_failed")
        call.token = ""
        with call.condition:
            call.closed = True
        call.emit("closed", reason=call.closing or "ended")
        call.done.set()
        with self._lock:
            # Keep the closed record briefly so the phone can read the final events.
            stale = [k for k, c in self._calls.items() if c.closed and monotonic() - c.started > c.max_seconds + 600]
            for key in stale:
                self._calls.pop(key, None)
