"""External memory: pairing, integrations, and the v1 contract for integration bearers."""
from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import SplitResult
from .common import (
    LocalApiResponse,
    _bearer_token,
    _csrf_token,
    _json_object,
    _required_text,
    _session_token,
    _text_tuple,
)


class ExternalMemoryRoutes:
    """VaultLocalApiApp routes: external memory: pairing, integrations, and the v1 contract for integration bearers."""

    def _route_external_memory_pairing(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_external_memory_pairing(
                method=method.upper(), path=path, body=body,
            )
        except Exception as exc:
            code = getattr(exc, "code", "external_memory_pairing_failed")
            status = 400 if isinstance(exc, ValueError) else 403
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _route_external_memory_integrations(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_external_memory_integrations(
                method=method.upper(), path=path, headers=headers, body=body,
            )
        except Exception as exc:
            code = getattr(exc, "code", "external_memory_request_failed")
            status = 400 if isinstance(exc, ValueError) else 403
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _route_external_memory(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_external_memory(
                method=method.upper(), path=path, headers=headers, body=body,
            )
        except Exception as exc:
            code = getattr(exc, "code", "external_memory_request_failed")
            status = 400 if isinstance(exc, ValueError) else 403
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _handle_external_memory_pairing(
        self, *, method: str, path: str, body: bytes,
    ) -> LocalApiResponse:
        repository = self._external_memory_integrations
        if repository is None:
            raise RuntimeError("External memory integrations are unavailable.")
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        payload = _json_object(body)
        if path == "/external-memory/pairing/start":
            grants = tuple(sorted(set(_text_tuple(payload, "grants", required=True))))
            if any(grant not in {"search", "propose", "correct", "forget"} for grant in grants):
                raise ValueError("grants may contain only search, propose, correct and forget")
            result = repository.start_pairing(
                display_name=_required_text(payload, "displayName")[:128],
                adapter_kind=_required_text(payload, "adapterKind")[:64], grants=grants,
                poll_token=_required_text(payload, "pollToken"),
                runtime_token_hash=_required_text(payload, "runtimeTokenHash"),
            )
            return LocalApiResponse(201, result, (("Cache-Control", "no-store"),))
        if path == "/external-memory/pairing/status":
            status = repository.pairing_status(
                pairing_id=_required_text(payload, "pairingId"),
                poll_token=_required_text(payload, "pollToken"),
            )
            return LocalApiResponse(200, {"status": status}, (("Cache-Control", "no-store"),))
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_external_memory_integrations(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity = self._identity_service
        repository = self._external_memory_integrations
        if identity is None or repository is None:
            raise RuntimeError("External memory integrations are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/external-memory/integrations":
            return LocalApiResponse(200, {"items": [
                _external_integration_payload(item) for item in repository.list(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                )
            ]})
        if method == "GET" and path.startswith("/external-memory/integrations/pairing/"):
            code = path.removeprefix("/external-memory/integrations/pairing/")
            return LocalApiResponse(200, repository.pairing_by_code(pairing_code=code))
        if method not in {"POST", "DELETE"}:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        if path.startswith("/external-memory/integrations/pairing/") and path.endswith("/approve"):
            pairing_id = path.removeprefix("/external-memory/integrations/pairing/").removesuffix("/approve").strip("/")
            integration = repository.approve_pairing(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                pairing_id=pairing_id,
            )
            return LocalApiResponse(200, _external_integration_payload(integration))
        if path == "/external-memory/integrations":
            grants = tuple(sorted(set(_text_tuple(payload, "grants", required=True))))
            if any(grant not in {"search", "propose", "correct", "forget"} for grant in grants):
                raise ValueError("grants may contain only search, propose, correct and forget")
            enrollment = repository.enroll(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                display_name=_required_text(payload, "displayName")[:128],
                adapter_kind=_required_text(payload, "adapterKind")[:64], grants=grants,
            )
            result = _external_integration_payload(enrollment.integration)
            result["credential"] = enrollment.credential
            return LocalApiResponse(201, result, (("Cache-Control", "no-store"),))
        suffix = path.removeprefix("/external-memory/integrations/")
        integration_id, _, operation = suffix.partition("/")
        if method == "DELETE" and integration_id and not operation:
            repository.remove_revoked(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                integration_id=integration_id,
            )
            return LocalApiResponse(200, {"status": "removed"})
        if integration_id and operation == "revoke":
            repository.revoke(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                integration_id=integration_id,
            )
            return LocalApiResponse(200, {"status": "revoked"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})

    def _handle_external_memory(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        service = self._external_memory
        if service is None:
            raise RuntimeError("External memory service is unavailable.")
        if method == "GET" and path == "/external-memory/v1/health":
            return LocalApiResponse(200, {
                "status": "ok", "contractVersion": "1",
                "operations": ["startup", "search", "get", "propose", "correct", "forget", "disconnect"],
            })
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        credential = _bearer_token(headers)
        payload = _json_object(body)
        request_id = _required_text(payload, "requestId")
        if path == "/external-memory/v1/disconnect":
            repository = self._external_memory_integrations
            if repository is None:
                raise RuntimeError("External memory integrations are unavailable.")
            repository.disconnect_credential(credential=credential)
            return LocalApiResponse(200, {"requestId": request_id, "status": "revoked"})
        if path == "/external-memory/v1/startup":
            memories = service.startup(
                credential=credential, request_id=request_id, limit=payload.get("limit", 8),
            )
            return LocalApiResponse(200, {
                "items": [_external_memory_record_payload(item) for item in memories],
            })
        if path == "/external-memory/v1/search":
            matches = service.search(
                credential=credential, request_id=request_id,
                query=_required_text(payload, "query"), limit=payload.get("limit", 8),
            )
            return LocalApiResponse(200, {"items": [_external_memory_match_payload(item) for item in matches]})
        if path == "/external-memory/v1/get":
            memory = service.get(
                credential=credential, request_id=request_id,
                memory_id=_required_text(payload, "memoryId"),
            )
            return LocalApiResponse(200, _external_memory_record_payload(memory))
        if path == "/external-memory/v1/propose":
            evidence = payload.get("evidence", "")
            if not isinstance(evidence, str):
                raise ValueError("evidence must be a string")
            proposal = service.propose(
                credential=credential, request_id=request_id,
                content=_required_text(payload, "content"),
                evidence=evidence,
            )
            result = proposal.result
            return LocalApiResponse(202, {
                "requestId": proposal.request_id, "status": "reviewed",
                "memoryCount": result.memory_count, "alreadyCompleted": result.already_completed,
            })
        if path in {"/external-memory/v1/request-correction", "/external-memory/v1/request-forget"}:
            action_kind = "correct" if path.endswith("correction") else "forget"
            new_content = payload.get("newContent")
            if new_content is not None and not isinstance(new_content, str):
                raise ValueError("newContent must be a string")
            result = service.apply_action(
                credential=credential, request_id=request_id, action_kind=action_kind,
                memory_id=_required_text(payload, "memoryId"), proposed_content=new_content,
            )
            return LocalApiResponse(200, {
                "requestId": request_id, "status": "applied", "result": result,
            })
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})


def _external_integration_payload(record) -> dict[str, Any]:
    return {
        "integrationId": record.integration_id,
        "displayName": record.display_name,
        "adapterKind": record.adapter_kind,
        "grants": list(record.grants),
        "status": record.status,
        "createdAt": record.created_at.isoformat(),
        "revokedAt": record.revoked_at.isoformat() if record.revoked_at else None,
    }


def _external_memory_match_payload(match) -> dict[str, Any]:
    memory = match.memory
    payload = _external_memory_record_payload(memory)
    payload.update({
        "score": match.score,
        "matchMethods": list(match.match_methods),
    })
    return payload


def _external_memory_record_payload(memory) -> dict[str, Any]:
    return {
        "memoryId": memory.memory_id,
        "subjectId": memory.subject_id,
        "domain": memory.domain,
        "memoryType": memory.memory_type,
        "memoryKey": memory.memory_key,
        "content": memory.content_text,
        "sourceAuthority": memory.source_authority,
        "confidence": memory.confidence,
        "sensitivity": memory.sensitivity,
        "visibility": memory.visibility,
    }
