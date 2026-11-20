from datetime import UTC, datetime, timedelta

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.voice.context import VoiceContextBuilder
from app.vault_runtime.voice.tools import redact_tool_arguments


class Memories:
    def profile_memories(self, **_kwargs): return ()
    def previous_session_summary(self, **_kwargs): return None


class Plugins:
    def list(self, **_kwargs):
        return [
            {"key":"weather","enabled":True,"configuration":{"primaryLocation":"St Petersburg, FL"}},
            {"key":"markets","enabled":True,"configuration":{"watchlist":["AAPL","MSFT"]}},
            {"key":"news","enabled":True,"configuration":{"defaultCategory":"technology","headlineCount":5}},
            {"key":"local_events","enabled":True,"configuration":{"homeLocation":"St Petersburg, FL","radiusMiles":10}},
            {"key":"agent_mail","enabled":False,"configuration":{}},
        ]


def test_voice_context_receives_safe_saved_plugin_defaults_and_routing():
    principal = LocalPrincipal("u1","owner","Christian","concise",True,"s1","w1",datetime.now(UTC)+timedelta(hours=1))
    context = VoiceContextBuilder(memories=Memories(), builtin_plugins=Plugins()).build(principal=principal, voice_session_id="v1")
    assert "saved primary location is St Petersburg, FL" in context.instructions
    assert "omit location to use the saved primary" in context.instructions
    assert "saved watchlist is AAPL, MSFT" in context.instructions
    assert "do not substitute generic web_search" in context.instructions
    assert "geographic/local news" in context.instructions
    assert "Agent Mail" not in context.instructions
    assert "agent2agent_send" not in context.instructions


def test_tool_argument_audit_keeps_routing_values_and_redacts_secrets():
    value = redact_tool_arguments({"location":"St Petersburg, FL","symbol":"AAPL","query":"market news","apiKey":"private","body":"private message","nested":{"password":"private","radiusMiles":10}})
    assert value == {"location":"St Petersburg, FL","symbol":"AAPL","query":"market news","apiKey":"[redacted]","body":"[redacted]","nested":{"password":"[redacted]","radiusMiles":10}}
