"""System agents, tools and Voice sessions (the runtime handler; Background is delegated)."""
from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import SplitResult, parse_qs

from app.vault_runtime.system_agents.inventory import SYSTEM_AGENT_INVENTORY, AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.voice.greeting import connect_greeting_event
from app.vault_runtime.voice.openai_realtime import uses_subscription_live_transport
from app.vault_runtime.memory.openai_reviewer import MemoryReviewProviderError
from .common import (
    LocalApiResponse,
    _csrf_token,
    _json_object,
    _optional_text,
    _required_nonnegative_int,
    _required_query,
    _required_text,
    _session_token,
)


class VoiceRoutes:
    """VaultLocalApiApp routes: system agents, tools and voice sessions (the runtime handler; background is delegated)."""

    def _route_runtime(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_runtime(
                method=method.upper(), path=path, query=target_parts.query,
                headers=headers, body=body,
            )
        except Exception as exc:
            from app.vault_runtime.background_agent.errors import BackgroundRunConflictError
            code = getattr(exc, "code", "runtime_request_failed")
            status = (
                502 if isinstance(exc, MemoryReviewProviderError)
                else 409 if isinstance(exc, BackgroundRunConflictError)
                else 400 if isinstance(exc, ValueError)
                else 403
            )
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _handle_runtime(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes
    ) -> LocalApiResponse:
        identity = self._identity_service
        if identity is None:
            raise RuntimeError("Local identity service is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/system-agents":
            return LocalApiResponse(200, {"items": [
                {
                    "kind": item.kind.value, "displayName": item.display_name,
                    "interactive": item.interactive,
                }
                for item in SYSTEM_AGENT_INVENTORY
            ]})
        if method == "GET" and path == "/tools":
            if self._voice_tools is None:
                raise RuntimeError("Local tools are unavailable.")
            return LocalApiResponse(200, {"items": [
                {
                    "name": item.name,
                    "description": item.description,
                    "effectClass": item.effect_class,
                    "audiences": sorted(agent.value for agent in item.audiences),
                    "builtIn": item.tool_id.startswith("builtin."),
                    "category": _tool_category(item.tool_id, item.name),
                }
                for item in self._voice_tools.definitions(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                )
            ]})
        if method == "POST" and path == "/voice/sessions":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            payload = _json_object(body, max_bytes=self._max_body_bytes)
            if self._voice_coordinator is None or self._provider_credential_resolver is None:
                raise RuntimeError("Local Voice provider is unavailable.")
            provider_key = _required_text(payload, "providerKey")
            if self._companion_voice is not None and self._companion_voice.active_for(principal.user_id, principal.workspace_id):
                return LocalApiResponse(409, {"error": {"code": "voice_busy",
                    "message": "A Voice session is already active for this account on another device."}})
            if self._mcp_lifecycle is not None:
                self._mcp_lifecycle.restore_scope(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                    agent=AgentKind.VOICE,
                )
            credential = self._provider_credential_resolver(principal, provider_key)
            started = self._voice_coordinator.start(
                principal=principal,
                provider_key=provider_key,
                model_key=_required_text(payload, "modelKey"),
                connection_mode=_required_text(payload, "connectionMode"),
                credential=credential,
                voice=_optional_text(payload, "voice"),
                offer_sdp=_optional_webrtc_sdp(payload, "offerSdp"),
            )
            return LocalApiResponse(201, {
                "voiceRealtimeSessionId": started.session.voice_session_id,
                "providerKey": started.provider.provider_key,
                "modelKey": started.provider.model_key,
                "connectionMode": started.provider.connection_mode,
                "clientSecret": started.provider.client_secret,
                "expiresAt": started.provider.expires_at,
                "sdpAnswer": started.provider.sdp_answer,
                "sessionUpdate": started.provider.session_update_event,
                "protocol": started.provider.protocol,
                "websocketUrl": started.provider.websocket_url,
                "websocketProtocol": started.provider.websocket_protocol,
                "inputSampleRate": started.provider.input_sample_rate,
                "outputSampleRate": started.provider.output_sample_rate,
                "connectGreetingEvent": connect_greeting_event(started.context.display_name),
                "liveTranscription": started.live_transcription,
            })
        payload = _json_object(body) if method == "POST" else {}
        if method in {"POST", "DELETE"}:
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if path.startswith("/voice/sessions/") and "/preparation" in path:
            from app.vault_runtime.live_memory.voice_host import PREFIX
            session_id,suffix=path.removeprefix("/voice/sessions/").split("/preparation",1)
            runtime=self._conversation_runtime
            preparation=runtime.preparation if runtime is not None else None
            if preparation is None or self._voice_sessions is None:
                return LocalApiResponse(503,{"error":{"code":"voice_preparation_unavailable"}})
            self._voice_sessions.session(user_id=principal.user_id,workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,voice_session_id=session_id,require_open=True)
            source_id=PREFIX+session_id
            if method=="GET" and suffix=="":
                params=parse_qs(query)
                return LocalApiResponse(200,preparation.status(principal,source_id,
                    _required_text({"utteranceId":params.get("utteranceId",[""])[0]},"utteranceId"),
                    int(params.get("revision",["0"])[0])),(("Cache-Control","no-store"),))
            if method=="POST" and suffix=="/transcription":
                credential=self._provider_credential_resolver(principal,"openai",capability="live_transcription")
                result=self._voice_coordinator.start_transcription(principal=principal,
                    voice_session_id=session_id,credential=credential)
                return LocalApiResponse(201,{"clientSecret":result.client_secret},(("Cache-Control","no-store"),))
            if method=="POST" and suffix=="/delivered":
                return LocalApiResponse(200,preparation.delivered(principal,source_id,
                    _required_text(payload,"utteranceId"),_required_nonnegative_int(payload,"memoryCount"),
                    _required_nonnegative_int(payload,"toolCount") if "toolCount" in payload else 0))
            if method=="POST" and suffix=="":
                return LocalApiResponse(202,preparation.update(principal,source_id,payload),(("Cache-Control","no-store"),))
            if method=="DELETE" and suffix=="":
                return LocalApiResponse(200,preparation.discard(principal,source_id))
            return LocalApiResponse(404,{"error":{"code":"not_found"}})
        if method == "GET" and path == "/voice/plan":
            if self._provider_credential_resolver is None:
                raise RuntimeError("Local Voice provider is unavailable.")
            params = parse_qs(query, keep_blank_values=True)
            provider_key = _required_query(params, "providerKey")
            model_key = _required_query(params, "modelKey")
            credential = self._provider_credential_resolver(principal, provider_key)
            subscription_live = uses_subscription_live_transport(
                auth_method=credential.auth_method,
                model_key=model_key,
            )
            return LocalApiResponse(200, {
                "transport": "openai-realtime",
                "negotiatedDataChannel": subscription_live,
                "dataChannelId": 0 if subscription_live else None,
            })
        if method == "GET" and path.startswith("/voice/sessions/") and path.endswith("/decision-review"):
            if self._decision_review is None:
                return LocalApiResponse(503,{"error":{"code":"decision_review_disabled","message":"Procedural review is disabled."}})
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/decision-review").strip("/")
            return LocalApiResponse(200,self._decision_review.status(principal=principal,voice_session_id=voice_session_id),
                                    (("Cache-Control","no-store"),))
        if method == "POST" and path.startswith("/voice/sessions/") and path.endswith("/close"):
            if self._voice_sessions is None:
                raise RuntimeError("Local Voice sessions are unavailable.")
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/close").strip("/")
            return LocalApiResponse(200, self._close_voice_session(principal, voice_session_id,
                                                                   payload.get("transcriptCaptureFailures")))
        if method == "POST" and path.startswith("/voice/sessions/") and path.endswith("/events"):
            if self._voice_learning is None:
                raise RuntimeError("Local Voice learning is unavailable.")
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/events").strip("/")
            event = self._voice_learning.capture(
                principal=principal, voice_session_id=voice_session_id,
                provider_event_id=_required_text(payload, "providerEventId"),
                event_type=_required_text(payload, "eventType"),
                role=_required_text(payload, "role"),
                transcript_text=_required_text(payload, "transcriptText") if "transcriptText" in payload else None,
                transcript_entry_index=_required_nonnegative_int(payload, "transcriptEntryIndex") if "transcriptEntryIndex" in payload else None,
                payload=payload.get("providerPayload", {}),
            )
            return LocalApiResponse(201 if event.accepted else 200, {
                "accepted": event.accepted, "providerEventId": event.provider_event_id,
            })
        if method == "POST" and path.startswith("/voice/sessions/") and path.endswith("/tools/call"):
            if self._voice_tools is None or self._voice_sessions is None:
                raise RuntimeError("Local Voice tools are unavailable.")
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/tools/call").strip("/")
            self._voice_sessions.session(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id, voice_session_id=voice_session_id,
                require_open=True,
            )
            arguments = payload.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            utterance_id = payload.get("userUtteranceId")
            if utterance_id is not None and (not isinstance(utterance_id, int) or utterance_id < 0):
                raise ValueError("userUtteranceId must be a non-negative integer")
            from app.vault_runtime.voice.tools import VoiceToolCallPending
            context = ToolInvocationContext(
                agent=AgentKind.VOICE, user_id=principal.user_id,
                workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,
                voice_session_id=voice_session_id,
                tool_call_id=_required_text(payload, "toolCallId"),
                user_utterance=_optional_text(payload, "userUtterance"),
                user_utterance_id=utterance_id,
            )
            try:
                result = self._voice_tools.invoke(name=_required_text(payload, "name"),
                                                  arguments=arguments, context=context)
            except VoiceToolCallPending:
                approvals = getattr(self._conversation_runtime, "approvals", None) if self._conversation_runtime is not None else None
                question = approvals.pending(principal, voice_session_id=voice_session_id) if approvals is not None else None
                return LocalApiResponse(
                    202,
                    {"pending": True, **({"approval": question} if question is not None else {})},
                    (("Cache-Control", "no-store"),),
                )
            return LocalApiResponse(200, result.mcp_result())
        if method == "POST" and path.startswith("/voice/sessions/") and path.endswith("/finalize"):
            if self._voice_learning is None or self._voice_sessions is None:
                raise RuntimeError("Local Voice learning is unavailable.")
            voice_session_id = path.removeprefix("/voice/sessions/").removesuffix("/finalize").strip("/")
            self._voice_sessions.session(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id, voice_session_id=voice_session_id,
                require_open=False,
            )
            if self._voice_sessions.capture_state(user_id=principal.user_id,workspace_id=principal.workspace_id,
                    local_session_id=principal.session_id,voice_session_id=voice_session_id)=="incomplete":
                return LocalApiResponse(409,{"error":{"code":"capture_incomplete",
                    "message":"Transcript capture was incomplete; review is blocked."}})
            finalized = (self._conversation_runtime.finalize_voice(principal=principal,voice_session_id=voice_session_id)
                if self._conversation_runtime is not None else self._voice_learning.finalize(
                    principal=principal,voice_session_id=voice_session_id))
            if finalized is None:
                return LocalApiResponse(409, {
                    "error": {"code": "nothing_to_review", "message": "Session has no transcript to review."},
                })
            response = {
                "voiceRealtimeSessionId": voice_session_id,
                "learning": "already_completed" if finalized.already_completed else "completed",
                "memoryCount": finalized.memory_count,
                "embeddedCount": finalized.embedded_count,
                "embeddingsAvailable": finalized.embeddings_available,
                "summary": finalized.summary,
            }
            if finalized.decision_review is not None:
                response["decisionReview"] = finalized.decision_review
            return LocalApiResponse(200,response)
        background = self._handle_background(principal, method=method, path=path, payload=payload)
        if background is not None:
            return background
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _close_voice_session(self, principal, voice_session_id: str, transcript_capture_failures=None) -> dict[str, Any]:
        """Close a Voice session and queue its review (browser Voice and Link Companion share this)."""
        if self._voice_sessions is None:
            raise RuntimeError("Local Voice sessions are unavailable.")
        if self._conversation_runtime is not None and self._conversation_runtime.preparation is not None:
            from app.vault_runtime.live_memory.voice_host import PREFIX
            current=self._voice_sessions.session(user_id=principal.user_id,workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,voice_session_id=voice_session_id)
            if current.status in {"starting","transport_open"}:
                self._conversation_runtime.preparation.discard(principal,PREFIX+voice_session_id)
        session = self._voice_sessions.close_session(
            user_id=principal.user_id, workspace_id=principal.workspace_id,
            local_session_id=principal.session_id, voice_session_id=voice_session_id,
            transcript_capture_failures=transcript_capture_failures,
        )
        if self._voice_coordinator is not None:
            self._voice_coordinator.close_modes(voice_session_id)
        response: dict[str, Any] = {
            "voiceRealtimeSessionId": session.voice_session_id, "status": session.status,
        }
        capture_state = self._voice_sessions.capture_state(user_id=principal.user_id,workspace_id=principal.workspace_id,
            local_session_id=principal.session_id,voice_session_id=voice_session_id)
        response["captureState"] = capture_state
        if capture_state=="incomplete":
            response.update(learning="deferred_incomplete_capture",decisionReview={"state":"blocked_incomplete_capture"})
            return response
        if self._voice_learning is not None and self._conversation_runtime is not None:
            self._conversation_runtime.queue_voice_review(principal=principal,voice_session_id=voice_session_id)
            response.update(learning="queued")
            return response
        if self._voice_learning is not None:
            finalized = (self._conversation_runtime.finalize_voice(principal=principal,voice_session_id=voice_session_id)
                if self._conversation_runtime is not None else self._voice_learning.finalize(
                    principal=principal,voice_session_id=voice_session_id))
            response.update({
                "learning": "completed" if finalized is not None else "skipped_empty",
                "memoryCount": finalized.memory_count if finalized is not None else 0,
                "embeddedCount": finalized.embedded_count if finalized is not None else 0,
                "embeddingsAvailable": finalized.embeddings_available if finalized is not None else False,
            })
            if finalized is not None and finalized.decision_review is not None:
                response["decisionReview"] = finalized.decision_review
        return response


def _optional_webrtc_sdp(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    text = value.lstrip("\ufeff")
    if not text.lstrip(" \t").startswith("v=0"):
        return None
    return text


def _tool_category(tool_id: str, name: str) -> str:
    """Expose the canonical tool family already encoded in built-in names/IDs."""
    if tool_id.startswith("mcp:"):
        return "MCP"
    prefixes = (
        ("memory_", "Memory"), ("email_", "Email"),
        ("calendar_", "Calendar"), ("contacts_", "Contacts"),
        ("agent2agent_", "Agent2Agent"),
    )
    for prefix, category in prefixes:
        if name.startswith(prefix):
            return category
    if name == "web_search":
        return "Web"
    if name in {"load_agent_skill", "read_agent_skill_resource"}:
        return "Skills"
    return "Other"
