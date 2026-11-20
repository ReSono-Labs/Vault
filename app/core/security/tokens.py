import hashlib
from hmac import compare_digest


def hash_token(token: str) -> str:
    """Preserve Voice's opaque-token SHA-256 storage representation."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_equals(left: str, right: str) -> bool:
    """Compare bearer secrets without accepting mismatched lengths as equal."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    left_bytes, right_bytes = left.encode("utf-8"), right.encode("utf-8")
    if len(left_bytes) != len(right_bytes):
        compare_digest(left_bytes, left_bytes)
        return False
    return compare_digest(left_bytes, right_bytes)
