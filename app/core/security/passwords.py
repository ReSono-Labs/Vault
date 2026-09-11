import hashlib
import hmac
import os


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    actual_salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), actual_salt, 600_000)
    return actual_salt.hex() + ":" + digest.hex()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, digest_hex = password_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return False
    computed = hash_password(password, salt=salt)
    return hmac.compare_digest(computed, password_hash)
