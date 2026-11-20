/** Mirrors genui/catalog.py LAYOUT_KEYS. Unknown layouts are never rendered. */
export const CARD_LAYOUTS = ["timeline", "options", "checklist", "comparison", "table", "metrics", "chart", "summary",
  "headlines", "places", "weather", "steps", "cards"] as const;
export type CardLayout = typeof CARD_LAYOUTS[number];
export const LAYOUT_LABELS: Record<CardLayout, string> = {
  timeline: "Timeline", options: "Options", checklist: "Checklist", comparison: "Comparison", table: "Table",
  metrics: "Numbers", chart: "Chart", summary: "Summary", headlines: "Headlines", places: "Places",
  weather: "Weather", steps: "Steps", cards: "Cards",
};
