"""Chat: the conversation API behind the host's sign-in and CSRF check."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult

from app.vault_runtime.local_identity.repository import LocalIdentityError
from app.vault_runtime.tools.strict_json import STRICT_JSON_MAX_BYTES
from .common import LocalApiResponse, _csrf_token, _json_object, _session_token


class ConversationRoutes:
    """VaultLocalApiApp routes: chat: the conversation api behind the host's sign-in and csrf check."""

    def _route_conversations(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        from app.vault_runtime.conversation.api import handle_conversation_api
        from app.vault_runtime.conversation.contracts import AuthorizationError,ConflictError,InputError,NotFoundError
        no_store = (("Cache-Control","no-store"),)
        try:
            if self._identity_service is None or self._conversation_runtime is None:
                return LocalApiResponse(503,{"error":{"code":"conversation_unavailable"}},no_store)
            principal = self._identity_service.authenticate(session_token=_session_token(headers))
            if method.upper()!="GET":
                self._identity_service.require_csrf(principal=principal,csrf_token=_csrf_token(headers))
            return handle_conversation_api(self._conversation_runtime,principal,method=method.upper(),path=path,
                query=target_parts.query,headers=headers,payload=_json_object(body,
                    max_bytes=min(self._max_body_bytes,7_100_000) if method.upper()=="POST" and path.endswith("/attachments")
                    else STRICT_JSON_MAX_BYTES) if body else {})
        except (LocalIdentityError,AuthorizationError) as exc:
            return LocalApiResponse(403,{"error":{"code":"conversation_authority_required","message":str(exc)}},no_store)
        except (InputError,ValueError,TypeError):
            return LocalApiResponse(400,{"error":{"code":"invalid_conversation_request"}},no_store)
        except NotFoundError:
            return LocalApiResponse(404,{"error":{"code":"conversation_not_found"}},no_store)
        except ConflictError as exc:
            return LocalApiResponse(409,{"error":{"code":"conversation_conflict","message":str(exc)}},no_store)
        except Exception:
            return LocalApiResponse(503,{"error":{"code":"conversation_unavailable"}},no_store)
