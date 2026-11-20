"""R1 route inventory and R2 response snapshots for ``VaultLocalApiApp.handle`` (cleanup B5).

R1 lists every route the dispatcher serves (method, path pattern, authentication and CSRF
requirement) and checks each requirement against the real app. R2 records status, headers and
payload of one request per route on a fixture account (secrets, ids, times and paths redacted)
and compares them with ``snapshots/local_api_routes.json``.

Both were written by reading the dispatcher before the split of ``local_api/app.py`` and must stay
identical while the route code moves. Regenerate the snapshot only for an intended API change:
``UPDATE_ROUTE_SNAPSHOTS=1``.
"""
from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.composition import build_local_app
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from tests.support.conversation_identity import require_test_database

SNAPSHOT = Path(__file__).parent / "snapshots" / "local_api_routes.json"
FAKE = "00000000-0000-4000-8000-00000000f00d"  # Id that names no row.


@dataclass(frozen=True)
class Route:
    method: str
    pattern: str
    auth: str  # "none" | "session" | "bearer" (Link Companion / external memory / plugin token)
    csrf: bool
    query: str = ""
    session_ending: bool = False  # Run last: the request ends the fixture session.

    @property
    def target(self) -> str:
        path = re.sub(r"\{[a-z_]+\}", FAKE, self.pattern)
        return f"{path}?{self.query}" if self.query else path

    @property
    def key(self) -> str:
        return f"{self.method} {self.pattern}"


def R(method, pattern, auth="session", csrf=None, **extra):  # noqa: N802 - table helper
    if csrf is None:
        csrf = auth == "session" and method != "GET"
    return Route(method, pattern, auth, csrf, **extra)


