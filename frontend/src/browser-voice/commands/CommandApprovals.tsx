import { useCallback, useEffect, useState } from "react";
import { localApi, type PendingCommand } from "@/browser-voice/localApi";
import { whenVisible } from "@/browser-voice/polling";

/**
 * Commands the agent asked to run in this chat. Nothing runs until the person clicks Run;
 * the click is recorded on the server, so the agent can't approve its own command.
 */
export function CommandApprovals({
  conversationId,
  running,
  onDecided,
}: {
  conversationId: string | null;
  running: boolean;
  onDecided: (message: string) => void;
}) {
  const [items, setItems] = useState<PendingCommand[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!conversationId) {
      setItems([]);
      return;
    }
    localApi
      .pendingCommands(conversationId)
      .then((value) => setItems(value.items.filter((item) => item.state === "pending")))
      .catch(() => setItems([]));
  }, [conversationId]);

  useEffect(() => {
    refresh();
    if (!running) return;
    const timer = window.setInterval(whenVisible(refresh), 2000);
    return () => window.clearInterval(timer);
  }, [refresh, running]);

  async function decide(item: PendingCommand, approve: boolean) {
    setBusy(item.requestId);
    setError(null);
    try {
      await localApi.decideCommand(item.requestId, approve);
      setItems((current) => current.filter((value) => value.requestId !== item.requestId));
      onDecided(
        approve
          ? `I approved the command (request ${item.requestId}). Run it now with command_run_approved.`
          : `Don't run that command (request ${item.requestId}).`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That decision couldn't be saved.");
      refresh();
    } finally {
      setBusy(null);
    }
  }

  if (!items.length && !error) return null;
  return (
    <aside aria-label="Commands waiting for you" className="vault-command-approvals">
      {items.map((item) => (
        <div className="vault-command-approval" key={item.requestId} role="group" aria-label="Command waiting for approval">
          <strong>Run this command?</strong>
          <small>In {item.directory}</small>
          <pre><code>{item.command}</code></pre>
          <small>It can change files in that folder and use the internet. Nothing runs unless you click Run.</small>
          <div className="vault-command-approval-actions">
            <button
              className="browser-voice-pill browser-voice-pill-muted"
              disabled={busy !== null || running}
              onClick={() => void decide(item, false)}
              type="button"
            >
              Don't run
            </button>
            <button
              className="browser-voice-submit"
              disabled={busy !== null || running}
              onClick={() => void decide(item, true)}
              type="button"
            >
              {busy === item.requestId ? "Saving…" : "Run"}
            </button>
          </div>
        </div>
      ))}
      {error ? <p role="alert">{error}</p> : null}
    </aside>
  );
}
