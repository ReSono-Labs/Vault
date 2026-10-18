"""Link Companion live voice over the real composed Vault; only OpenAI's call API and sideband are faked."""
import asyncio
import json
import queue
from time import monotonic, sleep

import psycopg

from tests.integration.test_mounted_voice_decision_review_postgres import mounted  # noqa: F401
from tests.integration.test_genui_conversation_postgres import grant
from tests.integration.test_link_companion_chat_postgres import _pair

OFFER = ("v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=group:BUNDLE 0 1\r\n"
         "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\nc=IN IP4 0.0.0.0\r\na=mid:0\r\na=sendrecv\r\na=rtpmap:111 opus/48000/2\r\n"
         "m=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\nc=IN IP4 0.0.0.0\r\na=mid:1\r\n")
ANSWER = "v=0\r\no=- 9 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"


class Sideband:
    """Stands in for wss://api.openai.com/v1/realtime?call_id=… ."""
    def __init__(self):
        self.inbox, self.sent, self.closed = queue.Queue(), [], False

    async def recv(self):
        try:
            return await asyncio.to_thread(self.inbox.get, True, 0.3)
        except queue.Empty:
            raise asyncio.TimeoutError from None

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def close(self):
        self.closed = True

    def push(self, **event):
        self.inbox.put(json.dumps(event))


def _voice(m, method, path, token, payload=None, query=""):
    headers = {"Authorization": f"Bearer {token}", "X-Link-Account": "acct-pseudonym"} if token else {}
    body = json.dumps(payload).encode() if payload is not None else b""
    return m.app.handle(method=method, target=f"/link-companion/voice/{path}{query}", headers=headers, body=body)


def _until(predicate, seconds=10):
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.05)
    raise AssertionError("condition not reached")


