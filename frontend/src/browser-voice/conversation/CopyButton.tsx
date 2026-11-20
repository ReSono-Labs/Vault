import { useEffect, useRef, useState } from "react";

/** Copy text to the clipboard; falls back to a hidden textarea where the Clipboard API is blocked (plain http). */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* fall through to the textarea copy */ }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  try { return document.execCommand("copy"); } catch { return false; } finally { area.remove(); }
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<number | null>(null);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);
  async function copy() {
    const ok = await copyText(text);
    setState(ok ? "copied" : "failed");
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 1800);
  }
  return <button aria-label={state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : label}
    className={`vault-copy-button${state === "copied" ? " is-copied" : ""}`} onClick={() => void copy()} title={label} type="button">
    {state === "copied"
      ? <svg aria-hidden="true" fill="none" height="16" viewBox="0 0 24 24" width="16"><path d="m5 12 4.5 4.5L19 7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" /></svg>
      : <svg aria-hidden="true" fill="none" height="16" viewBox="0 0 24 24" width="16"><rect height="12" rx="2" stroke="currentColor" strokeWidth="1.7" width="11" x="9" y="9" /><path d="M5 15V6a2 2 0 0 1 2-2h8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /></svg>}
    <span className="vault-visually-hidden" role="status">{state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : ""}</span>
  </button>;
}
