"""Shared test helpers moved out of test modules (TST-01)."""

import json
from time import monotonic, sleep


def _pair(m, poll="poll-secret"):
    started = m.post("/link-companion/pairing/start", {"displayName": "This computer", "pollToken": poll}, {})
    assert started.status_code == 201
    code, pairing = started.payload["pairingCode"], started.payload["pairingId"]
    shown = m.app.handle(method="GET", target=f"/link-companion/pairing/{code}", headers=m.headers)
    assert shown.status_code == 200
    approved = m.post(f"/link-companion/pairing/{pairing}/approve", {}, m.headers)
    assert approved.status_code == 200 and approved.payload["status"] == "paired"
    assert "companionToken" not in approved.payload
    first = m.post("/link-companion/pairing/status", {"pairingId": pairing, "pollToken": poll}, {})
    again = m.post("/link-companion/pairing/status", {"pairingId": pairing, "pollToken": poll}, {})
    assert first.payload["status"] == "approved" and len(first.payload["companionToken"]) > 40
    assert again.payload == {"status": "approved"}, "credential must be delivered exactly once"
    return first.payload["companionToken"], pairing


def _chat(m, method, path, token, payload=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = json.dumps(payload).encode() if payload is not None else b""
    return m.app.handle(method=method, target=f"/link-companion/chat/{path}", headers=headers, body=body)


def _run(m, token, run_id):
    deadline = monotonic() + 15
    while monotonic() < deadline:
        response = _chat(m, "GET", f"runs/{run_id}", token)
        assert response.status_code == 200, response.payload
        if response.payload["state"] not in {"queued", "running"}:
            return response.payload
        sleep(0.05)
    raise AssertionError("bounded companion run did not finish")