def test_companion_live_voice_end_to_end(mounted, monkeypatch):
    m = mounted
    grant(m)
    created_calls, hangups, sidebands = [], [], []

    def realtime_call(*, access_token, offer_sdp, session, organization=None):
        created_calls.append(dict(token_present=bool(access_token), session=session, offer=offer_sdp))
        return ANSWER, f"rtc_test{len(created_calls)}"

    monkeypatch.setattr("app.vault_runtime.voice.openai_realtime.OpenAIRealtimeProvider._realtime_call",
                        staticmethod(realtime_call))
    assert _voice(m, "GET", "health", None).payload == {"ready": False, "modes": [], "reason": "not_paired"}
    token, _ = _pair(m)
    assert _voice(m, "GET", "health", token).payload == {"ready": True, "modes": ["live"]}

    service = m.app._companion_voice_service()
    async def connect(call_id, credential):
        assert call_id.startswith("rtc_test") and credential == "sk-synthetic-test-only"
        sidebands.append(Sideband())
        return sidebands[-1]
    service._connect = connect
    service._hangup = lambda call_id, credential: hangups.append(call_id)

    assert _voice(m, "POST", "sessions", None, {"offerSdp": OFFER}).status_code == 401
    assert _voice(m, "POST", "sessions", token, {"offerSdp": "x" * 40_000}).payload["error"]["code"] in (
        "bound_exceeded", "rejected")
    started = _voice(m, "POST", "sessions", token, {"offerSdp": OFFER, "modeKey": "live",
                                                    "client": {"platform": "ios", "appVersion": "1.0"}})
    assert started.status_code == 201, started.payload
    body = started.payload
    sid = body["sessionId"]
    assert body["sdpAnswer"] == ANSWER and body["maxSeconds"] == 1800
    assert set(body) == {"sessionId", "sdpAnswer", "maxSeconds", "idleSeconds", "liveMemory", "liveTranscription", "control"}
    assert "sk-synthetic" not in json.dumps(body)
    session = created_calls[0]["session"]
    assert session["instructions"] and session["tools"], "Vault builds the full session itself"

    # One Voice session per account, whichever device asks.
    busy = _voice(m, "POST", "sessions", token, {"offerSdp": OFFER})
    assert busy.status_code == 409 and busy.payload["error"] == {"code": "busy", "retryable": True}
    browser = m.post("/voice/sessions", dict(providerKey="openai", modelKey="gpt-realtime",
                                             connectionMode="webrtc", offerSdp=OFFER), m.headers)
    assert browser.status_code == 409 and browser.payload["error"]["code"] == "voice_busy"

    _until(lambda: sidebands)
    band = sidebands[0]
    band.push(type="session.updated", event_id="e1")
    events = _voice(m, "POST", f"sessions/{sid}/events", token, {"after": 0, "wait": 3}).payload
    assert [e["type"] for e in events["events"]][:1] == ["ready"]
    assert _voice(m, "POST", f"sessions/{sid}/connected", token, {}).status_code == 200
    _until(lambda: any(e.get("type") == "response.create" and "instructions" in e.get("response", {}) for e in band.sent))

    band.push(type="input_audio_buffer.speech_started", event_id="e2", item_id="u1")
    band.push(type="conversation.item.input_audio_transcription.completed", event_id="e3", item_id="u1",
              transcript="Find my contacts named test")
    band.push(type="response.function_call_arguments.done", event_id="e4", call_id="call-1",
              name="contacts_search", arguments='{"query":"test"}')
    _until(lambda: any(e.get("item", {}).get("call_id") == "call-1" for e in band.sent))
    output = next(e for e in band.sent if e.get("item", {}).get("call_id") == "call-1")
    assert output["item"]["type"] == "function_call_output"
    assert band.sent[band.sent.index(output) + 1] == {"type": "response.create"}
    band.push(type="response.output_audio_transcript.done", event_id="e5", transcript="I found no contacts named test.")
    band.push(type="response.done", event_id="e6", response={"output": []})

    def phone_types():
        return [e["type"] for e in _voice(m, "GET", f"sessions/{sid}/events", token, query="?after=0&wait=0").payload["events"]]
    _until(lambda: phone_types().count("transcript") == 2)
    shown = _voice(m, "GET", f"sessions/{sid}/events", token, query="?after=0&wait=0").payload["events"]
    tools = [e for e in shown if e["type"] == "tool"]
    assert [t["state"] for t in tools] == ["running", "completed"] and tools[0]["name"] == "contacts_search"
    assert all("call_id" not in e and "arguments" not in e for e in shown), "phone events are display-only"

    closed = _voice(m, "POST", f"sessions/{sid}/close", token, {})
    assert closed.status_code == 200 and closed.payload == {"status": "closed"}
    assert hangups == ["rtc_test1"] and band.closed
    last = _voice(m, "GET", f"sessions/{sid}/events", token, query="?after=0&wait=0").payload
    assert last["closed"] is True and last["events"][-1] == {"seq": last["next"], "type": "closed", "reason": "ended"}
    with psycopg.connect(m.url) as connection:
        status = connection.execute("SELECT status FROM vault_private.vault_voice_sessions WHERE voice_session_id=%s",
                                    (sid,)).fetchone()[0]
        roles = [r[0] for r in connection.execute(
            """SELECT event_role FROM vault_private.vault_voice_provider_events
               WHERE voice_session_id=%s AND transcript_entry_index IS NOT NULL ORDER BY transcript_entry_index""",
            (sid,)).fetchall()]
        invoked = connection.execute(
            "SELECT count(*) FROM vault_private.vault_voice_tool_invocations WHERE voice_session_id=%s AND tool_call_id='call-1'",
            (sid,)).fetchone()[0]
    assert status == "closed" and roles == ["user", "assistant"] and invoked == 1

    # Freed: a new call can start; the idle cap ends it and frees it again.
    service.idle_seconds = 1
    again = _voice(m, "POST", "sessions", token, {"offerSdp": OFFER})
    assert again.status_code == 201, again.payload
    second = again.payload["sessionId"]
    _until(lambda: _voice(m, "GET", f"sessions/{second}/events", token, query="?after=0&wait=0").payload["closed"], 15)
    reason = _voice(m, "GET", f"sessions/{second}/events", token, query="?after=0&wait=0").payload["events"][-1]["reason"]
    assert reason == "idle" and hangups == ["rtc_test1", "rtc_test2"]
    assert service.active_for(m.principal.user_id, m.principal.workspace_id) is None
    assert _voice(m, "GET", "sessions/unknown/events", token).payload["error"]["code"] == "not_found"


