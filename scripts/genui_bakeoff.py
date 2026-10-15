#!/usr/bin/env python3
"""GenUI bake-off: Decisions presentation hint vs no hint, on fixed prompts.

MAKES PAID PROVIDER CALLS (Decisions API + your conversation model). Run only with explicit
approval. It never touches a Vault database: it calls the providers directly with the same
catalog prompt, tool schema and hint logic Vault uses, and prints a JSON summary.

Usage:
  OPENAI_API_KEY=sk-... python3 scripts/genui_bakeoff.py --model gpt-5.6-sol [--runs 1] [--out result.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vault_runtime.genui import catalog, presentation  # noqa: E402

PROMPTS = (
    ("Plan my Saturday: cake pickup at 5, dinner at 7:30 for six people, then jazz at 9:30.", "timeline"),
    ("Suggest three Italian restaurants near downtown for a birthday dinner and let me pick.", "options"),
    ("Make a packing list for a three-day ski trip.", "checklist"),
    ("Compare the iPhone 17 and Pixel 11 on price, battery, camera and weight.", "comparison"),
    ("List my last five invoices with client, amount, due date and status: Acme $1200 Nov 2 paid, "
     "Birch $640 Nov 9 open, Cole $2100 Nov 12 open, Dune $300 Nov 15 overdue, Echo $980 Nov 20 open.", "table"),
    ("What are today's totals: 12 tasks, 3 overdue, 41 unread emails, 2 meetings?", "metrics"),
    ("My weight this week was 82.1, 81.8, 81.9, 81.5, 81.2, 81.4, 81.0 kg. Show the trend.", "chart"),
    ("Summarize the key points of a good onboarding email for a new employee.", "summary"),
    ("Hi! How are you today?", "text"),
    ("What's the capital of Portugal?", "text"),
    ("Why is the sky blue?", "text"),
    ("Thanks, that's perfect.", "text"),
    ("Give me a 5-step morning routine with times starting at 6:30.", "timeline"),
    ("Which of these two laptops should I buy for video editing: MacBook Pro 14 M5 or Dell XPS 16?", "comparison"),
    ("Show my monthly spending: Jan 1200, Feb 980, Mar 1430, Apr 1100, May 1600, Jun 1250.", "chart"),
    ("Pick a movie for tonight from three good sci-fi options.", "options"),
    ("Tell me a short joke.", "text"),
    ("What do I need to renew a US passport by mail?", "checklist"),
    ("Explain the difference between a Roth and a traditional IRA in two sentences.", "text"),
    ("Draft three subject lines for a product launch email and let me choose one.", "options"),
)

BASE_INSTRUCTIONS = ("You are Vault's assistant in a text chat. Answer the user's request. "
                     "Never invent personal data; use only what the user gave you.")


class _Transport:
    def __init__(self, key: str):
        import httpx
        self.client, self.key = httpx.Client(), key

    def evaluate(self, payload, *, timeout_seconds):
        response = self.client.post("https://api.openai.com/v1/decisions", json=payload, timeout=timeout_seconds,
                                    headers={"Authorization": "Bearer " + self.key})
        response.raise_for_status()
        return response.json()


async def _turn(model: str, prompt: str, hint: dict | None) -> dict:
    from agents import Agent, FunctionTool, ModelSettings, Runner
    cards, started, first_card = [], monotonic(), None

    async def present(context, raw):
        nonlocal first_card
        try:
            card = catalog.validate(json.loads(raw))
        except (catalog.SpecError, ValueError) as error:
            cards.append({"invalid": str(error)})
            return json.dumps({"shown": False, "error": str(error)})
        first_card = first_card or monotonic() - started
        cards.append(card)
        return json.dumps({"shown": True})

    if hint is None:
        section = catalog.prompt_section()
    elif hint["textLikely"]:
        section = catalog.prompt_section(text_likely=True)
    else:
        section = catalog.prompt_section(tuple(hint["layouts"]) or None)
    agent = Agent(name="Vault GenUI bake-off", model=model, instructions=BASE_INSTRUCTIONS + " " + section,
                  model_settings=ModelSettings(reasoning={"effort": "none"} if model.startswith("gpt-5") else None),
                  tools=[FunctionTool(name=catalog.TOOL_NAME, description=catalog.TOOL_DESCRIPTION,
                                      params_json_schema=catalog.INPUT_SCHEMA, on_invoke_tool=present,
                                      strict_json_schema=False)])
    result = await Runner.run(agent, prompt, max_turns=6)
    usage = result.context_wrapper.usage
    return {"seconds": round(monotonic() - started, 3), "firstCardSeconds": round(first_card, 3) if first_card else None,
            "inputTokens": usage.input_tokens, "outputTokens": usage.output_tokens,
            "layouts": [c.get("layout") for c in cards if "layout" in c],
            "invalidCards": sum("invalid" in c for c in cards), "promptChars": len(section)}


def _summary(rows: list[dict], arm: str) -> dict:
    picked = [r for r in rows if r["arm"] == arm]
    match = [((r["layouts"][0] if r["layouts"] else "text") == r["expected"]) for r in picked]
    return {"turns": len(picked), "layoutMatchRate": round(sum(match) / len(match), 3),
            "medianSeconds": statistics.median(r["seconds"] for r in picked),
            "medianFirstCardSeconds": statistics.median([r["firstCardSeconds"] for r in picked if r["firstCardSeconds"]] or [0]),
            "meanInputTokens": round(statistics.mean(r["inputTokens"] for r in picked)),
            "meanOutputTokens": round(statistics.mean(r["outputTokens"] for r in picked)),
            "invalidCards": sum(r["invalidCards"] for r in picked)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--out")
    args = parser.parse_args()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY is required (paid calls).", file=sys.stderr)
        return 2
    transport, rows = _Transport(key), []
    for _ in range(args.runs):
        for prompt, expected in PROMPTS:
            hint = presentation.predict(transport, prompt, timeout_seconds=3)
            for arm, used in (("baseline", None), ("hinted", hint)):
                row = asyncio.run(_turn(args.model, prompt, used))
                rows.append(dict(row, arm=arm, expected=expected, prompt=prompt,
                                 hint=hint if arm == "hinted" else None))
                print(json.dumps({"arm": arm, "expected": expected, "layouts": row["layouts"], "s": row["seconds"]}))
    hinted = [r["hint"] for r in rows if r["arm"] == "hinted"]
    result = {"model": args.model, "baseline": _summary(rows, "baseline"), "hinted": _summary(rows, "hinted"),
              "decisions": {"available": sum(h is not None for h in hinted), "total": len(hinted),
                            "medianMs": statistics.median([h["elapsedMs"] for h in hinted if h] or [0]),
                            "hintMatchRate": round(sum(bool(h) and ((h["layouts"] or ["text"])[0] == r["expected"])
                                for h, r in zip(hinted, [r for r in rows if r["arm"] == "hinted"])) / len(hinted), 3)},
              "rows": rows}
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
