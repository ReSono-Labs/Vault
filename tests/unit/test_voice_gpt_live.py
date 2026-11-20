"""GPT-Live (gpt-live-1, 2026-11-17): Vault's Voice calls on the Live API, with Vault's own tools as
the backend the live model delegates to."""
import asyncio
from types import SimpleNamespace

from app.vault_runtime.voice.companion import CompanionCall, CompanionVoiceService, _live_session_update
from app.vault_runtime.voice.openai_realtime import build_openai_live_session_object, is_live_model
from app.vault_runtime.voice.provider import RealtimeSessionRequest

TOOL = {"type": "function", "name": "link_chat_card_publish", "description": "Show a card",
        "parameters": {"type": "object", "properties": {"fallback_text": {"type": "string"}}}}


def test_live_session_puts_vault_tools_and_instructions_on_the_backend():
    assert is_live_model("gpt-live-1") and not is_live_model("gpt-realtime-2.1")
    session = build_openai_live_session_object(RealtimeSessionRequest(
        model_key="gpt-live-1", connection_mode="webrtc", instructions="VAULT RULES",
        tool_definitions=(TOOL,), display_name="Christian", delegation_model="gpt-5.6-luna"))
    assert session["model"] == "gpt-live-1" and "Christian" in session["instructions"]
    assert "VAULT RULES" not in session["instructions"], "tool guidance goes to the backend only"
    backend = session["delegation"]["responses"]
    assert session["delegation"]["type"] == "responses" and backend["model"] == "gpt-5.6-luna"
    assert backend["instructions"].endswith("VAULT RULES")
    assert backend["tools"] == [{**TOOL, "strict": False}] and backend["parallel_tool_calls"] is False
    assert "turn_detection" not in str(session) and "audio" not in session


def _call():
    call = CompanionCall("voice-1", SimpleNamespace(user_id="u", workspace_id="w", session_id="s"),
                         "live_1", "token", None, 600, 120)
    call.protocol = "openai-live"
    return call


def _service(captured):
    service = CompanionVoiceService.__new__(CompanionVoiceService)
    async def capture(call, event, kind, role, *, text=None, index=None):
        captured.append((kind, role, text, index))
    service._capture = capture
    return service


def test_live_words_become_transcript_lines_and_tool_calls_go_to_the_worker():
    captured, call = [], _call()
    service, tools = _service(captured), asyncio.Queue()

    async def run():
        for kind, delta in (("session.input_transcript.delta", "Show my "), ("session.input_transcript.delta", "week"),
                            ("session.output_transcript.delta", "Here it "), ("session.output_transcript.delta", "is.")):
            await service._handle_live(call, {"type": kind, "delta": delta}, tools)
        await service._handle_live(call, {"type": "response.event", "delegation_id": "d1", "event": {
            "type": "response.output_item.done",
            "item": {"type": "function_call", "name": "link_chat_card_publish", "call_id": "c1", "arguments": "{}"}}}, tools)
        await service._live_turn_end(call)
        await service._handle_live(call, {"type": "session.closed", "reason": "close_requested"}, tools)
    asyncio.run(run())
    assert [(r, t) for _k, r, t, _i in captured] == [("user", "Show my week"), ("assistant", "Here it is.")]
    assert call.last_utterance == ("Show my week", 0)
    assert [e["text"] for e in call.events if e["type"] == "transcript"] == ["Show my week", "Here it is."]
    assert tools.get_nowait() == {"name": "link_chat_card_publish", "call_id": "c1", "arguments": "{}"}
    assert call.closing == "ended"


def test_a_mode_change_updates_the_backend_not_the_live_prompt():
    update = _live_session_update({"type": "session.update", "session": {"instructions": "GOAL MODE", "tools": [TOOL]}})
    responses = update["session"]["delegation"]["responses"]
    assert update["type"] == "session.update" and update["session"]["delegation"]["type"] == "responses"
    assert responses["instructions"].endswith("GOAL MODE") and responses["tools"][0]["strict"] is False
    assert "instructions" not in update["session"]