class Engine:
    """Records what the shared preparation engine is fed and answers like it does with one memory hit."""
    def __init__(self):
        self.updates, self.receipts, self.discarded = [], [], 0

    def update(self, principal, source, payload):
        self.updates.append((source, payload))
        return {"revision": payload["revision"], "state": "accepted"}

    def status(self, principal, source, utterance, revision):
        return {"revision": revision, "state": "ready", "toolState": "proposed",
                "memories": [{"id": "m1", "text": "Dana prefers morning calls", "methods": ["vector"]}],
                "tools": [{"id": "t1", "name": "contacts_search", "description": "Find contacts"}]}

    def delivered(self, principal, source, utterance, memories, tools):
        self.receipts.append((memories, tools))

    def discard(self, principal, source, utterance=None):
        self.discarded += 1


def test_companion_voice_uses_live_memory_and_tool_route_like_browser(mounted, monkeypatch):
    m = mounted
    grant(m)
    calls, bands = [], {}

    def realtime_call(*, access_token, offer_sdp, session, organization=None):
        calls.append(session)
        return ANSWER, f"rtc_live{len(calls)}"

    monkeypatch.setattr("app.vault_runtime.voice.openai_realtime.OpenAIRealtimeProvider._realtime_call",
                        staticmethod(realtime_call))
    token, _ = _pair(m)
    service = m.app._companion_voice_service()
    engine = Engine()
    service._preparation, service._live_enabled = engine, (lambda principal: True)
    async def connect(call_id, credential):
        bands[call_id] = Sideband()
        return bands[call_id]
    service._connect = connect
    service._hangup = lambda call_id, credential: None

    started = _voice(m, "POST", "sessions", token, {"offerSdp": OFFER})
    assert started.status_code == 201, started.payload
    body = started.payload
    assert body["liveMemory"] is True and body["liveTranscription"] is True
    sid = body["sessionId"]
    answer = _voice(m, "POST", f"sessions/{sid}/transcription", token, {"offerSdp": OFFER})
    assert answer.status_code == 201 and answer.payload == {"sdpAnswer": ANSWER}
    assert calls[1]["type"] == "transcription", "Vault created the live-transcription call itself"
    _until(lambda: "rtc_live1" in bands and "rtc_live2" in bands)
    call_band, words = bands["rtc_live1"], bands["rtc_live2"]

    call_band.push(type="input_audio_buffer.speech_started", event_id="s1", item_id="u1")
    _until(lambda: engine.updates)  # Speech start registers the utterance before words arrive (as on a real call).
    for delta in ("When does Dana ", "like calls?"):
        words.push(type="conversation.item.input_audio_transcription.delta", item_id="w1", content_index=0, delta=delta)
    _until(lambda: any(e.get("type") == "session.update" and "Dana prefers morning calls" in e["session"]["instructions"]
                       for e in call_band.sent))
    update = next(e for e in call_band.sent if e.get("type") == "session.update"
                  and "Dana prefers morning calls" in e["session"]["instructions"])
    assert update["session"]["instructions"].startswith(calls[0]["instructions"]), "mode instructions keep authority"
    assert "Live tool route" in update["session"]["instructions"] and "contacts_search" in update["session"]["instructions"]
    texts = [p["text"] for s, p in engine.updates]
    assert texts[0] == "" and texts[-1] == "When does Dana like calls?"
    assert all(s == f"voice-live:{sid}" for s, _ in engine.updates), "same source as browser Voice"
    assert engine.receipts and engine.receipts[-1] == (1, 1)
    call_band.push(type="input_audio_buffer.speech_stopped", event_id="s2", item_id="u1")
    _until(lambda: {"type": "input_audio_buffer.commit"} in words.sent)
    shown = _voice(m, "GET", f"sessions/{sid}/events", token, query="?after=0&wait=0").payload["events"]
    live = [e for e in shown if e["type"] == "live"]
    assert live and live[-1]["memories"] == [{"text": "Dana prefers morning calls"}] and live[-1]["tools"] == ["contacts_search"]

    assert _voice(m, "POST", f"sessions/{sid}/close", token, {}).payload == {"status": "closed"}
    assert engine.discarded == 1 and words.closed