# R1 - in the dispatcher's order of precedence.
ROUTES: tuple[Route, ...] = (
    R("GET", "/health", "none"),
    # Chat (conversation API); the host authenticates and checks CSRF for non-GET.
    R("GET", "/conversations"),
    R("POST", "/conversations"),
    R("GET", "/conversations/decisions/qualification"),
    R("POST", "/conversations/decisions/rebuild"),
    R("GET", "/conversations/genui/{id}"),
    R("GET", "/conversations/{id}"),
    R("POST", "/conversations/{id}/attachments"),
    R("DELETE", "/conversations/{id}/attachments/{attachment_id}"),
    R("GET", "/conversations/{id}/review-status"),
    R("POST", "/conversations/{id}/activity"),
    R("POST", "/conversations/{id}/end-session"),
    R("GET", "/conversations/{id}/preparation"),
    R("POST", "/conversations/{id}/preparation"),
    R("DELETE", "/conversations/{id}/preparation"),
    R("POST", "/conversations/{id}/turns"),
    R("GET", "/conversations/{id}/turns/{turn_id}"),
    R("POST", "/conversations/{id}/turns/{turn_id}/feedback"),
    R("POST", "/conversations/{id}/turns/{turn_id}/alternatives"),
    R("POST", "/conversations/{id}/turns/{turn_id}/choice"),
    R("POST", "/conversations/{id}/turns/{turn_id}/stop"),
    R("GET", "/conversations/{id}/turns/{turn_id}/events"),
    # Live memory and live tool routing.
    R("GET", "/live-memory"),
    R("POST", "/live-memory"),
    R("GET", "/live-tool-routing"),
    R("POST", "/live-tool-routing"),
    # Plugin services (plugin bearer token).
    R("POST", "/plugin-services/v1/memory/search", "bearer"),
    R("POST", "/plugin-services/v1/memory/propose", "bearer"),
    R("POST", "/plugin-services/v1/context/locale", "bearer"),
    R("POST", "/plugin-services/v1/activity/report", "bearer"),
    R("GET", "/plugin-services/v1/memory/search", "bearer"),
    # Identity.
    R("GET", "/identity/setup/start", "none", query="credential=wrong"),
    R("GET", "/identity/status", "none"),
    R("POST", "/identity/setup-session", "none"),
    R("POST", "/identity/onboard", "none"),
    R("POST", "/identity/register", "none"),
    R("POST", "/identity/login", "none"),
    R("POST", "/identity/activate", "none"),
    R("GET", "/me"),
    R("POST", "/local-users"),
    R("GET", "/local-users"),
    R("POST", "/local-users/{id}/password-reset"),
    R("POST", "/local-users/{id}/remove"),
    R("POST", "/identity/password"),
    R("GET", "/workspaces"),
    R("POST", "/workspaces"),
    R("POST", "/workspaces/select"),
    R("POST", "/workspaces/members"),
    R("POST", "/workspaces/members/revoke"),
    # Runtime: system agents, tools, Voice, Background.
    R("GET", "/system-agents"),
    R("GET", "/tools"),
    R("POST", "/voice/sessions"),
    R("GET", "/voice/sessions/{id}/preparation", query="utteranceId=u1&revision=0"),
    R("POST", "/voice/sessions/{id}/preparation"),
    R("DELETE", "/voice/sessions/{id}/preparation"),
    R("POST", "/voice/sessions/{id}/preparation/transcription"),
    R("POST", "/voice/sessions/{id}/preparation/delivered"),
    R("GET", "/voice/plan", query="providerKey=openai&modelKey=gpt-realtime"),
    R("GET", "/voice/sessions/{id}/decision-review"),
    R("POST", "/voice/sessions/{id}/close"),
    R("POST", "/voice/sessions/{id}/events"),
    R("POST", "/voice/sessions/{id}/tools/call"),
    R("POST", "/voice/sessions/{id}/finalize"),
    R("GET", "/background/health"),
    R("GET", "/background/runs"),
    R("POST", "/background/runs"),
    R("GET", "/background/runs/{id}"),
    R("DELETE", "/background/runs/{id}"),
    R("POST", "/background/runs/{id}/cancel"),
    R("GET", "/background/preferences"),
    R("POST", "/background/preferences"),
    R("GET", "/background/workers"),
    R("POST", "/background/workers"),
    R("POST", "/background/workers/{id}/pause"),
    R("POST", "/background/workers/{id}/reset"),
    R("POST", "/background/workers/{id}/delete"),
    R("GET", "/background/actions"),
    R("POST", "/background/actions/{id}/decision"),
    R("GET", "/background/work"),
    R("GET", "/background/work/{id}"),
    R("POST", "/background/work/{id}/task"),
    R("POST", "/background/work/{id}/cancel"),
    R("GET", "/background/routines"),
    R("POST", "/background/routines"),
    R("POST", "/background/routines/{id}/pause"),
    R("POST", "/background/routines/{id}/cancel"),
    R("GET", "/background/unknown"),
    # Agent network.
    R("POST", "/agent2agent/connections"),
    R("GET", "/agent2agent/connections"),
    R("GET", "/agent2agent/notifications"),
    R("GET", "/agent2agent/listen"),
    R("POST", "/agent2agent/listen/token"),
    R("POST", "/agent2agent/listen/rotate"),
    R("DELETE", "/agent2agent/connections/{id}"),
    # Extensions.
    R("GET", "/extensions"),
    R("GET", "/extensions/{id}/connections"),
    R("GET", "/extensions/{id}/grants"),
    R("GET", "/extensions/runtime"),
    R("POST", "/extensions/skills/preflight"),
    R("POST", "/extensions/plugins/preflight"),
    R("POST", "/extensions/mcp/preflight"),
    R("POST", "/extensions/mcp-packages/preflight"),
    R("POST", "/extensions/confirm"),
    R("POST", "/extensions/safe-mode"),
    R("POST", "/extensions/{id}/state"),
    R("POST", "/extensions/{id}/grants"),
    R("POST", "/extensions/{id}/credentials"),
    R("POST", "/extensions/{id}/settings"),
    R("POST", "/extensions/{id}/discover"),
    R("DELETE", "/extensions/{id}/unknown"),
    # Built-in plugins.
    R("GET", "/builtin-plugins"),
    R("GET", "/builtin-plugins/agent2agent"),
    R("POST", "/builtin-plugins/agent2agent"),
    # External memory pairing (no session) and integrations.
    R("POST", "/external-memory/pairing/start", "none"),
    R("POST", "/external-memory/pairing/status", "none"),
    R("GET", "/external-memory/integrations"),
    R("GET", "/external-memory/integrations/pairing/{code}"),
    R("POST", "/external-memory/integrations/pairing/{id}/approve"),
    R("POST", "/external-memory/integrations"),
    R("DELETE", "/external-memory/integrations/{id}"),
    R("POST", "/external-memory/integrations/{id}/revoke"),
    # Link Companion (companion bearer), its pairing, and the owner's Link page.
    R("POST", "/link-companion/tools/publish", "bearer"),
    R("POST", "/link-companion/tools/poll", "bearer"),
    R("POST", "/link-companion/tools/complete", "bearer"),
    R("GET", "/link-companion/voice/health", "none"),
    R("POST", "/link-companion/voice/sessions", "bearer"),
    R("POST", "/link-companion/voice/sessions/{id}/transcription", "bearer"),
    R("POST", "/link-companion/voice/sessions/{id}/connected", "bearer"),
    R("POST", "/link-companion/voice/sessions/{id}/close", "bearer"),
    R("GET", "/link-companion/voice/sessions/{id}/events", "bearer"),
    R("POST", "/link-companion/voice/sessions/{id}/events", "bearer"),
    R("POST", "/link-companion/voice/sessions/{id}/approval", "bearer"),
    R("POST", "/link-companion/voice/sessions/{id}/permission", "bearer"),
    R("GET", "/link-companion/chat/health", "none"),
    R("POST", "/link-companion/chat/sessions", "bearer"),
    R("POST", "/link-companion/chat/sessions/{id}/messages", "bearer"),
    # Link Front Door v1 (paired companion bearer).
    R("GET", "/link/v1/capabilities", "bearer"),
    R("POST", "/v1/responses", "bearer"),
    R("GET", "/v1/responses/{id}", "bearer"),
    R("POST", "/v1/responses/{id}/cancel", "bearer"),
    R("POST", "/link/v1/responses/{id}/approval", "bearer"),
    R("POST", "/link/v1/responses/{id}/steer", "bearer"),
    R("POST", "/link/v1/drafts", "bearer"),
    R("POST", "/link/v1/drafts/status", "bearer"),
    R("POST", "/link/v1/drafts/clear", "bearer"),
    R("POST", "/link-companion/pairing/start", "none"),
    R("POST", "/link-companion/pairing/status", "none"),
    R("POST", "/link-companion/agent-network/apply", "bearer"),
    R("POST", "/link-companion/release", "bearer"),
    R("GET", "/link-companion"),
    R("GET", "/link-companion/pairing/{code}"),
    R("POST", "/link-companion/pairing/{id}/approve"),
    R("POST", "/link-companion/unpair"),
    # Owner approvals.
    R("GET", "/approvals"),
    R("POST", "/approvals/{id}/decision"),
    # Commands.
    R("GET", "/commands/settings"),
    R("GET", "/commands/pending", query="conversationId=" + FAKE),
    R("POST", "/admin/commands/settings"),
    R("POST", "/commands/{id}/approve"),
    R("POST", "/commands/{id}/deny"),
    # Folders.
    R("GET", "/folders"),
    R("GET", "/folders/places"),
    R("GET", "/folders/browse", query="grantId=" + FAKE),
    R("GET", "/admin/folders/locations"),
    R("GET", "/admin/folders/browse", query="locationId=" + FAKE),
    R("GET", "/admin/users/{id}/folder-access"),
    R("POST", "/folders"),
    R("POST", "/folders/setup/vault-folder"),
    R("POST", "/admin/folders/add"),
    R("POST", "/folders/setup/add"),
    R("POST", "/folders/{id}/permission"),
    R("POST", "/folders/{id}/hidden"),
    R("POST", "/folders/{id}/remove"),
    R("POST", "/admin/users/{id}/folder-access"),
    R("POST", "/admin/folder-access/{id}/permission"),
    R("POST", "/admin/folder-access/{id}/hidden"),
    R("POST", "/admin/folder-access/{id}/remove"),
    # External memory contract (integration bearer).
    R("GET", "/external-memory/v1/health", "none"),
    R("POST", "/external-memory/v1/startup", "bearer"),
    R("POST", "/external-memory/v1/search", "bearer"),
    R("POST", "/external-memory/v1/get", "bearer"),
    R("POST", "/external-memory/v1/propose", "bearer"),
    R("POST", "/external-memory/v1/request-correction", "bearer"),
    R("POST", "/external-memory/v1/request-forget", "bearer"),
    R("POST", "/external-memory/v1/disconnect", "bearer"),
    # AI providers.
    R("GET", "/providers/gemini/oauth/callback", "none", query="state=wrong&code=wrong"),
    R("POST", "/providers/openai/oauth/start"),
    R("POST", "/providers/openai/oauth/poll"),
    R("POST", "/providers/gemini/oauth/start"),
    R("POST", "/providers/xai/oauth/start"),
    R("POST", "/providers/xai/oauth/poll"),
    R("GET", "/providers/catalog"),
    R("POST", "/providers/openai/auth-method"),
    R("DELETE", "/providers/openai/oauth"),
    R("GET", "/providers/openai/users/{id}"),
    R("POST", "/providers/openai/users/{id}"),
    R("GET", "/providers/openai"),
    R("POST", "/providers/openai"),
    R("POST", "/providers/openai/select"),
    R("DELETE", "/providers/openai"),
    R("GET", "/providers/unknown"),
    # Help, notifications, tasks.
    R("POST", "/help/ask"),
    R("GET", "/notifications"),
    R("POST", "/notifications/clear"),
    R("POST", "/notifications/{id}/clear"),
    R("GET", "/tasks/active"),
    # Workspace files.
    R("GET", "/workspace-files"),
    R("GET", "/workspace-files/read", query="fileKey=missing.md"),
    R("GET", "/workspace-files/download", query="fileKey=missing.md"),
    R("GET", "/workspace-files/shares", query="folderPath=missing"),
    R("PUT", "/workspace-files/files"),
    R("POST", "/workspace-files/text"),
    R("POST", "/workspace-files/directories"),
    R("POST", "/workspace-files/move"),
    R("POST", "/workspace-files/delete"),
    R("POST", "/workspace-files/upload"),
    R("POST", "/workspace-files/shares"),
    R("POST", "/workspace-files/shares/{id}/revoke"),
    # Mail, contacts, calendar.
    R("GET", "/mail/agent-accounts"),
    R("POST", "/mail/agent-accounts"),
    R("GET", "/mail/accounts"),
    R("POST", "/mail/accounts"),
    R("GET", "/mail/accounts/{id}/folders"),
    R("GET", "/mail/accounts/{id}/messages"),
    R("GET", "/mail/accounts/{id}/messages/{message_id}"),
    R("POST", "/mail/accounts/{id}/sync"),
    R("POST", "/mail/accounts/{id}/send/prepare"),
    R("POST", "/mail/accounts/{id}/send/confirm"),
    R("POST", "/mail/accounts/{id}/lifecycle"),
    R("POST", "/mail/accounts/{id}/remove"),
    R("GET", "/contacts"),
    R("POST", "/contacts/search"),
    R("POST", "/contacts/prepare"),
    R("POST", "/contacts/confirm"),
    R("GET", "/calendar/accounts"),
    R("GET", "/calendar/events"),
    R("POST", "/calendar/accounts"),
    R("POST", "/calendar/accounts/{id}/sync"),
    R("DELETE", "/calendar/accounts/{id}"),
    # No route.
    R("GET", "/not-a-route", "none"),
    # Last: these end the fixture session.
    R("POST", "/identity/token/refresh", session_ending=True),
    R("POST", "/identity/logout", session_ending=True),
)

