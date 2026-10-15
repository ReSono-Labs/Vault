from dataclasses import replace

import pytest

from app.vault_runtime.memory.analysis_spans import partition_sources, validate_coverage, validate_reference


def test_full_long_session_and_oversized_entry_preserve_tail_and_global_citations():
    entries = [(f"entry-{i}", "user", "x"*17000 + f"fact-{i}") for i in range(270)]
    windows = partition_sources(entries)
    validate_coverage(entries, windows)
    assert len(windows) > 1
    assert all(len("\n".join(s.formatted for s in w)) <= 60000 for w in windows)
    spans = [s for w in windows for s in w]
    assert [s.index for s in spans] == list(range(len(spans)))
    for identity, _, text in entries:
        assert "".join(s.text for s in spans if s.source_id == identity) == text
    assert spans[-1].text.endswith("fact-269")


@pytest.mark.parametrize("change", ["missing", "text", "overlap", "fingerprint", "identity", "index"])
def test_bad_coverage_is_rejected(change):
    entries = [("source", "user", "abcdef")]
    spans = list(partition_sources(entries, span_characters=3)[0])
    if change == "missing":
        spans.pop()
    else:
        field, value = {"text":("text","xyz"), "overlap":("start",1),
            "fingerprint":("source_fingerprint","0"*64), "identity":("source_id","other"),
            "index":("index",99)}[change]
        spans[-1] = replace(spans[-1], **{field:value})
    with pytest.raises(ValueError):
        validate_coverage(entries, [spans])


def test_empty_sources_and_unicode_are_lossless_and_shape_is_strict():
    entries = [("a","user",""),("b","assistant","😊é\n你好")]
    windows = partition_sources(entries, span_characters=2)
    validate_coverage(entries, windows)
    ref = windows[0][-1].reference
    with pytest.raises(ValueError):
        validate_reference({**ref,"start":True}, windows[0][-1].text)
    with pytest.raises(ValueError):
        partition_sources(entries+entries)


def test_source_overhead_cannot_silently_overflow_input_budget():
    with pytest.raises(ValueError, match="window budget"):
        partition_sources([("source","user","abc")], window_characters=2)
