from datetime import datetime

from app.vault_runtime.voice.greeting import connect_greeting_event


def test_connect_greeting_matches_r1_daypart_contract() -> None:
    event = connect_greeting_event("Christian", now=datetime(2026, 8, 29, 9, 0))
    assert event == {
        "type": "response.create",
        "response": {
            "instructions": 'Say exactly: "Good morning Christian, what can I help you with this morning?" Then stop and wait for the user.'
        },
    }


def test_connect_greeting_omits_blank_name() -> None:
    assert connect_greeting_event("  ") is None
