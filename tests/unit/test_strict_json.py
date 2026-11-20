import pytest

from app.vault_runtime.tools.strict_json import StrictJSONError, parse_json_object_bytes


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b'{"x":1,"x":2}', "duplicate_key"),
        (b'{"x":NaN}', "non_finite"),
        (b'[]', "object_required"),
        (b'\xff', "syntax"),
    ],
)
def test_strict_json_rejects_unsafe_inputs(raw: bytes, reason: str) -> None:
    with pytest.raises(StrictJSONError) as caught:
        parse_json_object_bytes(raw)
    assert caught.value.reason == reason


def test_strict_json_rejects_depth_and_size() -> None:
    with pytest.raises(StrictJSONError, match="bounded") as depth:
        parse_json_object_bytes((b'{"x":' * 34) + b"0" + (b"}" * 34))
    assert depth.value.reason == "depth"
    with pytest.raises(StrictJSONError) as size:
        parse_json_object_bytes(b'{"x":"123"}', max_bytes=4)
    assert size.value.reason == "raw_size"
