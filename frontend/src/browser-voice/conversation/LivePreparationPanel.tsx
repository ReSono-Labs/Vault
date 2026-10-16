import { useEffect, useState } from "react";
import { LIVE_PANEL_EVENT, livePanelShown, type LiveSurface } from "./livePanel";
import "./conversation.css";
import type { Preparation } from "./api";
import { ToolPreparation } from "./ToolPreparation";

const STATE_LABELS: Record<string, string> = { searching: "searching", ready: "ready", settled: "ready",
  waiting: "listening", stale: "updating", unavailable: "unavailable", off: "off" };

const TOOL_LABELS: Record<string, string> = { waiting: "Waiting for words", choosing: "Choosing…",
  no_tool: "No tool needed", proposed: "Choosing…" };

export function LivePreparationPanel({ value, surface = "chat" }: { value: Preparation | null; surface?: LiveSurface }) {
  const [shown, setShown] = useState(() => livePanelShown(surface));
  useEffect(() => {
    const sync = () => setShown(livePanelShown(surface));
    window.addEventListener(LIVE_PANEL_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener(LIVE_PANEL_EVENT, sync); window.removeEventListener("storage", sync); };
  }, [surface]);
  if (!value || !shown) return null;
  const state = STATE_LABELS[value.state] ?? value.state;
  return <aside className="vault-chat-preparation" aria-label="Live preparation">
        <strong>Live preparation · {state}</strong>
        <small>Provisional only. No tools have been executed.</small>
        <div>Memory: {value.memories.length ? <ul>{value.memories.map(memory =>
          <li key={memory.id}>{memory.text}<small>{memory.methods.join(", ")}</small></li>)}</ul> : "No current matches"}</div>
        <div>Tool route: {value.tools.length ? <ul>{value.tools.map(tool =>
          <li key={tool.id}><ToolPreparation tool={tool} /></li>)}</ul> : TOOL_LABELS[value.toolState ?? ""] ?? "Choosing…"}</div>
      </aside>;
}
