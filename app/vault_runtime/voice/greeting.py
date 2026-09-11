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
