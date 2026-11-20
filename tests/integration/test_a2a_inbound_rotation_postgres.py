"""Making a new inbound Agent2Agent token against the real schema, isolated test DB only."""
import psycopg


def _enable(m):
    response = m.post("/builtin-plugins/agent2agent", {"enabled": True}, m.headers)
    assert response.status_code == 200, response.payload


def test_new_inbound_token_keeps_the_session_and_retires_the_old_token(mounted):
    m = mounted
    _enable(m)
    service = m.app._a2a_service
    repository, scope = service.repository, dict(user_id=m.principal.user_id, workspace_id=m.principal.workspace_id)
    old = service.listen_info(**scope)["token"]
    session = repository.resolve_inbound(old)[2]

    listed = m.app.handle(method="GET", target="/agent2agent/listen", headers=m.headers)
    assert listed.status_code == 200 and listed.payload["tokenHint"] == old[-4:] and "token" not in listed.payload

    rotated = m.post("/agent2agent/listen/rotate", {}, m.headers)
    assert rotated.status_code == 200, rotated.payload
    new = m.post("/agent2agent/listen/token", {}, m.headers).payload["token"]
    assert new != old and rotated.payload["tokenHint"] == new[-4:]
    assert repository.resolve_inbound(old) is None
    assert repository.resolve_inbound(new) == (m.principal.user_id, m.principal.workspace_id, session)

    # A password change revokes every other session, including the inbound one: a new token repairs it.
    with psycopg.connect(m.url) as connection:
        connection.execute("UPDATE vault_private.local_sessions SET status='revoked',revoked_at=now() WHERE session_id=%s",
                           (session,))
    assert repository.inbound_session_active(session_id=session) is False
    service.rotate_listen_token(**scope)
    repaired = repository.inbound_row(**scope)
    assert repaired[0] != session and repository.inbound_session_active(session_id=repaired[0])
    assert repository.resolve_inbound(new) is None


def test_rotate_requires_csrf(mounted):
    m = mounted
    _enable(m)
    old = m.app._a2a_service.listen_info(user_id=m.principal.user_id, workspace_id=m.principal.workspace_id)["token"]
    no_csrf = {"Cookie": m.headers["Cookie"]}
    assert m.post("/agent2agent/listen/rotate", {}, no_csrf).status_code != 200
    assert m.post("/agent2agent/listen/token", {}, no_csrf).status_code != 200
    assert m.app._a2a_service.repository.resolve_inbound(old) is not None
