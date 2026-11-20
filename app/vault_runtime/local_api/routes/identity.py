"""Local identity: setup, onboarding, sign-in, sessions, local users and workspaces."""
from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import SplitResult, parse_qs, quote

from app.vault_runtime.local_identity.models import LocalPrincipal, LocalSessionTokens
from app.vault_runtime.local_identity.repository import LocalIdentityError
from .common import (
    LocalApiResponse,
    _cookie_value,
    _csrf_token,
    _header,
    _json_object,
    _optional_text,
    _required_text,
    _session_token,
)


class IdentityRoutes:
    """VaultLocalApiApp routes: local identity: setup, onboarding, sign-in, sessions, local users and workspaces."""

    def _route_identity_setup_start(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            secure_cookies = _request_uses_secure_cookies(headers)
            values = parse_qs(target_parts.query, keep_blank_values=True).get("credential", [])
            setup_credential = values[0].strip() if len(values) == 1 else ""
            self._identity_service.validate_setup_credential(setup_credential)
            return LocalApiResponse(303, {"status": "ready"}, (
                ("Set-Cookie", f"resono_setup_resume={setup_credential}; Path=/; HttpOnly; SameSite=Strict{_secure_cookie_suffix(secure_cookies)}"),
                # Carry the already validated one-time proof into the local
                # onboarding document. Some mobile browsers do not retain a
                # Set-Cookie response across a certificate-interstitial/303
                # transition. The UI removes this query immediately after
                # the owner credential is consumed.
                ("Location", f"/browser-voice.html?setup=fresh&bootstrap={quote(setup_credential, safe='')}"),
                ("Cache-Control", "no-store"),
            ))
        except (LocalIdentityError, ValueError) as exc:
            code = getattr(exc, "code", "invalid_request")
            return LocalApiResponse(403, {"error": {"code": code, "message": str(exc)}}, (("Cache-Control", "no-store"),))

    def _route_identity(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_local_identity(
                method=method.upper(), path=path, headers=headers, body=body
            )
        except (LocalIdentityError, ValueError) as exc:
            code = getattr(exc, "code", "invalid_request")
            status = 401 if code in {"invalid_credentials", "local_session_invalid"} else 403
            if code in {"local_identity_conflict", "local_user_limit_reached"}:
                status = 409
            if isinstance(exc, ValueError):
                status = 400
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _handle_local_identity(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes
    ) -> LocalApiResponse:
        service = self._identity_service
        if service is None:
            raise RuntimeError("Local identity service is unavailable.")
        if method == "GET" and path == "/identity/status":
            return LocalApiResponse(200, {"setupComplete": service.setup_complete()})
        payload = _json_object(body) if method == "POST" else {}
        secure_cookies = _request_uses_secure_cookies(headers)
        if method == "POST" and path == "/identity/setup-session":
            setup_credential = _required_text(payload, "setupCredential")
            service.validate_setup_credential(setup_credential)
            return LocalApiResponse(200, {"status": "ready"}, (
                ("Set-Cookie", f"resono_setup_resume={setup_credential}; Path=/; HttpOnly; SameSite=Strict{_secure_cookie_suffix(secure_cookies)}"),
            ))
        if method == "POST" and path == "/identity/onboard":
            tokens, username, recovery_password = service.bootstrap_owner_minimal(
                setup_credential=_required_text(payload, "setupCredential"),
                display_name=_required_text(payload, "displayName"),
                experience_style=_required_text(payload, "experienceStyle"),
            )
            response = _session_response(tokens, status_code=201, secure=secure_cookies)
            return LocalApiResponse(
                response.status_code,
                {**response.payload, "recovery": {
                    "username": username, "generatedPassword": recovery_password,
                    "mustStoreNow": True,
                }},
                response.headers,
            )
        if method == "POST" and path == "/identity/register":
            setup_credential = _optional_text(payload, "setupCredential") or _cookie_value(headers, "resono_setup_resume")
            tokens = service.bootstrap_owner(
                setup_credential=setup_credential,
                username=_required_text(payload, "username"),
                password=_required_text(payload, "password"),
                display_name=_required_text(payload, "displayName"),
                experience_style=_required_text(payload, "experienceStyle"),
            )
            response = _session_response(tokens, status_code=201, secure=secure_cookies)
            return LocalApiResponse(response.status_code, response.payload, (*response.headers,
                ("Set-Cookie", f"resono_setup_resume=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{_secure_cookie_suffix(secure_cookies)}"),
            ))
        if method == "POST" and path == "/identity/login":
            tokens = service.login(
                username=_required_text(payload, "username"),
                password=_required_text(payload, "password"),
            )
            return _session_response(tokens, secure=secure_cookies)
        if method == "POST" and path == "/identity/activate":
            return _session_response(service.activate_user(
                setup_credential=_required_text(payload, "setupCredential"),
                new_password=_required_text(payload, "newPassword"),
            ), secure=secure_cookies)
        session_token = _session_token(headers)
        if method == "POST" and path == "/identity/token/refresh":
            return _session_response(service.refresh(
                session_token=session_token, csrf_token=_csrf_token(headers)
            ), secure=secure_cookies)
        principal = service.authenticate(session_token=session_token, allow_restricted=True)
        restricted_paths = {"/me", "/identity/password", "/identity/logout"}
        if principal.must_change_password and path not in restricted_paths:
            from app.vault_runtime.local_identity.service import LocalPasswordChangeRequiredError
            raise LocalPasswordChangeRequiredError("Password change is required before using Vault.")
        if method == "GET" and path == "/me":
            return LocalApiResponse(200, {"user": _principal_payload(principal)})
        if method == "POST" and path == "/identity/logout":
            service.logout(session_token=session_token, csrf_token=_csrf_token(headers))
            return LocalApiResponse(200, {"status": "logged_out"}, _clear_session_cookie_headers(secure=secure_cookies))
        if method == "POST" and path == "/local-users":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            provisioned = service.provision_user(
                actor=principal, username=_required_text(payload, "username"),
                password=_optional_text(payload, "password"),
                password_mode=_optional_text(payload, "passwordMode") or "temporary_password",
                age_group=_required_text(payload, "ageGroup"),
                display_name=_required_text(payload, "displayName"),
                experience_style=_required_text(payload, "experienceStyle"),
            )
            return LocalApiResponse(201, {
                "userId": provisioned.user_id, "workspaceId": provisioned.workspace_id,
                "passwordMode": provisioned.password_mode,
                "setupCredential": provisioned.setup_credential,
            })
        if method == "GET" and path == "/local-users":
            return LocalApiResponse(200, {"items": service.list_users(actor=principal)})
        local_user_operation = _local_user_operation(path)
        if method == "POST" and local_user_operation is not None:
            user_id, operation = local_user_operation
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            if operation == "password-reset":
                setup_credential = service.reset_user_password(
                    actor=principal, user_id=user_id,
                    new_password=_optional_text(payload, "newPassword"),
                    password_mode=_optional_text(payload, "passwordMode") or "temporary_password",
                )
                return LocalApiResponse(200, {
                    "status": "password_reset", "setupCredential": setup_credential,
                })
            if operation == "remove":
                service.remove_user(actor=principal, user_id=user_id)
                return LocalApiResponse(200, {"status": "account_removed"})
        if method == "POST" and path == "/identity/password":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            service.change_password(
                principal=principal, current_password=_required_text(payload, "currentPassword"),
                new_password=_required_text(payload, "newPassword"),
            )
            return LocalApiResponse(200, {"status": "password_changed"})
        if method == "GET" and path == "/workspaces":
            workspaces = service.list_workspaces(principal=principal)
            return LocalApiResponse(200, {"items": [
                {"workspaceId": item.workspace_id, "displayName": item.display_name,
                 "ownerUserId": item.owner_user_id, "membershipType": item.membership_type}
                for item in workspaces
            ]})
        if method == "POST" and path == "/workspaces":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            workspace_id = service.create_workspace(
                principal=principal, display_name=_required_text(payload, "displayName")
            )
            return LocalApiResponse(201, {"workspaceId": workspace_id})
        if method == "POST" and path == "/workspaces/select":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            service.switch_workspace(
                principal=principal, workspace_id=_required_text(payload, "workspaceId")
            )
            return LocalApiResponse(200, {"user": _principal_payload(
                service.authenticate(session_token=session_token)
            )})
        if method == "POST" and path == "/workspaces/members":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            service.add_member(
                principal=principal, workspace_id=_required_text(payload, "workspaceId"),
                username=_required_text(payload, "username"),
            )
            return LocalApiResponse(200, {"status": "member_added"})
        if method == "POST" and path == "/workspaces/members/revoke":
            service.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            service.revoke_member(
                principal=principal, workspace_id=_required_text(payload, "workspaceId"),
                username=_required_text(payload, "username"),
            )
            return LocalApiResponse(200, {"status": "member_revoked"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})


def _local_user_operation(path: str) -> tuple[str, str] | None:
    parts = path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "local-users" or parts[2] not in {"password-reset", "remove"}:
        return None
    user_id = parts[1].strip()
    return (user_id, parts[2]) if user_id else None


def _principal_payload(principal: LocalPrincipal) -> dict[str, Any]:
    return {
        "userId": principal.user_id, "username": principal.username,
        "displayName": principal.display_name, "experienceStyle": principal.experience_style,
        "isDeviceOwner": principal.is_device_owner,
        "passwordMode": principal.password_mode,
        "mustChangePassword": principal.must_change_password,
        "ageGroup": principal.age_group,
        "sessionId": principal.session_id, "activeWorkspaceId": principal.workspace_id,
        "expiresAt": principal.expires_at.isoformat(),
    }


def _session_response(
    tokens: LocalSessionTokens, *, status_code: int = 200, secure: bool = False,
) -> LocalApiResponse:
    return LocalApiResponse(
        status_code, {"user": _principal_payload(tokens.principal)},
        _session_cookie_headers(tokens.session_token, tokens.csrf_token, secure=secure),
    )


def _session_cookie_headers(
    session_token: str, csrf_token: str, *, secure: bool = False,
) -> tuple[tuple[str, str], ...]:
    suffix = _secure_cookie_suffix(secure)
    return (
        ("Set-Cookie", f"resono_refresh={session_token}; Path=/; HttpOnly; SameSite=Strict{suffix}"),
        ("Set-Cookie", f"resono_csrf={csrf_token}; Path=/; SameSite=Strict{suffix}"),
    )


def _clear_session_cookie_headers(*, secure: bool = False) -> tuple[tuple[str, str], ...]:
    suffix = _secure_cookie_suffix(secure)
    return (
        ("Set-Cookie", f"resono_refresh=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{suffix}"),
        ("Set-Cookie", f"resono_csrf=; Path=/; Max-Age=0; SameSite=Strict{suffix}"),
    )


def _request_uses_secure_cookies(headers: Mapping[str, str]) -> bool:
    return (_header(headers, "x-resono-request-secure") or "") == "1"


def _secure_cookie_suffix(secure: bool) -> str:
    return "; Secure" if secure else ""
