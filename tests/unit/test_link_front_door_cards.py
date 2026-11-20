"""GenUI cards become Link Cards v1 in Front Door replies (ported from Link's legacy engine mapping)."""
from app.vault_runtime.link_companion.front_door import _output, link_card


def test_checklist_maps_like_link_legacy_engine():
    card = {"layout": "checklist", "fallbackText": "Trip: Friday 9:00",
            "items": [{"text": "Socks", "done": True}, {"text": "Hat"}]}
    assert link_card(card) == {"version": 1, "kind": "list", "title": "Checklist", "fallback_text": "Trip: Friday 9:00",
                               "fields": [{"label": "Done", "value": "Socks"}, {"label": "To do", "value": "Hat"}]}


def test_weather_headlines_and_summary():
    weather = link_card({"layout": "weather", "title": "Austin", "fallbackText": "Sunny 72F",
                         "items": [{"label": "Now", "value": "72F", "detail": "Sunny"}]})
    assert weather["kind"] == "status" and weather["fields"] == [{"label": "Now", "value": "72F \u00b7 Sunny"}]
    news = link_card({"layout": "headlines", "fallbackText": "News", "items": [
        {"title": "A", "url": "https://example.com/a"}, {"title": "B", "url": "http://insecure.example/b"}]})
    assert news["actions"] == [{"kind": "open_url", "url": "https://example.com/a"}]
    assert news["fields"][0]["label"] == "Headline"
    summary = link_card({"layout": "summary", "fallbackText": "Done", "body": "All tasks closed"})
    assert summary["subtitle"] == "All tasks closed" and "fields" not in summary


def test_unmappable_cards_fall_back_to_text_and_text_follows_cards():
    body = {"state": "completed", "messages": [
        {"cards": [{"id": "c1", "card": {"layout": "checklist", "fallbackText": "List", "items": [{"text": "x"}]}}]},
        {"cards": [{"id": "c2", "card": {"layout": "unknown", "fallbackText": "Plain fallback"}}]},
        {"text": "Here it is"}]}
    output = _output(body)
    assert output[0]["type"] == "link_cards" and len(output[0]["cards"]) == 1
    assert output[1]["content"][0]["text"] == "Plain fallback\n\nHere it is"
    assert link_card({"layout": "checklist", "items": [{"text": "x"}]}) is None, "no fallback text, no card"
