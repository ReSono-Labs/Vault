import pytest

from app.vault_runtime.genui import catalog, presentation


def test_valid_cards_normalize_and_strip_control_text():
    card = catalog.validate({"layout": "timeline", "title": " Saturday\u202e ", "fallbackText": "Plan",
        "items": [{"time": "17:00", "title": "Cake", "state": "done"}, {"time": "19:30", "title": "Dinner"}],
        "columns": ["ignored"]})
    assert card == {"version": 1, "layout": "timeline", "fallbackText": "Plan", "title": "Saturday",
                    "items": [{"time": "17:00", "title": "Cake", "state": "done"}, {"time": "19:30", "title": "Dinner"}]}
    chart = catalog.validate({"layout": "chart", "fallbackText": "AAPL", "chartKind": "bar",
        "items": [{"label": "Mon", "amount": 1}, {"label": "Tue", "amount": 2.5}]})
    assert chart["chartKind"] == "bar" and chart["items"][1]["amount"] == 2.5
    grid = catalog.validate({"layout": "comparison", "fallbackText": "x", "columns": ["A", "B"],
        "rows": [["Price", "$1", "$2"]]})
    assert grid["rows"] == [["Price", "$1", "$2"]]
    checks = catalog.validate({"layout": "checklist", "fallbackText": "x", "items": [{"text": "Gift"}]})
    assert checks["items"] == [{"text": "Gift", "done": False}]


@pytest.mark.parametrize("spec", [
    None, [], {"layout": "html", "fallbackText": "x"},
    {"layout": "timeline", "fallbackText": "x", "script": "alert(1)"},
    {"layout": "timeline", "fallbackText": "   ", "items": [{"time": "1", "title": "a"}]},
    {"layout": "timeline", "fallbackText": "x", "items": [{"title": "missing time"}]},
    {"layout": "timeline", "fallbackText": "x", "items": [{"time": "1", "title": "a", "onClick": "x"}]},
    {"layout": "options", "fallbackText": "x", "items": [{"title": "only one"}]},
    {"layout": "chart", "fallbackText": "x", "items": [{"label": "a", "amount": "1"}, {"label": "b", "amount": 2}]},
    {"layout": "chart", "fallbackText": "x", "items": [{"label": "a", "amount": float("nan")}, {"label": "b", "amount": 2}]},
    {"layout": "table", "fallbackText": "x", "columns": ["a", "b"], "rows": [["only one"]]},
    {"layout": "comparison", "fallbackText": "x", "columns": ["a"], "rows": [["k", "v"]]},
    {"layout": "metrics", "fallbackText": "x", "items": [{"label": "a", "value": "1", "trend": "sideways"}]},
    {"layout": "summary", "fallbackText": "x", "title": "t" * 81, "items": [{"text": "a"}]},
])
def test_invalid_cards_are_rejected(spec):
    with pytest.raises(catalog.SpecError):
        catalog.validate(spec)


def test_prompt_sections_narrow_guidance_but_keep_every_layout_allowed():
    full = catalog.prompt_section()
    assert all(f"- {key}:" in full for key in catalog.LAYOUT_KEYS)
    narrowed = catalog.prompt_section(("timeline",))
    assert "- timeline:" in narrowed and "- options:" not in narrowed and "also available: options" in narrowed
    assert len(narrowed) < len(full)
    assert len(catalog.prompt_section(text_likely=True)) < len(narrowed)
    assert "simple" in catalog.prompt_section(simple=True)
    assert set(catalog.INPUT_SCHEMA["properties"]["layout"]["enum"]) == set(catalog.LAYOUT_KEYS)


class Transport:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.payloads = response, error, []

    def evaluate(self, payload, *, timeout_seconds):
        self.payloads.append((payload, timeout_seconds))
        if self.error:
            raise self.error
        return self.response


def answer(choice, visual, probabilities=()):
    return {"answers": [
        {"type": "choice", "name": "presentation", "choice": choice, "confidence": 0.8,
         "probabilities": [{"value": v, "probability": p} for v, p in probabilities]},
        {"type": "predicate", "name": "visual_helps", "probability": visual}]}


def test_presentation_payload_has_two_independent_questions():
    payload = presentation.build_payload("Plan Saturday", ("calendar_list_events",))
    assert payload["model"] == "gpt-6-luna"
    assert [q["name"] for q in payload["questions"]] == ["presentation", "visual_helps"]
    values = [c["value"] for c in payload["questions"][0]["choices"]]
    assert values == ["text", *catalog.LAYOUT_KEYS]


def test_presentation_decodes_layouts_and_text_likely():
    transport = Transport(answer("timeline", 0.9, [("timeline", .6), ("options", .3), ("table", .05), ("text", .05)]))
    hint = presentation.predict(transport, "Plan Saturday")
    assert hint["layouts"] == ["timeline", "options"] and hint["visualProbability"] == 0.9
    assert hint["textLikely"] is False and hint["elapsedMs"] >= 0
    text = presentation.predict(Transport(answer("text", 0.1, [("text", .9)])), "hi")
    assert text["layouts"] == [] and text["textLikely"] is True


@pytest.mark.parametrize("response", [
    None, {}, {"answers": []}, answer("html", 0.5), answer("timeline", 1.5),
    {"answers": [{"type": "refusal", "name": "presentation"}, answer("text", .1)["answers"][1]]},
])
def test_presentation_failures_are_no_hint(response):
    assert presentation.predict(Transport(response), "x") is None
    assert presentation.predict(Transport(error=TimeoutError()), "x") is None


def test_new_layouts_validate_and_links_are_https_only():
    news = catalog.validate({"layout": "headlines", "fallbackText": "News", "items": [
        {"title": "A", "source": "BBC", "time": "2h", "url": "https://bbc.com/a"}, {"title": "B"}]})
    assert news["items"][0]["url"] == "https://bbc.com/a" and "url" not in news["items"][1]
    for url in ("javascript:alert(1)", "http://x.com", "https://u@x.com/", "data:text/html,x"):
        with pytest.raises(catalog.SpecError):
            catalog.validate({"layout": "headlines", "fallbackText": "x", "items": [{"title": "A", "url": url}]})
    weather = catalog.validate({"layout": "weather", "title": "Toronto", "fallbackText": "15C cloudy",
        "items": [{"label": "Now", "value": "15°", "detail": "Cloudy", "condition": "cloud"}, {"label": "Fri", "value": "18°"}]})
    assert weather["items"][0]["condition"] == "cloud"
    with pytest.raises(catalog.SpecError):
        catalog.validate({"layout": "weather", "fallbackText": "x", "items": [{"label": "Now", "value": "1", "condition": "lava"}]})
    assert catalog.validate({"layout": "places", "fallbackText": "x",
        "items": [{"title": "Lucia's", "rating": "4.7", "distance": "0.8 mi", "status": "Open"}]})["items"][0]["status"] == "Open"
    assert len(catalog.validate({"layout": "steps", "fallbackText": "x", "items": [{"title": "a"}, {"title": "b"}]})["items"]) == 2
    with pytest.raises(catalog.SpecError):
        catalog.validate({"layout": "cards", "fallbackText": "x", "items": [{"title": "only one"}]})


def test_prompt_guidance_and_preferred_layout():
    text = catalog.prompt_section(("headlines",), guidance={"headlines": "Keep to five stories."}, preferred="headlines")
    assert "explicitly chosen the headlines layout" in text and "User preference: Keep to five stories." in text
