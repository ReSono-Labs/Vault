"""GenUI feedback routes, mounted inside the authenticated, CSRF-checked conversation API."""
from __future__ import annotations

import logging
from threading import Thread
from urllib.parse import parse_qs

from app.vault_runtime.conversation.contracts import InputError
from . import catalog, preferences, previews

logger = logging.getLogger(__name__)


def _store(runtime):
    return getattr(runtime, "genui_feedback", None) if getattr(runtime, "genui_enabled", False) else None


def handle_turn(runtime, principal, conversation_id, turn_id, action, *, method, payload, response, envelope):
    """``/conversations/{id}/turns/{turn}/{feedback|alternatives|choice}``; returns None when not matched."""
    if action not in ("feedback", "alternatives", "choice") or method != "POST":
        return None
    store = _store(runtime)
    if store is None:
        return response(503, {"error": {"code": "genui_unavailable"}})
    if action == "feedback":
        envelope(("verdict",))
        return response(200, store.record_verdict(principal, conversation_id, turn_id, payload["verdict"]))
    if action == "alternatives":
        envelope(())
        facts = store.turn_facts(principal, conversation_id, turn_id)
        cached = store.cached_previews(principal, turn_id)
        if cached is None:  # One paid generation per answer; later opens reuse it.
            cached = previews.generate(runtime, principal, facts)
            store.store_previews(principal, conversation_id, turn_id, cached)
        shown = [card.get("layout") for card in facts["cards"]]
        current = {"layout": shown[0] if shown else "text", "card": facts["cards"][0] if facts["cards"] else None,
                   "text": facts["answer"][:2000]}
        return response(200, {"current": current, "previews": cached})
    envelope(("layout",))
    result = store.record_choice(principal, conversation_id, turn_id, payload["layout"])

    def tune():
        try:
            preferences.tune(runtime, principal, store)
        except Exception:
            logger.warning("genui_tuner_failed")  # No private payload in logs.
    Thread(target=tune, name="vault-presentation-tuner", daemon=True).start()
    return response(200, result)


def handle_global(runtime, principal, parts, *, method, query, payload, response, envelope):
    """``/conversations/genui/...``; returns None when not matched."""
    if parts[:2] != ["conversations", "genui"]:
        return None
    store = _store(runtime)
    if store is None:
        return response(503, {"error": {"code": "genui_unavailable"}})
    rest = parts[2:]
    if rest == ["presentation"] and method == "GET":
        return response(200, store.config(principal))
    if rest in (["presentation", "keep"], ["presentation", "undo"]) and method == "POST":
        envelope(("version",))
        (store.keep if rest[1] == "keep" else store.undo)(principal, payload["version"])
        return response(200, store.config(principal))
    if rest == ["presentation", "reset"] and method == "POST":
        envelope(())
        return response(200, {"removedFeedback": store.reset(principal), **store.config(principal)})
    if rest == ["feedback", "export"] and method == "GET":
        values = parse_qs(query, keep_blank_values=True)
        if set(values) - {"includeText"} or values.get("includeText", ["0"])[0] not in ("0", "1"):
            raise InputError("Invalid export options.")
        return response(200, store.export(principal, include_text=values.get("includeText", ["0"])[0] == "1",
                                          catalog_version=catalog.CATALOG_VERSION))
    return response(404, {"error": {"code": "not_found"}})
