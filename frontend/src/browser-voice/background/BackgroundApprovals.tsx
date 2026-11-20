import { useCallback, useEffect, useState } from "react";
import {
  backgroundApi,
  type BackgroundActionItem,
  type WebsiteOwnerApprovalItem,
} from "@/browser-voice/background/api";
import { whenVisible } from "@/browser-voice/polling";

type UnifiedApproval = {
  source: "background" | "website";
  actionId: string;
  actionHash: string;
  kind: string;
  scheduleKind?: string | null;
  title: string;
  detail: string;
  detailLines: string[];
  channels: ("browser" | "link")[];
};

function toUnified(
  bgItems: BackgroundActionItem[],
  webItems: WebsiteOwnerApprovalItem[],
): UnifiedApproval[] {
  const seen = new Set<string>();
  const unified: UnifiedApproval[] = [];

  for (const item of bgItems) {
    if (item.state && item.state !== "pending") continue;
    seen.add(item.actionId);
    unified.push({
      source: "background",
      actionId: item.actionId,
      actionHash: item.actionHash,
      kind: item.kind,
      scheduleKind: item.scheduleKind,
      title: item.title,
      detail: item.detail,
      detailLines: item.detailLines?.length ? item.detailLines : item.detail ? [item.detail] : [],
      channels: item.channels?.length ? item.channels : ["browser"],
    });
  }

  for (const w of webItems) {
    if (seen.has(w.id)) continue;
    seen.add(w.id);
    unified.push({
      source: "website",
      actionId: w.id,
      actionHash: w.actionHash || "",
      kind: w.kind,
      title: w.title,
      detail: w.detail,
      detailLines: w.detailLines?.length ? w.detailLines : Array.isArray(w.detail) ? w.detail : w.detail ? [w.detail] : [],
      channels: ["browser"],
    });
  }

  return unified;
}

export function BackgroundApprovals({
  onDecided,
  pollIntervalMs,
  conversationId,
  voiceSessionId,
  pollWhileHidden = false,
}: {
  isDeviceOwner?: boolean;
  onDecided?: (actionId: string, choice: "allow_once" | "deny") => void;
  pollIntervalMs?: number;
  conversationId?: string;
  voiceSessionId?: string;
  /** The Voice page keeps polling while hidden (owner decision 7-C); other pages pause. */
  pollWhileHidden?: boolean;
}) {
  const [items, setItems] = useState<UnifiedApproval[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [bgRes, webRes] = await Promise.allSettled([
      backgroundApi.actions(),
      backgroundApi.websiteApprovals(),
    ]);
    const bgItems = bgRes.status === "fulfilled" ? bgRes.value.items ?? [] : [];
    const webItems = webRes.status === "fulfilled" ? webRes.value.items ?? [] : [];
    const inSession = (item: { conversationId?: string | null; voiceSessionId?: string | null }) =>
      conversationId ? item.conversationId === conversationId :
        voiceSessionId ? item.voiceSessionId === voiceSessionId : true;
    setItems(toUnified(
      bgItems.filter(item => inSession(item) && item.kind !== "owner_approval"),
      webItems.filter(inSession),
    ));
  }, [conversationId, voiceSessionId]);

  useEffect(() => {
    void refresh();
    if (!pollIntervalMs || pollIntervalMs <= 0) return;
    const tick = () => void refresh();
    const timer = window.setInterval(pollWhileHidden ? tick : whenVisible(tick), pollIntervalMs);
    return () => window.clearInterval(timer);
  }, [refresh, pollIntervalMs, pollWhileHidden]);

  async function decide(item: UnifiedApproval, choice: "allow_once" | "deny") {
    setBusyId(item.actionId);
    setError(null);
    try {
      if (item.source === "background") {
        await backgroundApi.decideAction(item.actionId, item.actionHash, choice);
      } else {
        await backgroundApi.decideWebsiteApproval(item.actionId, choice, item.actionHash || undefined);
      }
      setItems((current) => current.filter((entry) => entry.actionId !== item.actionId));
      setSelectedId(null);
      onDecided?.(item.actionId, choice);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Approval decision could not be saved.");
    } finally {
      setBusyId(null);
    }
  }

  if (!items.length && !error) return null;

  const selected = items.length === 1 ? items[0] : items.find(item => item.actionId === selectedId);
  return (
    <section aria-label="Pending approvals" className="browser-voice-background-approvals">
      {items.length > 1 ? (
        <ul className="browser-voice-background-approval-details">
          {items.map(item => <li key={item.actionId}>
            <button type="button" className="browser-voice-pill" aria-expanded={selected?.actionId === item.actionId}
              onClick={() => setSelectedId(item.actionId)}>{item.title}</button>
          </li>)}
        </ul>
      ) : null}
      {selected ? (() => {
        const item = selected;
        return (
          <article
            key={item.actionId}
            className="browser-voice-background-approval-card"
            role="group"
            aria-label={item.title}
          >
            <header>
              <strong>{item.title}</strong>

            </header>
            {item.detailLines.length > 0 ? (
              <ul className="browser-voice-background-approval-details">
                {item.detailLines.map((line, index) => (
                  <li key={`${item.actionId}-line-${index}`}>{line}</li>
                ))}
              </ul>
            ) : item.detail ? (
              <p>{item.detail}</p>
            ) : null}
            {conversationId && item.kind === "routine_create" ? (
              <p>{item.scheduleKind === "once" ? "This runs once at the time shown." :
                "Approving creates the schedule. It then repeats at the times shown."}</p>
            ) : null}
            <div className="browser-voice-background-approval-actions">
              <button
                type="button"
                className="browser-voice-submit"
                disabled={busyId !== null}
                onClick={() => void decide(item, "allow_once")}
              >
                {conversationId && item.kind === "routine_create" ?
                  (item.scheduleKind === "once" ? "Approve one-time schedule" : "Approve recurring schedule") : "Allow once"}
              </button>
              <button
                type="button"
                className="browser-voice-pill browser-voice-pill-muted"
                disabled={busyId !== null}
                onClick={() => void decide(item, "deny")}
              >
                Deny
              </button>
            </div>
          </article>
        );
      })() : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
