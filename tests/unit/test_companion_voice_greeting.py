"""Link Companion greeting: the phone's /connected and Vault's sideband open race; the greeting must survive both orders."""
import asyncio
import threading
from time import monotonic, sleep
from types import SimpleNamespace

from app.vault_runtime.voice.companion import CompanionVoiceService

GREETING = {"type": "response.create", "response": {"instructions": 'Say exactly: "Good morning Christian"'}}


class Principal:
    user_id, workspace_id, session_id, display_name = "user-1", "workspace-1", "local-1", "Christian"


class Coordinator:
    def start(self, **_kwargs):
        return SimpleNamespace(
            session=SimpleNamespace(voice_session_id="voice-1"),
            provider=SimpleNamespace(call_id="rtc_1", sdp_answer="answer", session_update_event={}),
            context=SimpleNamespace(display_name="Christian"),
        )


class Sideband:
    def __init__(self):
        self.sent, self.closed = [], False

    async def recv(self):
        await asyncio.sleep(0.05)
        raise asyncio.TimeoutError

    async def send(self, raw):
        import json
        self.sent.append(json.loads(raw))

    async def close(self):
        self.closed = True


def _service(open_gate: threading.Event):
    band = Sideband()

    async def connect(call_id, token):
        await asyncio.to_thread(open_gate.wait, 5)  # Holds the sideband open back, like a slow OpenAI connect.
        return band

    service = CompanionVoiceService(
        coordinator=Coordinator(),
        credential_resolver=lambda principal, provider, **_: SimpleNamespace(value="sk-test", auth_method="api_key"),
        credential_status=lambda principal, provider: {"configured": True, "apiKeyConnected": True},
        voice_tools=None, voice_learning=SimpleNamespace(capture=lambda **_: None),
        recent_session_open=lambda principal: False, finish_close=lambda principal, sid: None,
        greeting=lambda name: GREETING, connect=connect, hangup=lambda call_id, token: None,
    )
    return service, band


def _until(predicate, seconds=5.0):
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.02)
    raise AssertionError("condition not reached")


def _greetings(band):
    return [event for event in band.sent if event == GREETING]


def test_greeting_survives_phone_connected_before_sideband_opens():
    gate = threading.Event()
    service, band = _service(gate)
    principal = Principal()
    sid = service.start(principal, offer_sdp="offer")["sessionId"]

    service.connected(principal, sid)  # Phone audio is up; Vault's sideband is still connecting.
    sleep(0.2)
    assert _greetings(band) == []
    assert service.call(principal, sid).greeting == GREETING, "greeting is kept, not dropped"

    gate.set()
    _until(lambda: _greetings(band))
    assert len(_greetings(band)) == 1
    assert service.close(principal, sid) == "closed"


def test_greeting_sent_when_sideband_opens_first():
    gate = threading.Event()
    gate.set()
    service, band = _service(gate)
    principal = Principal()
    sid = service.start(principal, offer_sdp="offer")["sessionId"]
    call = service.call(principal, sid)
    _until(lambda: call.sender is not None)
    sleep(0.1)
    assert _greetings(band) == [], "no greeting before the phone's audio is up"

    service.connected(principal, sid)
    _until(lambda: _greetings(band))
    service.connected(principal, sid)  # A repeated /connected never greets twice.
    sleep(0.2)
    assert len(_greetings(band)) == 1
    assert service.close(principal, sid) == "closed"


def test_no_greeting_after_close():
    gate = threading.Event()
    service, band = _service(gate)
    principal = Principal()
    sid = service.start(principal, offer_sdp="offer")["sessionId"]
    service.connected(principal, sid)
    call = service.call(principal, sid)
    call.closing = "ended"
    gate.set()
    _until(lambda: call.done.is_set())
    assert _greetings(band) == []


def test_greeting_is_spoken_with_turn_detection_off_then_restored():
    """The mic hearing the greeting at the start of a call must not start a new reply and cut it off."""
    import app.vault_runtime.voice.companion as companion
    detection = {"type": "server_vad", "create_response": True, "interrupt_response": False}
    gate = threading.Event()
    service, band = _service(gate)
    service._coordinator.start = lambda **_kw: SimpleNamespace(
        session=SimpleNamespace(voice_session_id="voice-1"),
        provider=SimpleNamespace(call_id="rtc_1", sdp_answer="answer",
                                 session_update_event={"session": {"audio": {"input": {"turn_detection": detection}}}}),
        context=SimpleNamespace(display_name="Christian"))
    old = companion.GREETING_GUARD_MAX
    companion.GREETING_GUARD_MAX = 0.4
    try:
        principal = Principal()
        sid = service.start(principal, offer_sdp="offer")["sessionId"]
        service.connected(principal, sid)
        gate.set()
        _until(lambda: any(e.get("type") == "input_audio_buffer.clear" for e in band.sent))
        kinds = [(e.get("type"), ((e.get("session") or {}).get("audio") or {}).get("input", {}).get("turn_detection", "-"))
                 for e in band.sent]
        off = kinds.index(("session.update", None))
        assert band.sent.index(GREETING) == off + 1
        assert ("session.update", detection) in kinds[kinds.index(("input_audio_buffer.clear", "-")):]
    finally:
        companion.GREETING_GUARD_MAX = old
        service.close(principal, sid)
