import { useEffect, useState } from "react";
import { conversationApi as api, type ToolRouting } from "./api";

/** Live tool routing: separate from Live Memory, and only usable with an OpenAI API key. */
export function ToolRoutingSwitch({ active }: { active: boolean }) {
  const [value, setValue] = useState<ToolRouting | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active || typeof api.toolRouting !== "function") return;
    const abort = new AbortController();
    api.toolRouting(abort.signal).then(next => { if (!abort.signal.aborted) setValue(next); })
      .catch(() => { if (!abort.signal.aborted) setError("Live Tool Routing setting unavailable"); });
    return () => abort.abort();
  }, [active]);

  async function toggle() {
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    try {
      setValue(await api.setToolRouting(!value.enabled));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Live Tool Routing could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  const on = Boolean(value?.enabled && value.available);
  return <>
    <button type="button" className="vault-chat-memory-toggle" role="switch" aria-label="Live Tool Routing"
      disabled={!value || busy || !value.available} aria-checked={on} onClick={() => void toggle()}
      title={value?.reason ?? undefined}>
      <span>Live Tool Routing<small>{!value ? "…" : !value.available ? "Unavailable" : value.enabled ? "On" : "Off"}</small></span>
      <span className="vault-chat-switch-track" aria-hidden="true"><span /></span></button>
    {value && !value.available ? <small>{value.reason}</small> : null}
    {error ? <small role="alert">{error}</small> : null}
  </>;
}
