"""Vault's own component catalog: what the model may compose, and the server-side gate.

The model never emits markup or code. It calls ``present_ui`` with one card description
built only from these layouts. Every description is validated and normalized here before
it is stored or streamed. Rendering, styling and any interaction belong to the frontend's
registered components, and an interaction can only send a new user message.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CATALOG_VERSION = 1
TOOL_NAME = "present_ui"
MAX_CARDS_PER_TURN = 6

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]")


@dataclass(frozen=True, slots=True)
class Layout:
    key: str
    use_when: str
    fields: str


LAYOUTS: tuple[Layout, ...] = (
    Layout("timeline", "events or steps in time order: a day plan, an itinerary, a schedule, progress steps.",
           "items[{time, title, detail?, state? done|needs_you|optional|pending}] 1-12"),
    Layout("options", "the user should pick one of several alternatives: places, products, plans.",
           "items[{title, detail?}] 2-6; a tap sends the chosen title back as the user's reply"),
    Layout("checklist", "a to-do list, packing list or requirements to tick off.",
           "items[{text, done?}] 1-12"),
    Layout("comparison", "two to four things compared on the same attributes.",
           "columns = the things compared (2-4); rows[[attribute, value per column...]] 1-12"),
    Layout("table", "structured records: several rows sharing the same columns.",
           "columns 1-6; rows[[cell per column]] 1-20"),
    Layout("metrics", "a few headline numbers: prices, totals, scores, counts.",
           "items[{label, value, detail?, trend? up|down|flat}] 1-6"),
    Layout("chart", "a numeric series where the shape matters: trend over time, or amounts by category.",
           "chartKind line|bar; items[{label, amount}] 2-24"),
    Layout("summary", "a short structured brief: key points with an optional lead sentence.",
           "body?; items[{text}] 1-8"),
)
LAYOUT_KEYS = tuple(layout.key for layout in LAYOUTS)
_LAYOUTS = {layout.key: layout for layout in LAYOUTS}

_STATES = ("done", "needs_you", "optional", "pending")
_TRENDS = ("up", "down", "flat")

_ITEM_PROPERTIES = {
    "title": {"type": "string", "maxLength": 80},
    "detail": {"type": "string", "maxLength": 160},
    "time": {"type": "string", "maxLength": 16},
    "state": {"type": "string", "enum": list(_STATES)},
    "text": {"type": "string", "maxLength": 160},
    "done": {"type": "boolean"},
    "label": {"type": "string", "maxLength": 48},
    "value": {"type": "string", "maxLength": 32},
    "trend": {"type": "string", "enum": list(_TRENDS)},
    "amount": {"type": "number"},
}

INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "layout": {"type": "string", "enum": list(LAYOUT_KEYS)},
        "title": {"type": "string", "maxLength": 80},
        "fallbackText": {"type": "string", "minLength": 1, "maxLength": 600,
                         "description": "Plain-text equivalent of the card, used for accessibility and history."},
        "body": {"type": "string", "maxLength": 400},
        "items": {"type": "array", "maxItems": 24,
                  "items": {"type": "object", "properties": _ITEM_PROPERTIES, "additionalProperties": False}},
        "columns": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 48}},
        "rows": {"type": "array", "maxItems": 20,
                 "items": {"type": "array", "maxItems": 7, "items": {"type": "string", "maxLength": 80}}},
        "chartKind": {"type": "string", "enum": ["line", "bar"]},
    },
    "required": ["layout", "fallbackText"],
    "additionalProperties": False,
}

TOOL_DESCRIPTION = (
    "Show one visual card in the conversation, built from Vault's fixed layouts. "
    "Call it only when a layout is clearly easier to read than prose; call it again for another card. "
    "It displays data only and performs no action."
)


class SpecError(ValueError):
    """The card description does not satisfy the catalog. Message is safe to return to the model."""


def prompt_section(layouts: tuple[str, ...] | None = None, *, simple: bool = False,
                   text_likely: bool = False) -> str:
    """Instructions for the conversation model.

    ``layouts`` narrows the detailed guidance to predicted layouts (other keys stay listed and
    allowed); ``text_likely`` means the predictor expects a plain-text answer, so only a one-line
    reminder is sent. Both are hints: the tool schema always accepts every layout.
    """
    if simple:
        return ("Visual cards: the user prefers simple answers. Answer in text; call present_ui only "
                "if the user explicitly asks for a table, chart or visual.")
    if text_likely:
        return ("Visual cards: this request most likely needs a plain-text answer. Only if a card is clearly "
                "better, call present_ui with one of: " + ", ".join(LAYOUT_KEYS) + ". Never invent data.")
    chosen = [_LAYOUTS[key] for key in (layouts or LAYOUT_KEYS) if key in _LAYOUTS]
    lines = "\n".join(f"- {layout.key}: use for {layout.use_when} Fields: {layout.fields}." for layout in chosen)
    others = [key for key in LAYOUT_KEYS if layouts and key not in layouts]
    if others:
        lines += "\n- also available: " + ", ".join(others) + "."
    lead = ("Visual cards: you may call present_ui to show a card next to your reply. Choose by what the "
            "user needs to understand or decide. Plain text is right for short answers, explanations, opinions "
            "and anything conversational; do not add a card that only repeats one sentence. ")
    if layouts:
        lead += ("The likely layout for this request was predicted below; prefer it when it fits, otherwise use "
                 "text or any other present_ui layout. ")
    return (lead + "Keep your text short when a card carries the detail; never repeat the card in prose. "
            "Only show facts from the conversation, tool results or memory; never invent data. "
            "Cards display information only: never describe a card button as booking, sending or confirming "
            "anything. Real actions still use their own tools and confirmations.\nLayouts:\n" + lines)


def _text(value, field: str, *, limit: int, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise SpecError(f"{field} is required.")
        return None
    if type(value) is not str:
        raise SpecError(f"{field} must be text.")
    value = " ".join(_CONTROL.sub("", value).split())
    if not value:
        if required:
            raise SpecError(f"{field} is required.")
        return None
    if len(value) > limit:
        raise SpecError(f"{field} exceeds {limit} characters.")
    return value


def _items(spec, low: int, high: int, allowed: dict[str, tuple[bool, int | None]]) -> list[dict]:
    items = spec.get("items")
    if type(items) is not list or not low <= len(items) <= high:
        raise SpecError(f"{spec['layout']} needs {low}-{high} items.")
    result = []
    for index, item in enumerate(items):
        if type(item) is not dict:
            raise SpecError(f"items[{index}] must be an object.")
        unknown = set(item) - set(_ITEM_PROPERTIES)
        if unknown:
            raise SpecError(f"items[{index}] has unsupported fields.")
        clean = {}
        for name, (required, limit) in allowed.items():
            value = item.get(name)
            label = f"items[{index}].{name}"
            if name == "done":
                if value is not None and type(value) is not bool:
                    raise SpecError(f"{label} must be true or false.")
                clean[name] = bool(value)
            elif name == "amount":
                if type(value) not in (int, float) or value != value or abs(value) > 1e15:
                    raise SpecError(f"{label} must be a finite number.")
                clean[name] = value
            elif name in ("state", "trend"):
                choices = _STATES if name == "state" else _TRENDS
                if value is not None and value not in choices:
                    raise SpecError(f"{label} is not a supported value.")
                if value is not None:
                    clean[name] = value
            else:
                text = _text(value, label, limit=limit, required=required)
                if text is not None:
                    clean[name] = text
        result.append(clean)
    return result


def _grid(spec, *, low: int, high: int, extra: int, max_rows: int) -> tuple[list[str], list[list[str]]]:
    columns = spec.get("columns")
    if type(columns) is not list or not low <= len(columns) <= high:
        raise SpecError(f"{spec['layout']} needs {low}-{high} columns.")
    columns = [_text(c, f"columns[{i}]", limit=48, required=True) for i, c in enumerate(columns)]
    rows = spec.get("rows")
    if type(rows) is not list or not 1 <= len(rows) <= max_rows:
        raise SpecError(f"{spec['layout']} needs 1-{max_rows} rows.")
    width = len(columns) + extra
    clean = []
    for r, row in enumerate(rows):
        if type(row) is not list or len(row) != width:
            raise SpecError(f"rows[{r}] needs exactly {width} cells.")
        clean.append([_text(cell, f"rows[{r}][{c}]", limit=80) or "" for c, cell in enumerate(row)])
    return columns, clean


def validate(spec: object) -> dict:
    """Return a normalized catalog card or raise SpecError. Never trusts provider-side schema checks."""
    if type(spec) is not dict:
        raise SpecError("Card description must be an object.")
    unknown = set(spec) - set(INPUT_SCHEMA["properties"])
    if unknown:
        raise SpecError("Card description has unsupported fields.")
    layout = spec.get("layout")
    if layout not in _LAYOUTS:
        raise SpecError("layout must be one of: " + ", ".join(LAYOUT_KEYS) + ".")
    card = {"version": CATALOG_VERSION, "layout": layout,
            "fallbackText": _text(spec.get("fallbackText"), "fallbackText", limit=600, required=True)}
    title = _text(spec.get("title"), "title", limit=80)
    if title:
        card["title"] = title
    if layout == "timeline":
        card["items"] = _items(spec, 1, 12, {"time": (True, 16), "title": (True, 80), "detail": (False, 160),
                                             "state": (False, None)})
    elif layout == "options":
        card["items"] = _items(spec, 2, 6, {"title": (True, 80), "detail": (False, 160)})
    elif layout == "checklist":
        card["items"] = _items(spec, 1, 12, {"text": (True, 160), "done": (False, None)})
    elif layout == "metrics":
        card["items"] = _items(spec, 1, 6, {"label": (True, 48), "value": (True, 32), "detail": (False, 160),
                                            "trend": (False, None)})
    elif layout == "chart":
        kind = spec.get("chartKind", "line")
        if kind not in ("line", "bar"):
            raise SpecError("chartKind must be line or bar.")
        card["chartKind"] = kind
        card["items"] = _items(spec, 2, 24, {"label": (True, 48), "amount": (True, None)})
    elif layout == "summary":
        body = _text(spec.get("body"), "body", limit=400)
        if body:
            card["body"] = body
        card["items"] = _items(spec, 1, 8, {"text": (True, 160)})
    elif layout == "table":
        card["columns"], card["rows"] = _grid(spec, low=1, high=6, extra=0, max_rows=20)
    elif layout == "comparison":
        card["columns"], card["rows"] = _grid(spec, low=2, high=4, extra=1, max_rows=12)
    return card
