import hashlib


def hash_token(token: str) -> str:
    """Preserve Voice's opaque-token SHA-256 storage representation."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
