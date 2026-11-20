/** Presentation only: never interprets a rule as permission to execute. */
export function ToolPreparation({ tool }: { tool: { description: string; kind: string } }) {
  if (tool.kind !== "learned_rule") return <>{tool.description}<small>Catalog proposal</small></>;
  let title = tool.description;
  let conditions: string[] = [], slots: string[] = [], exclusions: string[] = [];
  try {
    const value: unknown = JSON.parse(tool.description);
    if (value && typeof value === "object") {
      const rule = value as Record<string, unknown>;
      if (typeof rule.description === "string") title = rule.description;
      const strings = (items: unknown): string[] => Array.isArray(items) && items.every(item => typeof item === "string") ? items : [];
      const when = rule.conditions && typeof rule.conditions === "object" ? rule.conditions as Record<string, unknown> : {};
      conditions = strings(when.all);
      slots = strings(rule.required_slots);
      exclusions = strings(rule.exclusions);
    }
  } catch { /* Unknown future representation stays plain escaped text. */ }
  return <>{title}<small>Learned read-only rule</small>
    {conditions.length ? <small>When: {conditions.join("; ")}</small> : null}
    {slots.length ? <small>Needs: {slots.join(", ")}</small> : null}
    {exclusions.length ? <small>Excludes: {exclusions.join("; ")}</small> : null}
  </>;
}