def test_link_calls_use_the_live_api_and_fall_back_when_it_is_not_offered(monkeypatch):
    import httpx
    from app.vault_runtime.voice.openai_realtime import OpenAIRealtimeProvider
    from app.vault_runtime.voice.provider import ProviderCredential
    seen = []

    def post(url, **kwargs):
        seen.append(url)
        request = httpx.Request("POST", url)
        if url.endswith("/live/sessions"):
            if len(seen) == 1:
                return httpx.Response(201, request=request, json={"session": {"id": "live_123"}, "transport": {"sdp": "v=0\r\no=a"}})
            return httpx.Response(403, request=request, json={"error": {"message": "not offered"}})
        return httpx.Response(201, request=request, text="v=0\r\no=b", headers={"location": "/v1/realtime/calls/rtc_9"})

    monkeypatch.setattr("app.vault_runtime.voice.openai_realtime.httpx.post", post)
    offer = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    request = RealtimeSessionRequest(model_key="gpt-live-1", connection_mode="webrtc", offer_sdp=offer,
                                     server_controlled=True, tool_definitions=(TOOL,))
    live = OpenAIRealtimeProvider().create_realtime_session(request, credential=ProviderCredential("t", auth_method="api_key"))
    assert live.protocol == "openai-live" and live.call_id == "live_123"
    fallback = OpenAIRealtimeProvider().create_realtime_session(request, credential=ProviderCredential("t", auth_method="api_key"))
    assert fallback.protocol == "openai-realtime" and fallback.call_id == "rtc_9"
    assert seen[-1].endswith("/realtime/calls")


def _token(account="acct_123"):
    import base64, json as _json
    body = base64.urlsafe_b64encode(_json.dumps({"https://api.openai.com/auth": {"chatgpt_account_id": account}}).encode()).decode().rstrip("=")
    return f"x.{body}.y"


def test_chatgpt_sign_in_uses_codex_voice_broker_with_client_delegation(monkeypatch):
    import httpx
    from app.vault_runtime.voice.openai_realtime import OpenAIRealtimeProvider, chatgpt_account_id
    from app.vault_runtime.voice.provider import ProviderCredential
    assert chatgpt_account_id(_token()) == "acct_123" and chatgpt_account_id("junk") == ""
    seen = {}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return httpx.Response(201, request=httpx.Request("POST", url), text="v=0\r\no=a",
                              headers={"location": "/v1/realtime/calls/rtc_live9"})

    monkeypatch.setattr("app.vault_runtime.voice.openai_realtime.httpx.post", post)
    offer = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    result = OpenAIRealtimeProvider().create_realtime_session(RealtimeSessionRequest(
        model_key="gpt-live-1", connection_mode="webrtc", offer_sdp=offer, server_controlled=True,
        display_name="Christian", voice="marin", tool_definitions=(TOOL,)),
        credential=ProviderCredential(_token(), auth_method="chatgpt_oauth"))
    assert seen["url"].startswith("https://chatgpt.com/backend-api/codex/realtime/calls?intent=quicksilver")
    assert seen["headers"]["chatgpt-account-id"] == "acct_123" and seen["headers"]["OpenAI-Alpha"] == "quicksilver=v2"
    session = seen["json"]["session"]
    assert session["model"] == "gpt-live-1-codex" and session["delegation"] == {"type": "client"}
    assert session["audio"]["output"]["voice"] == "sol", "a Realtime voice falls back to a subscription voice"
    assert "Christian" in session["instructions"] and "link_chat_card_publish" not in str(session)
    assert result.protocol == "openai-live-client" and result.call_id == "rtc_live9"
    assert result.sideband_url == "wss://api.openai.com/v1/live/rtc_live9"


def test_subscription_turns_and_delegations():
    captured, call = [], _call()
    call.protocol = "openai-live-client"
    service, tools = _service(captured), asyncio.Queue()
    started = []

    async def delegate(call, delegation_id, prompt, send):
        started.append((delegation_id, prompt))
    service._delegate = delegate

    async def send(event):
        pass

    async def run():
        await service._handle_live(call, {"type": "turn.done", "turn": {"role": "user", "transcript": "Show my week"}}, tools, send)
        await service._handle_live(call, {"type": "delegation.created", "item": {
            "id": "dlg_1", "type": "delegation", "target": "client",
            "content": [{"type": "input_text", "text": "Put the user's week on a card"}]}}, tools, send)
        await asyncio.sleep(0)
    asyncio.run(run())
    assert [(r, t) for _k, r, t, _i in captured] == [("user", "Show my week")]
    assert call.recent_lines == [("user", "Show my week")]
    assert started == [("dlg_1", "Put the user's week on a card")]