SESSION_FAILURES = ("Local session is required.", "Local session is invalid or expired.")
CSRF_FAILURE = "CSRF proof is invalid."
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z)?")
_SECRET_KEY = re.compile(r"token|secret|credential|password|csrf|cookie|hash|bootstrap", re.I)
_TIME_KEY = re.compile(r"(At|_at|Time|Seconds|epoch)$")
# Versions of the test machine's software (pgvector, Postgres) differ between hosts.
_ENV_KEY = re.compile(r"(Version|version)$")


def _redact(value, tmp: str, key: str = ""):
    if isinstance(value, dict):
        return {k: _redact(v, tmp, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item, tmp, key) for item in value]
    if isinstance(value, str):
        if _ENV_KEY.search(key) and key not in {"contractVersion", "historyVersion", "intentVersion"} and value:
            return "<version>"
        if _SECRET_KEY.search(key) and value:
            return "<secret>"
        if _TIME_KEY.search(key) and value:
            return "<time>"
        value = value.replace(tmp, "<tmp>")
        value = _UUID.sub(lambda m: "<fake-id>" if m.group(0) == FAKE else "<id>", value)
        value = _TIME.sub("<time>", value)
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and _TIME_KEY.search(key):
        return "<time>"
    return value


def _header(name: str, value: str, tmp: str) -> list[str]:
    if name.lower() == "set-cookie":
        cookie, _, attributes = value.partition(";")
        cookie_name, _, cookie_value = cookie.partition("=")
        return [name, f"{cookie_name}={'<secret>' if cookie_value else ''};{attributes}"]
    if name.lower() == "location":
        return [name, re.sub(r"bootstrap=[^&]*", "bootstrap=<secret>", value)]
    return [name, _redact(value, tmp)]


