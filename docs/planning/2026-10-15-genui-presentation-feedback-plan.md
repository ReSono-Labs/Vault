# Generative UI, presentation feedback and tuning — plan

Revision: GENUI-2026-10-15-r1. Branch `design/genui-overhaul`. Owner: Christian (decisions recorded 2026-10-15).

## Owner decisions

| ID | Decision |
|---|---|
| D-14 | The UI may be redesigned (supersedes D-02 "exact Browser Voice port" for new surfaces). Direction: `design/mockups/` (glass cards, aurora, one input bar). |
| D-15 | Answers may contain generative cards composed only from Vault's server-validated catalog (`genui/catalog.py`). Cards are display-only; a card interaction can only send a new user message. |
| D-16 | Vault collects presentation feedback: 👍/👎 per answer and an explicit "How can I do better?" choice among previews of the same answer in other layouts. |
| D-17 | An explicit carousel choice is the user's own stated presentation preference and may change layout selection directly. It is also passed to the existing decision reviewer as linked `user_feedback` evidence (fills `feedback_source_ids`). Thumbs alone are evidence, not a preference. |
| D-18 | When a request kind shows an overwhelming pattern, a bounded tuner may change presentation configuration only (weights, layout guidance lines, visual threshold). Changes are versioned, shown to the user in Chat with an example, and can be kept or undone. It never changes tools, grants, memory or code. |
| D-19 | Beta feedback leaves the device only by an explicit user export with a preview. Default export excludes request text; text is opt-in per export. No automatic or background transmission (D-01 holds). |

## Design

- **Catalog**: timeline, options, checklist, comparison, table, metrics, chart, summary, headlines, places, weather, steps, cards.
- **Feedback store** (`vault_genui_feedback`): per turn — predicted layouts (Decisions), shown layouts, verdict, chosen layout, request-kind label, local embedding, timestamps. Scoped to user+workspace; cascades with the turn.
- **Previews**: on request, one call to the user's configured chat model re-presents the answer's data in up to 5 alternative layouts; each preview is validated by the catalog; invalid ones are dropped.
- **Applying preferences**: at Send, nearest past explicit choices (pgvector over the local embedding) reweight the Decisions layout probabilities and are added as evidence. Strong agreement (≥3 neighbours, same choice) skips the prediction.
- **Tuner**: runs in the existing review pass (not a new agent). Trigger default: ≥5 events for a kind in 30 days with ≥70% preferring one other layout. Model output is a constrained edit list; Vault validates bounds and stores a new config version. A Chat notice offers Keep/Undo.
- **Export**: `GET /genui/feedback/export?preview=1` and a download; JSON with catalog version, model ids, layouts, verdicts, timings; `includeText=true` adds request text.

## Constraints honoured

No learning from unsent drafts (only finalized turns); prediction vs shown vs preferred stored separately; unknown stays unknown (no feedback = no signal); per user/workspace; removable module (`genui/`), flags `RESONO_VAULT_GENUI_ENABLED`, `RESONO_VAULT_GENUI_PRESENTATION_HINTS`; reset clears learned presentation state.

## Open

Numeric trigger defaults need beta evidence; the bake-off (`scripts/genui_bakeoff.py`) consumes exported feedback as labeled cases. Voice card delivery is a later step.
