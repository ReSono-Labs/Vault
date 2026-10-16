import pytest

from app.vault_runtime.genui import preferences as p
from app.vault_runtime.genui.feedback import cosine


def n(layout, request="news"):
    return {"layout": layout, "request": request, "similarity": 0.9, "at": "x"}


def test_strong_agreeing_neighbours_skip_decisions():
    assert p.strong_preference([n("headlines")] * 3) == "headlines"
    assert p.strong_preference([n("headlines")] * 2) is None
    assert p.strong_preference([n("headlines"), n("headlines"), n("table")]) is None
    hint = p.apply(None, {}, [n("headlines")] * 3)
    assert hint["layouts"] == ["headlines"] and hint["source"] == "preference" and hint["preferred"] == "headlines"
    text = p.apply(None, {}, [n("text")] * 4)
    assert text["textLikely"] is True and text["layouts"] == []


def test_reweighting_lets_weights_and_votes_beat_raw_decisions():
    hint = {"layouts": [], "visualProbability": 0.2, "textLikely": True,
            "probabilities": {"text": 0.6, "summary": 0.25, "headlines": 0.15}}
    assert p.apply(dict(hint), {}, [])["textLikely"] is True
    tuned = p.apply(dict(hint), {"weights": {"headlines": 2.0}, "visualThreshold": 0.3}, [n("headlines"), n("table")])
    assert tuned["layouts"][0] == "headlines" and tuned["source"] == "decisions+preferences"
    assert p.apply(None, {"weights": {"table": 2}}, []) is None


def test_pattern_requires_volume_share_and_a_real_change():
    vec = [1.0, 0.0]
    events = [{"layout": "headlines", "shown": ["summary"], "embedding": vec, "request": "news", "previews":
               [{"layout": "headlines", "card": {"layout": "headlines"}}]} for _ in range(4)]
    assert p.pattern(events, vec) is None
    split = events[:3] + [dict(events[0], layout="table")] * 2
    assert p.pattern(split, vec) is None  # 3/5 = 60% < 70%
    events.append(dict(events[0], layout="table"))
    found = p.pattern(events, vec)  # 4/5 = 80%
    assert found["layout"] == "headlines" and found["replaced"] == "summary" and found["previewCard"]
    same = [dict(e, shown=["headlines"]) for e in events if e["layout"] == "headlines"]
    assert p.pattern(same, vec) is None
    far = [dict(e, embedding=[0.0, 1.0]) for e in events]
    assert p.pattern(far, vec) is None and round(cosine(vec, vec), 3) == 1.0


def test_edits_are_bounded_and_unknown_edits_rejected():
    base = {"weights": {}, "guidance": {}, "visualThreshold": 0.5}
    out = p.validate_edits(base, {"weights": {"headlines": 9}, "visualThreshold": 0.0,
                                  "guidance": {"headlines": "  Keep to   five stories. "}})
    assert out["weights"]["headlines"] == 2.0 and out["visualThreshold"] == 0.3
    assert out["guidance"]["headlines"] == "Keep to five stories." and base["weights"] == {}
    for bad in ({"tools": {}}, {"weights": {"shell": 1}}, {"guidance": {"table": "x" * 200}}, {"visualThreshold": "low"}):
        with pytest.raises(ValueError):
            p.validate_edits(base, bad)
    assert p.fallback_edits(base, {"layout": "headlines", "replaced": "text"}) == {
        "weights": {"headlines": 1.25}, "visualThreshold": 0.45}