def _call(app, route: Route, headers: dict[str, str], tmp: str) -> dict:
    body = b"" if route.method == "GET" else b"{}"
    try:
        response = app.handle(method=route.method, target=route.target, headers=dict(headers), body=body)
    except Exception as exc:  # The dispatcher lets some errors reach the HTTP server; record them.
        return {"raised": type(exc).__name__, "message": _redact(str(exc), tmp)}
    result = {
        "status": response.status_code,
        "payload": _redact(response.payload, tmp),
        "headers": [_header(name, value, tmp) for name, value in response.headers],
    }
    if response.body is not None:
        result["body"] = f"<{len(response.body)} bytes>"
    if response.content_type is not None:
        result["contentType"] = response.content_type
    if response.stream is not None:
        result["stream"] = True
    return result


def _text(result: dict) -> str:
    return json.dumps(result)


def _session_failure(result: dict) -> bool:
    return any(message in _text(result) for message in SESSION_FAILURES)


def _csrf_failure(result: dict) -> bool:
    return CSRF_FAILURE in _text(result)


@pytest.fixture()
def routes_app(tmp_path, monkeypatch):
    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Exact isolated database required")
    require_test_database(url)
    with psycopg.connect(url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
        connection.execute("DROP SCHEMA IF EXISTS vault_background_queue CASCADE")
    # No workers, network or model calls: every answer comes from the request and the database.
    monkeypatch.setattr("app.vault_runtime.memory.service.MemoryService.ensure_vectors", lambda *a, **k: (0, 0))
    monkeypatch.setattr("app.vault_runtime.memory_search.maintenance.IndexedMemoryMaintenance.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.background_agent.jobs.BackgroundJobs.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.agent_network.service.A2AService.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.agent_network.inbound.A2AInboundHttpServer.start", lambda *_: None)
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_runtime.McpRuntimeSupervisor.restore_on_boot", lambda *_: None)

    def no_network(*_args, **_kwargs):
        raise OSError("network disabled in route snapshots")
    monkeypatch.setattr(socket, "create_connection", no_network)
    config = VaultLocalApiConfig(
        host="127.0.0.1", port=0, token="local-test", data_root=str(tmp_path),
        storage_status_file=str(tmp_path / "status.json"), storage_mount_point=str(tmp_path / "private"),
        database_url=url, setup_credential_hash=hash_token("setup"),
        background_coordination_enabled=True, owner_approvals_enabled=True,
    )
    app = build_local_app(config)
    app._conversation_runtime.title_runner = None
    onboard = app.handle(method="POST", target="/identity/onboard", headers={}, body=json.dumps(
        {"setupCredential": "setup", "displayName": "Owner", "experienceStyle": "strict"}).encode())
    assert onboard.status_code == 201
    cookies = "; ".join(v.split(";", 1)[0] for k, v in onboard.headers if k == "Set-Cookie")
    csrf = next(v.split("=", 1)[1] for v in cookies.split("; ") if v.startswith("resono_csrf="))
    try:
        yield app, {"Cookie": cookies, "X-ReSono-CSRF": csrf}, str(tmp_path)
    finally:
        app.close()
        with psycopg.connect(require_test_database(url)) as connection:
            connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
            connection.execute("DROP SCHEMA IF EXISTS vault_background_queue CASCADE")


def test_route_inventory_has_no_duplicates() -> None:
    keys = [route.key for route in ROUTES]
    assert len(keys) == len(set(keys))


def test_r1_inventory_and_r2_snapshots(routes_app) -> None:
    app, owner, tmp = routes_app
    wrong_csrf = {**owner, "X-ReSono-CSRF": "wrong"}
    ordered = [r for r in ROUTES if not r.session_ending] + [r for r in ROUTES if r.session_ending]
    anonymous = {r.key: _call(app, r, {}, tmp) for r in ordered}
    no_csrf = {r.key: _call(app, r, wrong_csrf, tmp) for r in ordered}
    full = {r.key: _call(app, r, owner, tmp) for r in ordered}

    # R1: authentication and CSRF requirements per route.
    problems = []
    for route in ROUTES:
        if (route.auth == "session") != _session_failure(anonymous[route.key]):
            problems.append(f"{route.key}: auth={route.auth} but anonymous -> {anonymous[route.key]}")
        if route.auth == "bearer" and 200 <= anonymous[route.key].get("status", 500) < 300:
            problems.append(f"{route.key}: bearer route answered without a bearer -> {anonymous[route.key]}")
        if route.csrf != _csrf_failure(no_csrf[route.key]):
            problems.append(f"{route.key}: csrf={route.csrf} but wrong CSRF -> {no_csrf[route.key]}")
    assert not problems, "\n".join(problems)

    # R2: one snapshot per route (anonymous, wrong CSRF, signed-in owner).
    observed = {
        "routes": [
            {"route": r.key, "auth": r.auth, "csrf": r.csrf, "target": _redact(r.target, tmp),
             "anonymous": anonymous[r.key], "wrongCsrf": no_csrf[r.key], "owner": full[r.key]}
            for r in ROUTES
        ],
    }
    if os.getenv("UPDATE_ROUTE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps(observed, indent=1, sort_keys=True) + "\n")
    expected = json.loads(SNAPSHOT.read_text())
    assert [item["route"] for item in observed["routes"]] == [item["route"] for item in expected["routes"]]
    for got, want in zip(observed["routes"], expected["routes"]):
        assert got == want, got["route"]
