"""ERR-EVIDENCE (2026-11-22): window reviews failed whole on one imprecise excerpt or citation."""
from types import SimpleNamespace as NS

from app.vault_runtime.decision_learning.analysis_windows import anchor_excerpt, restrict_to_selected
from app.vault_runtime.decision_learning.reviewer import ReviewOutput, _validate_output
from tests.support.decision_learning_reviewer import output, snapshot

SPAN = NS(start=100, end=160, text="The owner said: \u201cuse the  Q3 numbers\u201d and then left.\nDone.")


def test_an_exact_excerpt_is_kept_as_is():
    assert anchor_excerpt(NS(start=116, end=137, text="\u201cuse the  Q3 numbers\u201d"), SPAN) == (
        116, 137, "\u201cuse the  Q3 numbers\u201d")


def test_wrong_offsets_or_quote_and_space_drift_re_anchor_to_the_original_text():
    assert anchor_excerpt(NS(start=3, end=9, text="use the  Q3 numbers"), SPAN) == (117, 136, "use the  Q3 numbers")
    # The kept text is the original slice (curly quotes, double space), never the model's copy.
    assert anchor_excerpt(NS(start=0, end=5, text='"use the Q3 numbers"'), SPAN) == (
        116, 137, "\u201cuse the  Q3 numbers\u201d")


def test_text_that_is_not_in_the_source_is_dropped():
    assert anchor_excerpt(NS(start=100, end=110, text="approve the payment"), SPAN) is None


def test_an_unselected_citation_is_removed_and_its_judgment_becomes_unknown():
    snap = snapshot()
    result = ReviewOutput.model_validate(output())
    view = [dict(source_id="final", reviewed_excerpts=[dict(start=0, end=5, text="Check")]),
            dict(source_id="result", reviewed_excerpts=[dict(start=0, end=4, text="Paid")]),
            dict(source_id="answer", reviewed_excerpts=[])]
    restricted = restrict_to_selected(result, view, snap)
    _validate_output(restricted, snap)  # Strict validation still passes.
    resolution = restricted.assessments[0].request_resolution
    assert "answer" not in resolution.evidence_source_ids and resolution.judgment == "unknown"
    assert restricted.assessments[0].tool_selection.judgment == "correct"
    # The proposal cited only selected sources, but its point no longer qualifies: it cannot teach.
    assert restricted.proposals[0].disposition == "insufficient_evidence"
