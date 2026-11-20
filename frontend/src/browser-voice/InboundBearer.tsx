import { useEffect, useRef, useState } from "react";
import { localApi } from "@/browser-voice/localApi";

const SHOW_SECONDS = 60;

/**
 * This Vault's inbound Agent2Agent bearer, hidden by default. The token is only
 * requested from Vault when the user clicks Show or Copy, and is hidden again
 * after a minute or when the page closes.
 */
export function InboundBearer({ hint, onChanged }: { hint: string; onChanged?: (hint: string) => void }) {
  const [token, setToken] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const hideTimer = useRef<number | undefined>(undefined);
  const statusTimer = useRef<number | undefined>(undefined);
  useEffect(() => () => { window.clearTimeout(hideTimer.current); window.clearTimeout(statusTimer.current); }, []);
  // A different token (for example a new one) must never keep showing the old value.
  useEffect(() => { setToken(null); }, [hint]);

  function flash(message: string) {
    setStatus(message);
    window.clearTimeout(statusTimer.current);
    statusTimer.current = window.setTimeout(() => setStatus(""), 2500);
  }
  async function fetchToken() {
    setBusy(true);
    try { return (await localApi.a2aListenToken()).token; }
    catch (caught) { flash(caught instanceof Error ? caught.message : "The token could not be loaded."); return null; }
    finally { setBusy(false); }
  }
  function show(value: string) {
    setToken(value);
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setToken(null), SHOW_SECONDS * 1000);
  }
  async function toggle() {
    if (token) { window.clearTimeout(hideTimer.current); setToken(null); return; }
    const value = await fetchToken();
    if (value) show(value);
  }
  async function copy() {
    const value = token ?? await fetchToken();
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      flash("Copied");
    } catch {
      show(value); // Clipboard blocked: show it so it can be copied by hand.
      flash("Copy it from the box above.");
    }
  }
  async function makeNew() {
    if (!window.confirm("Make a new token? The current one stops working right away. "
      + "Any agent that uses it will need the new token.")) return;
    setBusy(true);
    try {
      const next = await localApi.a2aListenRotate();
      window.clearTimeout(hideTimer.current);
      setToken(null);
      onChanged?.(next.tokenHint);
      flash("New token made");
    } catch (caught) { flash(caught instanceof Error ? caught.message : "A new token could not be made."); }
    finally { setBusy(false); }
  }

  return <div className="browser-voice-inbound-bearer">
    <code aria-label={token ? "Inbound bearer" : "Inbound bearer, hidden"}>{token ?? `••••••••••••••••${hint}`}</code>
    <span className="browser-voice-inbound-bearer-actions">
      <button type="button" className="browser-voice-chip" disabled={busy} onClick={() => void toggle()}>{token ? "Hide" : "Show"}</button>
      <button type="button" className="browser-voice-chip" disabled={busy} onClick={() => void copy()}>Copy</button>
      <button type="button" className="browser-voice-chip" disabled={busy} onClick={() => void makeNew()}>Make new token</button>
      <small role="status">{status}</small>
    </span>
  </div>;
}
