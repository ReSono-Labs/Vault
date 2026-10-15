import "./conversation.css";
import type { Preparation } from "./api";
import { ToolPreparation } from "./ToolPreparation";

const STATE_LABELS: Record<string, string> = { searching: "searching", ready: "ready", settled: "ready",
  waiting: "listening", stale: "updating", unavailable: "unavailable", off: "off" };

const TOOL_LABELS: Record<string, string> = { waiting: "Waiting for words", choosing: "Choosing…",
  no_tool: "No tool needed", proposed: "Choosing…" };

export function LivePreparationPanel({ value }: { value: Preparation | null }) {
  return (value ? <aside className="vault-chat-preparation" aria-label="Live preparation">
        <strong>Live preparation · {STATE_LABELS[value.state] ?? value.state}</strong>
        <small>Provisional only. No tools have been executed.</small>
        <div>Memory: {value.memories.length ? <ul>{value.memories.map(memory =>
          <li key={memory.id}>{memory.text}<small>{memory.methods.join(", ")}</small></li>)}</ul> : "No current matches"}</div>
        <div>Tool route: {value.tools.length ? <ul>{value.tools.map(tool =>
          <li key={tool.id}><ToolPreparation tool={tool} /></li>)}</ul> : TOOL_LABELS[value.toolState ?? ""] ?? "Choosing…"}</div>
      </aside> : null);
}