def test_live_memory_transcription_stays_on_realtime():
    """2026-11-17: gpt-live-transcribe was taken for GPT-Live, so live memory got no words."""
    assert not is_live_model("gpt-live-transcribe")
    assert is_live_model("gpt-live-1") and is_live_model("gpt-live-1-codex")


class _FakeEngine:
    """Shared preparation engine stand-in: records the words, answers with one memory and a tool."""
    def __init__(self):
        self.updates, self.delivered = [], []

    def update(self, principal, source, update):
        self.updates.append(update)
        return {"enabled": True}

    def status(self, principal, source, utterance, posted):
        return {"state": "ready", "memories": [{"id": "m1", "text": "Christian's dentist is Dr. Ito"}],
                "tools": [{"name": "calendar_list"}]}

    def delivered(self, principal, source, utterance, memories, tools):
        self.delivered.append((memories, tools))

    def discard(self, principal, source):
        pass


def test_live_memory_runs_on_gpt_live_words_and_reaches_the_delegated_agent():
    """2026-11-17: live memory during a GPT-Live call (ChatGPT sign-in). The live prompt is never
    replaced; the panel gets the result and Vault's agent gets it with the delegated request."""
    from app.vault_runtime.voice.companion import LivePreparation
    captured, call = [], _call()
    call.protocol = "openai-live-client"
    engine = _FakeEngine()
    call.live_prep = LivePreparation(call, engine, "BASE", native=True, apply_instructions=False)
    service, tools, sent = _service(captured), asyncio.Queue(), []

    async def send(event):
        sent.append(event)

    async def run():
        for fragment in ("When is ", "my dentist?"):
            await service._handle_live(call, {"type": "input_transcript.added", "item": {"text": fragment}}, tools, send)
        await service._handle_live(call, {"type": "turn.done", "turn": {"role": "user", "transcript": "When is my dentist?"}}, tools, send)
        for _ in range(20):
            await asyncio.sleep(0.05)
            if call.live_prep.context:
                break
        return await call.live_prep.settled()
    prepared = asyncio.run(run())
    words = [u["text"] for u in engine.updates if u.get("text")]
    assert words[:2] == ["When is ", "When is my dentist?"]
    assert not any(e.get("type") == "session.update" for e in sent), "the live model's prompt is not replaced"
    silent = [e for e in sent if e.get("type") == "session.context.append"]
    assert silent and silent[-1]["channel"] == "commentary" and "Dr. Ito" in silent[-1]["content"][0]["text"]
    panel = [e for e in call.events if e["type"] == "live"]
    assert panel and panel[-1]["memories"] == [{"text": "Christian's dentist is Dr. Ito"}]
    assert panel[-1]["tools"] == ["calendar_list"]
    assert "Dr. Ito" in prepared and "calendar_list" in prepared


def test_every_voice_model_gets_the_same_shared_prompt():
    """2026-11-17: live-1 got a separate short prompt (no profile, style, memory, last summary)."""
    from app.vault_runtime.voice.openai_realtime import build_subscription_live_session_object
    shared = "SHARED VOICE PROMPT with memory and style"
    request = RealtimeSessionRequest(model_key="gpt-live-1", connection_mode="webrtc",
        instructions=shared + "\n\nTOOL GUIDANCE", conversation_instructions=shared,
        tool_definitions=(TOOL,), display_name="Christian")
    api = build_openai_live_session_object(request)
    sub = build_subscription_live_session_object(request)
    for session in (api, sub):
        assert shared in session["instructions"] and "TOOL GUIDANCE" not in session["instructions"]
        assert session["instructions"].startswith("Live voice layer")
    assert api["delegation"]["responses"]["instructions"].endswith(shared + "\n\nTOOL GUIDANCE")


def test_gpt_live_greets_with_the_shared_greeting():
    from app.vault_runtime.voice.companion import _greeting_words, _live_context_event
    from app.vault_runtime.voice.greeting import connect_greeting_event
    words = _greeting_words(connect_greeting_event("Christian"))
    assert "Christian" in words and words.startswith("Greet the user now")
    sub = _live_context_event(words, "speakable", subscription=True)
    assert sub["type"] == "session.context.append" and sub["channel"] == "speakable"
    api = _live_context_event(words, "speakable", subscription=False)
    assert api["type"] == "session.commentary.append" and api["delegation_id"] is None
    assert _live_context_event("x", "commentary", subscription=False)["type"] == "session.thinking.append"


