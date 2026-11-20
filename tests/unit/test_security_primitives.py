import hashlib

from app.core.security.passwords import hash_password, verify_password
from app.core.security.tokens import hash_token, token_equals


def test_password_hash_roundtrip_preserves_voice_contract() -> None:
    password_hash = hash_password("secret-password")
    assert verify_password("secret-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_password_hash_preserves_voice_deterministic_vector() -> None:
    salt = bytes.fromhex("00112233445566778899aabbccddeeff")
    password_hash = hash_password("secret-password", salt=salt)
    assert password_hash == (
        "00112233445566778899aabbccddeeff:"
        "40815e5b3039eef5e9dcc211a45de80c7d0ec40f0999201de151fb1264e38bb1"
    )


def test_malformed_password_hash_is_denied_without_crashing_login() -> None:
    assert verify_password("secret-password", "not-a-valid-hash") is False
    assert verify_password("secret-password", "zz:11") is False


def test_opaque_token_hash_is_voice_compatible() -> None:
    assert hash_token("local-session-token") == hashlib.sha256(b"local-session-token").hexdigest()


def test_bearer_secrets_compare_equal_only_when_identical() -> None:
    assert token_equals("inbound-secret", "inbound-secret") is True
    assert token_equals("inbound-secret", "outbound-secret") is False
    assert token_equals("short", "much-longer-token") is False
    assert token_equals("", "inbound-secret") is False
