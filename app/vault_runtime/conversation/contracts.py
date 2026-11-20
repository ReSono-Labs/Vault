from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

INPUT_CONTRACT_VERSION = 1
MAX_INPUT_BYTES = 65536


class ConversationError(RuntimeError):
    """Safe domain error; no database details in the message."""


class AuthorizationError(ConversationError):
    pass


class NotFoundError(ConversationError):
    pass


class ConflictError(ConversationError):
    pass


class InputError(ConversationError):
    pass


def _utf8(value: str) -> bytes:
    if not isinstance(value, str) or "\x00" in value:
        raise InputError("Text must be valid UTF-8 without NUL bytes.")
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError:
        raise InputError("Text must be valid UTF-8 without NUL bytes.") from None


def identifier(value: str) -> str:
    _utf8(value)
    normalized = value.strip()
    if not normalized or len(normalized.encode("utf-8")) > 256:
        raise InputError("Identifiers must contain 1 to 256 UTF-8 bytes.")
    return normalized


def text_fingerprint(input_text: str) -> str:
    encoded = _utf8(input_text)
    if not input_text.strip() or len(encoded) > MAX_INPUT_BYTES:
        raise InputError("Input must contain nonblank text within 65536 UTF-8 bytes.")
    return sha256(encoded).hexdigest()


def history_version(value: int) -> int:
    if type(value) is not int or value < 0:
        raise InputError("History version must be a nonnegative integer.")
    return value


@dataclass(frozen=True, slots=True)
class ConversationSegment:
    segment_id: str
    conversation_id: str
    user_id: str
    workspace_id: str
    ordinal: int
    state: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Conversation:
    conversation_id: str
    user_id: str
    workspace_id: str
    create_key: str
    history_version: int
    next_turn_ordinal: int
    state: str
    title: str
    created_at: datetime
    updated_at: datetime
    segments: tuple[ConversationSegment, ...]


@dataclass(frozen=True, slots=True)
class SubmittedTurn:
    turn_id: str
    conversation_id: str
    segment_id: str
    user_id: str
    workspace_id: str
    ordinal: int
    submission_key: str
    input_text: str
    input_fingerprint: str
    submitted_history_version: int
    state: str
    created_at: datetime
    updated_at: datetime
    duplicate: bool
    history_version: int

    @property
    def input_contract_version(self) -> int:
        return INPUT_CONTRACT_VERSION