def test_context_builder_splits_shared_prompt_from_tool_guidance():
    from app.vault_runtime.voice.context import VoiceContextBuilder
    from app.vault_runtime.voice.instructions import LINK_CARDS_GUIDANCE, PRIMARY_VOICE_INSTRUCTIONS
    memories = SimpleNamespace(profile_memories=lambda **k: (), previous_session_summary=lambda **k: "Talked about cards.")
    principal = SimpleNamespace(user_id="u", workspace_id="w", display_name="Christian", experience_style="Calm")
    context = VoiceContextBuilder(memories=memories).build(principal=principal, voice_session_id="v")
    shared = context.conversation_instructions
    assert PRIMARY_VOICE_INSTRUCTIONS in shared and "Christian" in shared and "Calm" in shared
    assert "Talked about cards." in shared and LINK_CARDS_GUIDANCE not in shared
    assert context.instructions.startswith(shared) and LINK_CARDS_GUIDANCE in context.instructions


def test_gpt_live_greeting_waits_for_session_started():
    """Like OpenClaw: speakable context sent before session.started can be dropped."""
    call, sent = _call(), []
    call.protocol = "openai-live-client"
    call.greeting = {"type": "session.context.append", "channel": "speakable", "content": []}
    call.media_connected = True
    service, tools = _service([]), asyncio.Queue()

    async def run():
        call.loop = asyncio.get_running_loop()
        async def sender(event):
            sent.append(event)
        call.sender = sender
        call.deliver_greeting("sideband_open")
        await asyncio.sleep(0)
        assert sent == [] and call.greeting is not None
        await service._handle_live(call, {"type": "session.started"}, tools)
        await asyncio.sleep(0)
    asyncio.run(run())
    assert [e["type"] for e in sent] == ["session.context.append"] and call.greeting is None


def test_gpt_live_sessions_start_with_the_greeting_as_a_developer_message():
    """OpenAI "Greet before the caller speaks": greeting in session.input, then commentary after start."""
    from app.vault_runtime.voice.openai_realtime import build_subscription_live_session_object
    request = RealtimeSessionRequest(model_key="gpt-live-1", connection_mode="webrtc", display_name="Christian",
                                     conversation_instructions="SHARED", tool_definitions=(TOOL,))
    for session in (build_openai_live_session_object(request), build_subscription_live_session_object(request)):
        (message,) = session["input"]
        assert message["role"] == "developer" and message["content"][0]["type"] == "input_text"
        assert "Christian" in message["content"][0]["text"] and "Greet the user now" in message["content"][0]["text"]
    nameless = RealtimeSessionRequest(model_key="gpt-live-1", connection_mode="webrtc", tool_definitions=(TOOL,))
    assert "input" not in build_openai_live_session_object(nameless)


def test_broker_refusing_the_startup_greeting_still_starts_the_call(monkeypatch):
    import httpx
    from app.vault_runtime.voice.openai_realtime import OpenAIRealtimeProvider
    from app.vault_runtime.voice.provider import ProviderCredential
    bodies = []

    def post(url, **kwargs):
        bodies.append(kwargs["json"]["session"])
        request = httpx.Request("POST", url)
        if "input" in kwargs["json"]["session"]:
            return httpx.Response(400, request=request, json={"error": {"message": "unknown field input"}})
        return httpx.Response(201, request=request, text="v=0\r\no=a", headers={"location": "/v1/realtime/calls/rtc_live9"})

    monkeypatch.setattr("app.vault_runtime.voice.openai_realtime.httpx.post", post)
    offer = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    result = OpenAIRealtimeProvider().create_realtime_session(RealtimeSessionRequest(
        model_key="gpt-live-1", connection_mode="webrtc", offer_sdp=offer, server_controlled=True,
        display_name="Christian", tool_definitions=(TOOL,)),
        credential=ProviderCredential(_token(), auth_method="chatgpt_oauth"))
    assert result.call_id == "rtc_live9" and "input" in bodies[0] and "input" not in bodies[1]
