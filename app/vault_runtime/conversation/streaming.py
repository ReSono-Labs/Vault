"""Replayable bounded SSE viewing. Disconnect is never authorization to rerun work."""
import json
from threading import Event
from time import monotonic


def event_stream(store,principal,conversation_id,turn_id,*,after=0,seconds=25,slots=None):
    if slots is not None and not slots.acquire(blocking=False):
        yield b'event: unavailable\ndata: {"code":"stream_capacity"}\n\n'
        return
    try:
        yield from _events(store,principal,conversation_id,turn_id,after=after,seconds=seconds)
    finally:
        if slots is not None:
            slots.release()


def _events(store,principal,conversation_id,turn_id,*,after,seconds):
    cursor,deadline = after,monotonic()+seconds
    pause = Event()
    while monotonic()<deadline:
        events = store.events(principal,conversation_id,turn_id,cursor)
        for event in events:
            cursor = event["sequence"]
            yield ("id: "+str(cursor)+"\nevent: conversation\ndata: "+
                json.dumps(dict(turnId=turn_id,**event),ensure_ascii=False,separators=(",",":"))+"\n\n").encode()
        if events:
            continue
        status = store.status(principal,conversation_id,turn_id)
        if status["state"] not in {"submitted","running"}:
            return
        yield b": keepalive\n\n"
        pause.wait(0.2)
