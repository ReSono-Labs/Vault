"""Link Companion: tools, Voice, Chat and pairing for the paired companion, and the owner's Link page."""
from __future__ import annotations

import logging
from typing import Mapping
from urllib.parse import SplitResult, parse_qs

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.voice.greeting import connect_greeting_event
from app.vault_runtime.link_companion.repository import LinkCompanionAuthorizationError
from .common import (
    API_LOGGER,
    LocalApiResponse,
    _csrf_token,
    _header,
    _json_object,
    _required_text,
    _session_token,
)


class LinkCompanionRoutes:
    """VaultLocalApiApp routes: link companion: tools, voice, chat and pairing for the paired companion, and the owner's link page."""

    def _route_link_companion_tools(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            principal = self._link_companion_principal(headers)
            if self._link_tools is None:
                return _companion_error(503, "tools_unavailable")
            payload = _json_object(body, max_bytes=4*1024*1024) if body else {}
            action = path.removeprefix("/link-companion/tools/")
            if method.upper() != "POST":
                return _companion_error(405, "method_not_allowed")
            if action == "publish":
                result = self._link_tools.publish(principal, payload.get("tools"))
            elif action == "poll":
                result = self._link_tools.poll(principal)
            elif action == "complete":
                result = self._link_tools.complete(principal, payload.get("id"), payload.get("result"))
            else:
                return _companion_error(404, "not_found")
            return LocalApiResponse(200, result, (("Cache-Control", "no-store"),))
        except LinkCompanionAuthorizationError:
            return _companion_error(401, "not_paired")
        except ValueError:
            return _companion_error(400, "invalid_tools_request")
        except Exception:
            logging.getLogger(API_LOGGER).warning("link_companion_tools_failed")
            return _companion_error(503, "tools_unavailable")

    def _route_link_companion_voice(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        return self._handle_link_companion_voice(
            method=method.upper(), path=path, query=target_parts.query, headers=headers, body=body,
        )

    def _route_link_companion_chat(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        return self._handle_link_companion_chat(
            method=method.upper(), path=path, query=target_parts.query, headers=headers, body=body,
        )

    def _route_link_front_door(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        """Link Front Door v1 for the paired companion (link_companion/front_door.py)."""
        from app.vault_runtime.conversation.contracts import ConflictError, InputError, NotFoundError
        from app.vault_runtime.link_companion import front_door
        from app.vault_runtime.link_companion.chat import ChatRejected
        no_store = (("Cache-Control", "no-store"),)
        def fail(status: int, code: str) -> LocalApiResponse:
            return LocalApiResponse(status, front_door.error_body(code), no_store)
        try:
            principal = self._link_companion_principal(headers)   # before any body parsing
        except Exception:
            return fail(401, "unauthorized")
        runtime = self._conversation_runtime
        if runtime is None:
            return fail(503, "unavailable")
        method = method.upper()
        if path == "/link/v1/capabilities":
            if method != "GET":
                return fail(405, "method_not_allowed")
            return LocalApiResponse(200, front_door.capabilities(
                images=getattr(runtime, "attachments", None) is not None), no_store)
        try:
            payload = _json_object(body, max_bytes=min(self._max_body_bytes, 9_000_000)) if body else {}
            status, value = front_door.handle(runtime, principal, method=method, path=path, payload=payload,
                                              idempotency_key=_header(headers, "idempotency-key"))
            return LocalApiResponse(status, value, no_store)
        except front_door.FrontDoorError as exc:
            return fail(exc.status, exc.code)
        except NotFoundError:
            return fail(404, "not_found")
        except ConflictError:
            return fail(409, "busy")
        except (ChatRejected, InputError, ValueError) as exc:
            reason = _rejection_reason(exc)
            logging.getLogger(API_LOGGER).warning("link_front_door_rejected %s: %s", type(exc).__name__, reason)
            body = front_door.error_body("invalid_request")
            body["error"]["message"] = reason
            return LocalApiResponse(400, body, no_store)
        except Exception as exc:
            logging.getLogger(API_LOGGER).warning("link_front_door_failed %s", type(exc).__name__)  # No message text or images.
            return fail(503, "unavailable")

    def _route_link_companion_pairing(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_link_companion_pairing(
                method=method.upper(), path=path, headers=headers, body=body,
            )
        except LinkCompanionAuthorizationError as exc:
            return LocalApiResponse(403, {"error": {"code": exc.code, "message": str(exc)}})
        except Exception as exc:
            code = getattr(exc, "code", "link_companion_pairing_failed")
            status = 400 if isinstance(exc, ValueError) else 403
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _route_link_companion(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_link_companion(
                method=method.upper(), path=path, headers=headers, body=body,
            )
        except LinkCompanionAuthorizationError as exc:
            return LocalApiResponse(403, {"error": {"code": exc.code, "message": str(exc)}})
        except Exception as exc:
            code = getattr(exc, "code", "link_companion_request_failed")
            status = 400 if isinstance(exc, ValueError) else 403
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _handle_link_companion_pairing(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        repository = self._link_companion
        if repository is None:
            raise RuntimeError("Link Companion pairing is unavailable.")
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        payload = _json_object(body)
        if path == "/link-companion/pairing/start":
            result = repository.start_pairing(
                display_name=_required_text(payload, "displayName")[:128],
                poll_token=_required_text(payload, "pollToken"),
            )
            return LocalApiResponse(201, result, (("Cache-Control", "no-store"),))
        if path == "/link-companion/pairing/status":
            status = repository.pairing_status(
                pairing_id=_required_text(payload, "pairingId"),
                poll_token=_required_text(payload, "pollToken"),
            )
            return LocalApiResponse(200, status, (("Cache-Control", "no-store"),))
        if path == "/link-companion/release":
            # Link ends the relationship when the owner removes Vault from Link: the paired
            # companion itself (its bearer) releases the pairing; Vault keeps no Link companion.
            self._link_companion_principal(headers)
            repository.unpair(reason="link_removed")
            if self._a2a_service is not None:
                self._a2a_service.clear_link_snapshot()
            return LocalApiResponse(200, {"status": "unpaired"}, (("Cache-Control", "no-store"),))
        if path == "/link-companion/agent-network/apply":
            self._link_companion_principal(headers)
            service = self._a2a_service
            if service is None:
                raise RuntimeError("Agent2Agent is unavailable.")
            inbound = payload.get("inbound")
            outbound = payload.get("outbound")
            if not isinstance(inbound, list) or not isinstance(outbound, list):
                raise ValueError("inbound and outbound must be lists")
            result = service.apply_link_snapshot(
                inbound=[item for item in inbound if isinstance(item, dict)],
                outbound=[item for item in outbound if isinstance(item, dict)],
            )
            return LocalApiResponse(200, result, (("Cache-Control", "no-store"),))
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _link_companion_principal(self, headers: Mapping[str, str]):
        """Authenticate the paired companion: its bearer token must be the linked owner session."""
        repository, identity = self._link_companion, self._identity_service
        if repository is None or identity is None:
            raise RuntimeError("Link Companion is unavailable.")
        linked = repository.link_session_id()
        authorization = _header(headers, "authorization") or ""
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        if not linked or not token:
            raise LinkCompanionAuthorizationError("Link Companion is not paired.")
        try:
            principal = identity.authenticate(session_token=token)
        except Exception:
            raise LinkCompanionAuthorizationError("Link Companion is not paired.") from None
        if principal.session_id != linked or not principal.is_device_owner:
            raise LinkCompanionAuthorizationError("Link Companion is not paired.")
        repository.touch_session(linked)
        return principal

    def _companion_voice_service(self):
        if self._companion_voice is None:
            if None in (self._voice_coordinator, self._provider_credential_resolver, self._voice_provider_credentials,
                        self._voice_tools, self._voice_learning, self._voice_sessions):
                return None
            from app.vault_runtime.voice.companion import CompanionVoiceService
            sessions = self._voice_sessions
            self._companion_voice = CompanionVoiceService(
                coordinator=self._voice_coordinator,
                credential_resolver=self._provider_credential_resolver,
                credential_status=lambda principal, provider: self._voice_provider_credentials.status(principal, provider),
                voice_tools=self._voice_tools, voice_learning=self._voice_learning,
                recent_session_open=lambda principal: sessions.recent_open_session(
                    user_id=principal.user_id, workspace_id=principal.workspace_id),
                finish_close=lambda principal, voice_session_id: self._close_voice_session(principal, voice_session_id),
                greeting=connect_greeting_event,
                # Same live memory + live tool routing engine and the same choice of word source as browser Voice.
                preparation=self._conversation_runtime.preparation if self._conversation_runtime is not None else None,
                live_enabled=self._voice_coordinator.live_preparation,
                transcription_credential=self._companion_transcription_credential,
                start_transcription=self._voice_coordinator.start_transcription,
            )
            runtime = self._conversation_runtime
            coordinator = getattr(runtime, "background_coordinator", None) if runtime is not None else None
            if coordinator is not None:
                from app.vault_runtime.voice.coordinator_tools import coordinator_replies
                self._companion_voice.hand_offs = getattr(runtime, "voice_hand_offs", None)
                self._companion_voice.hand_off_times = getattr(runtime, "voice_hand_off_times", None)
                self._companion_voice.pending_approvals = coordinator.pending_hand_off_approvals
                self._companion_voice.hand_off_replies = coordinator_replies(runtime)
        return self._companion_voice

    def _companion_transcription_credential(self, principal):
        available = self._voice_coordinator.transcription_available if self._voice_coordinator is not None else None
        if available is None or not available(principal):
            return None
        return self._provider_credential_resolver(principal, "openai", capability="live_transcription")

    def _handle_link_companion_voice(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        from app.vault_runtime.voice.companion import CompanionVoiceError
        parts = path.removeprefix("/link-companion/voice/").strip("/").split("/")
        service = self._companion_voice_service()
        no_store = (("Cache-Control", "no-store"),)
        if parts == ["health"] and method == "GET":
            reason = None
            try:
                principal = self._link_companion_principal(headers)
            except Exception:
                reason = "not_paired"
            if reason is None and service is None:
                reason = "not_ready"
            if reason is None:
                try:
                    selected = self._voice_provider_credentials.selected_provider(
                        user_id=principal.user_id, workspace_id=principal.workspace_id)
                except Exception:
                    selected = "openai"
                reason = "provider_unsupported" if selected != "openai" else service.readiness(principal)
            return LocalApiResponse(200, {"ready": reason is None, "modes": ["live"] if reason is None else [],
                                          **({"reason": reason} if reason else {})}, no_store)
        try:
            principal = self._link_companion_principal(headers)
        except Exception:
            return _companion_error(401, "not_paired")
        if service is None:
            return _companion_error(503, "not_ready")
        account = _header(headers, "x-link-account") or ""
        try:
            if parts == ["sessions"] and method == "POST":
                if len(body) > 40_000:
                    return _companion_error(413, "bound_exceeded")
                payload = _json_object(body, max_bytes=40_000)
                offer = payload.get("offerSdp")
                if not isinstance(offer, str) or not offer.strip() or len(offer.encode()) > 32_768:
                    return _companion_error(400, "rejected")
                if payload.get("modeKey") not in (None, "live"):
                    return _companion_error(400, "rejected")
                if self._mcp_lifecycle is not None:
                    self._mcp_lifecycle.restore_scope(user_id=principal.user_id,
                        workspace_id=principal.workspace_id, agent=AgentKind.VOICE)
                started = service.start(principal, offer_sdp=offer)
                if account:
                    from hashlib import sha256
                    logging.getLogger(API_LOGGER).info("companion_voice_started",
                        extra={"account": sha256(account.encode()).hexdigest()[:12]})
                sid = started["sessionId"]
                base = f"/link-companion/voice/sessions/{sid}"
                control = {
                    "events": base + "/events",
                    "connected": base + "/connected",
                    "close": base + "/close",
                    "approval": base + "/approval",
                }
                if started["liveTranscription"]:
                    control["transcription"] = base + "/transcription"
                return LocalApiResponse(201, {"sessionId": sid, "sdpAnswer": started["sdpAnswer"],
                    "maxSeconds": started["maxSeconds"], "idleSeconds": started["idleSeconds"],
                    "liveMemory": started["liveMemory"], "liveTranscription": started["liveTranscription"],
                    "control": control}, no_store)
            if len(parts) == 3 and parts[0] == "sessions":
                sid = parts[1]
                if len(body) > 65_536:
                    return _companion_error(413, "bound_exceeded")
                if parts[2] == "transcription" and method == "POST":
                    payload = _json_object(body, max_bytes=40_000)
                    offer = payload.get("offerSdp")
                    if not isinstance(offer, str) or not offer.strip() or len(offer.encode()) > 32_768:
                        return _companion_error(400, "rejected")
                    return LocalApiResponse(201, {"sdpAnswer": service.transcription(principal, sid, offer_sdp=offer)},
                                            no_store)
                if parts[2] == "connected" and method == "POST":
                    service.connected(principal, sid)
                    return LocalApiResponse(200, {"status": "connected"}, no_store)
                if parts[2] == "close" and method == "POST":
                    return LocalApiResponse(200, {"status": service.close(principal, sid)}, no_store)
                if parts[2] == "events" and method in ("GET", "POST"):
                    # POST {after, wait} is the form for clients that cannot send query strings.
                    source = (_json_object(body, max_bytes=1024) if body else {}) if method == "POST" else \
                        {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items() if v}
                    try:
                        after = max(0, int(source.get("after", 0)))
                        wait = max(0.0, min(float(source.get("wait", 20)), 25.0))
                    except (TypeError, ValueError):
                        return _companion_error(400, "rejected")
                    call = service.call(principal, sid)
                    events, latest = call.wait(after, wait)
                    return LocalApiResponse(200, {"events": events, "next": latest, "closed": call.closed}, no_store)
                if parts[2] in ("approval", "permission") and method == "POST":
                    call = service.call(principal, sid)
                    if call.closed or call.closing:
                        return _companion_error(409, "not_ready")
                    approvals = getattr(self._conversation_runtime, "approvals", None) if self._conversation_runtime is not None else None
                    if approvals is None:
                        return _companion_error(503, "not_ready")
                    payload = _json_object(body, max_bytes=4096)
                    action_id = payload.get("id") or payload.get("action_id")
                    choice = payload.get("choice")
                    if not isinstance(action_id, str) or not action_id.strip() or not isinstance(choice, str):
                        return _companion_error(400, "rejected")
                    from app.vault_runtime.background_agent.errors import (
                        BackgroundRunAuthorizationError, BackgroundRunConflictError,
                    )
                    try:
                        from app.vault_runtime.link_companion.chat import decide_background_action, is_background_action
                        if is_background_action(self._conversation_runtime, principal, action_id.strip()):
                            # Work handed to the coordinator on this call (Coordinator intake).
                            result = decide_background_action(
                                self._conversation_runtime, principal, action_id=action_id.strip(),
                                choice=choice.strip(), decision_id=f"link-voice:{sid}:{action_id.strip()}"[:128])
                        else:
                            result = approvals.answer(
                                principal, action_id.strip(), choice.strip(),
                                channel="link", voice_session_id=sid,
                            )
                    except (ValueError, BackgroundRunAuthorizationError, BackgroundRunConflictError):
                        return _companion_error(400, "rejected")
                    except Exception as exc:
                        if type(exc).__name__ != "ChatRejected":
                            raise
                        return _companion_error(400, "rejected")
                    if result == "expired":
                        return _companion_error(400, "rejected")
                    return LocalApiResponse(
                        200,
                        {"id": action_id.strip(), "action_id": action_id.strip(), "result": result},
                        no_store,
                    )
            return _companion_error(404, "not_found")
        except CompanionVoiceError as exc:
            status = {"not_found": 404, "busy": 409, "not_ready": 409, "provider_refused": 502,
                      "provider_unavailable": 503}.get(exc.code, 400)
            return _companion_error(status, exc.code, exc.retryable)
        except Exception:
            logging.getLogger(API_LOGGER).warning("link_companion_voice_failed")
            return _companion_error(503, "provider_unavailable", True)

    def _handle_link_companion_chat(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        from app.vault_runtime.conversation.contracts import ConflictError, InputError, NotFoundError
        from app.vault_runtime.link_companion.chat import ChatRejected, handle_chat
        no_store = (("Cache-Control", "no-store"),)
        def fail(status: int, code: str) -> LocalApiResponse:
            return _companion_error(status, code)
        parts = path.removeprefix("/link-companion/chat/").strip("/").split("/")
        runtime = self._conversation_runtime
        if parts == ["health"] and method == "GET":
            ready = False
            try:
                current = self._link_companion.current_link() if self._link_companion is not None else None
                ready = bool(current and current["status"] == "paired") and runtime is not None
            except Exception:
                ready = False
            images = ready and getattr(runtime, "attachments", None) is not None
            return LocalApiResponse(200, {"ready": ready, "images": images, "linkTools": bool(ready and self._link_tools is not None and self._link_tools.status()["ready"])}, no_store)
        try:
            principal = self._link_companion_principal(headers)
        except Exception:
            return fail(401, "not_paired")
        if runtime is None:
            return fail(503, "unavailable")
        try:
            payload = _json_object(body, max_bytes=min(self._max_body_bytes, 9_000_000)) if body else {}
            response = handle_chat(runtime, principal, method=method, parts=parts, query=query, payload=payload,
                respond=lambda status, value: LocalApiResponse(status, value, no_store))
            return response if response is not None else fail(404, "not_found")
        except NotFoundError:
            return fail(404, "not_found")
        except ConflictError:
            return fail(409, "busy")
        except (ChatRejected, InputError, ValueError) as exc:
            # The reason is Vault's own fixed wording (never message text or image bytes), so the
            # owner's apps and this log say why a message was refused.
            reason = _rejection_reason(exc)
            logging.getLogger(API_LOGGER).warning("link_companion_chat_rejected %s: %s", type(exc).__name__, reason)
            return LocalApiResponse(400, {"error": {"code": "rejected", "retryable": False, "reason": reason}}, no_store)
        except Exception as exc:
            logging.getLogger(API_LOGGER).warning("link_companion_chat_failed %s", type(exc).__name__)  # No message text, images or internal detail.
            return fail(503, "unavailable")

    def _handle_link_companion(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        repository = self._link_companion
        identity = self._identity_service
        if repository is None or identity is None:
            raise RuntimeError("Link Companion is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/link-companion":
            current = repository.current_link()
            return LocalApiResponse(200, current or {"status": "not_paired"})
        if method == "GET" and path.startswith("/link-companion/pairing/"):
            code = path.removeprefix("/link-companion/pairing/").strip("/")
            return LocalApiResponse(200, repository.pairing_by_code(pairing_code=code))
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if not principal.is_device_owner:
            raise LinkCompanionAuthorizationError("Only the Vault owner can confirm Link Companion.")
        if path.startswith("/link-companion/pairing/") and path.endswith("/approve"):
            pairing_id = path.removeprefix("/link-companion/pairing/").removesuffix("/approve").strip("/")
            # The companion gets its own owner session; its token never reaches this browser.
            companion = identity.issue_link_companion_session(principal=principal)
            try:
                approved = repository.approve_pairing(pairing_id=pairing_id,
                    session_id=companion.principal.session_id, companion_token=companion.session_token)
            except Exception:
                identity.revoke_link_companion_session(session_token=companion.session_token)
                raise
            return LocalApiResponse(200, approved)
        if path == "/link-companion/unpair":
            repository.unpair()
            if self._a2a_service is not None:
                self._a2a_service.clear_link_snapshot()
            return LocalApiResponse(200, {"status": "unpaired"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})


_COMPANION_RETRYABLE = {"busy", "unavailable", "provider_unavailable"}


def _rejection_reason(exc: Exception) -> str:
    """Why Vault refused a chat request: the exception's fixed wording, bounded to one line."""
    text = " ".join(str(exc).split())[:200]
    return text or type(exc).__name__


def _companion_error(status: int, code: str, retryable: bool | None = None) -> LocalApiResponse:
    """Link Companion errors: a short safe code and whether retrying the same request can help."""
    return LocalApiResponse(status, {"error": {"code": code,
        "retryable": code in _COMPANION_RETRYABLE if retryable is None else retryable}},
        (("Cache-Control", "no-store"),))
