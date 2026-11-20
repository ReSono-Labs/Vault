"""AI providers: catalog, keys, preferences, account access and OAuth sign-in."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult, parse_qs

from app.vault_runtime.voice.openai_realtime import uses_subscription_live_transport
from .common import (
    LocalApiResponse,
    _csrf_token,
    _json_object,
    _optional_text,
    _required_text,
    _session_token,
)


class ProviderRoutes:
    """VaultLocalApiApp routes: ai providers: catalog, keys, preferences, account access and oauth sign-in."""

    def _route_providers(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_providers(
                method=method.upper(), path=path, query=target_parts.query,
                headers=headers, body=body,
            )
        except Exception as exc:
            code = getattr(exc, "code", "provider_request_failed")
            return LocalApiResponse(
                400 if isinstance(exc, ValueError) else 403,
                {"error": {"code": code, "message": str(exc)}},
            )

    def _handle_providers(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity = self._identity_service
        credentials = self._voice_provider_credentials
        if identity is None or credentials is None:
            raise RuntimeError("Local Voice provider management is unavailable.")
        oauth = self._provider_oauth
        if path == "/providers/gemini/oauth/callback" and method == "GET":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            values = parse_qs(query, keep_blank_values=True)
            state = values.get("state", [""])[0]
            code = values.get("code", [""])[0]
            oauth.complete_gemini(state=state, code=code)
            return LocalApiResponse(303, {"status": "connected"}, (("Location", "/browser-voice.html?providerOAuth=gemini"),))
        principal = identity.authenticate(session_token=_session_token(headers))
        if path == "/providers/openai/oauth/start" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.start_openai(principal))
        if path == "/providers/openai/oauth/poll" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.poll_openai(principal, _required_text(_json_object(body), "authSessionId")))
        if path == "/providers/gemini/oauth/start" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.start_gemini(principal, _required_text(_json_object(body), "redirectUri")))
        if path == "/providers/xai/oauth/start" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.start_xai(principal))
        if path == "/providers/xai/oauth/poll" and method == "POST":
            if oauth is None: raise RuntimeError("Provider OAuth is unavailable.")
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, oauth.poll_xai(principal, _required_text(_json_object(body), "authSessionId")))
        if self._voice_coordinator is None:
            raise RuntimeError("AI provider registry is unavailable.")
        descriptors = {item.provider_key: item for item in self._voice_coordinator.provider_descriptors()}
        if path == "/providers/catalog" and method == "GET":
            selected = credentials.selected_provider(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
            )
            return LocalApiResponse(200, {"selectedProviderKey": selected, "items": [
                {
                    **(
                        item_status := credentials.status(
                            principal, item.provider_key,
                            default_model_key=item.default_voice_model,
                            default_voice=item.default_voice,
                            default_background_model_key=item.default_text_model,
                        )
                    ),
                    "displayName": item.display_name,
                    "connectionMode": item.connection_mode,
                    "protocol": item.protocol,
                    "voices": list(item.voices),
                    "voiceModels": list(item.voice_models),
                    "textModels": list(item.text_models),
                    "negotiatedDataChannel": uses_subscription_live_transport(
                        auth_method=str(item_status.get("authMethod") or "api_key"),
                        model_key=str(item_status.get("modelKey") or item.default_voice_model),
                    ),
                    "dataChannelId": (
                        0
                        if uses_subscription_live_transport(
                            auth_method=str(item_status.get("authMethod") or "api_key"),
                            model_key=str(item_status.get("modelKey") or item.default_voice_model),
                        )
                        else None
                    ),
                    "selected": selected == item.provider_key,
                }
                for item in descriptors.values()
            ]})
        parts = path.removeprefix("/providers/").split("/")
        provider_key = parts[0] if parts else ""
        descriptor = descriptors.get(provider_key)
        if descriptor is None:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        if len(parts) == 2 and parts[1] == "auth-method" and method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            credentials.select_auth_method(
                principal, provider_key=provider_key,
                auth_method=_required_text(_json_object(body), "authMethod"),
            )
            return LocalApiResponse(200, credentials.status(
                principal, provider_key, default_model_key=descriptor.default_voice_model,
                default_voice=descriptor.default_voice,
                default_background_model_key=descriptor.default_text_model,
            ))
        if len(parts) == 2 and parts[1] == "oauth" and method == "DELETE":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            credentials.remove_oauth(principal, provider_key)
            return LocalApiResponse(200, credentials.status(
                principal, provider_key, default_model_key=descriptor.default_voice_model,
                default_voice=descriptor.default_voice,
                default_background_model_key=descriptor.default_text_model,
            ))
        if len(parts) == 2 and parts[1] == "select" and method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            credentials.select_provider(principal, provider_key)
            return LocalApiResponse(200, {"selectedProviderKey": provider_key})
        if len(parts) >= 3 and parts[1] == "users":
            target_user_id = parts[2]
            if not target_user_id or "/" in target_user_id:
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
            if method == "GET":
                return LocalApiResponse(200, credentials.account_access_status(principal, target_user_id, provider_key))
            if method == "POST":
                identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
                payload = _json_object(body)
                credentials.set_account_access(
                    principal, target_user_id=target_user_id,
                    provider_key=provider_key,
                    access_mode=_required_text(payload, "accessMode"),
                    api_key=_optional_text(payload, "apiKey"),
                    model_key=_optional_text(payload, "modelKey") or descriptor.default_voice_model,
                    background_model_key=_optional_text(payload, "backgroundModelKey") or descriptor.default_text_model,
                    voice=_optional_text(payload, "voice") or descriptor.default_voice,
                )
                return LocalApiResponse(200, credentials.account_access_status(principal, target_user_id, provider_key))
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        if len(parts) != 1:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        if method == "GET":
            return LocalApiResponse(200, credentials.status(
                principal, provider_key, default_model_key=descriptor.default_voice_model,
                default_voice=descriptor.default_voice,
                default_background_model_key=descriptor.default_text_model,
            ))
        if method == "DELETE":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            credentials.remove(principal, provider_key)
            return LocalApiResponse(200, {"status": "removed"})
        if method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            payload = _json_object(body)
            model_key = _required_text(payload, "modelKey")
            # Audio persona is an internal provider detail, not a user-facing model setting.
            voice = descriptor.default_voice
            background_model_key = (
                _optional_text(payload, "backgroundModelKey") or descriptor.default_text_model
            )
            api_key = _optional_text(payload, "apiKey")
            if api_key:
                credentials.set(
                    principal, provider_key=provider_key, api_key=api_key,
                    model_key=model_key, voice=voice, background_model_key=background_model_key,
                )
            else:
                credentials.update_preferences(
                    principal, provider_key=provider_key, model_key=model_key,
                    voice=voice, background_model_key=background_model_key,
                )
            return LocalApiResponse(200, credentials.status(
                principal, provider_key, default_model_key=descriptor.default_voice_model,
                default_voice=descriptor.default_voice,
                default_background_model_key=descriptor.default_text_model,
            ))
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
