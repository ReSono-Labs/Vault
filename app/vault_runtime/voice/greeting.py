"""R1-derived, local-only Voice connection greeting contract."""

from __future__ import annotations

from datetime import datetime


def connect_greeting_event(display_name: str, *, now: datetime | None = None) -> dict[str, object] | None:
    name = display_name.strip()
    if not name:
        return None
    local_time = now or datetime.now().astimezone()
    hour = local_time.hour
    daypart = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    greeting = f"Good {daypart} {name}, what can I help you with this {daypart}?"
    return {
        "type": "response.create",
        "response": {
            "instructions": f'Say exactly: "{greeting}" Then stop and wait for the user.'
        },
    }


def live_greeting_text(greeting: dict[str, object] | None) -> str:
    """GPT-Live has no response.create: the same greeting as a direction it follows (OpenAI "Greet
    before the caller speaks": what to say, that it begins now, then pause and listen)."""
    said = str(((greeting or {}).get("response") or {}).get("instructions") or "")  # type: ignore[union-attr]
    return ("Greet the user now in English, before they speak. " + said) if said else ""


def live_greeting_input(display_name: str | None) -> list[dict[str, object]]:
    """The greeting as a developer message in session.input, available from the session's start."""
    text = live_greeting_text(connect_greeting_event(display_name or ""))
    return [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": text}]}] if text else []
