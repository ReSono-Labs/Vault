import { useEffect, useRef, useState } from "react";
import { localApi, type VaultNotification } from "@/browser-voice/localApi";

function NotificationBellIcon() {
  return (
    <svg aria-hidden="true" className="browser-voice-header-icon" fill="none" viewBox="0 0 24 24">
      <path d="M6.5 17.5h11M9.2 17.5V9.4a2.8 2.8 0 1 1 5.6 0v8.1" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
      <path d="M5.5 9.6a6.5 6.5 0 0 1 13 0c0 2.4.8 4.6 2.1 6.4H3.4c1.3-1.8 2.1-4 2.1-6.4Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function formatNotificationTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<VaultNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [clearingAll, setClearingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const result = await localApi.notifications();
      setItems(result.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Notifications could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open) {
      return;
    }
    void refresh();
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Node) || !rootRef.current?.contains(target)) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  async function clearOne(notificationId: string) {
    setWorkingId(notificationId);
    setError(null);
    try {
      await localApi.clearNotification(notificationId);
      setItems((current) => current.filter((item) => item.notificationId !== notificationId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Notification could not be cleared.");
    } finally {
      setWorkingId(null);
    }
  }

  async function clearAll() {
    setClearingAll(true);
    setError(null);
    try {
      await localApi.clearAllNotifications();
      setItems([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Notifications could not be cleared.");
    } finally {
      setClearingAll(false);
    }
  }

  const badge = items.length > 99 ? "99+" : String(items.length);
  const summary = items.length
    ? `${items.length} ${items.length === 1 ? "notification" : "notifications"}`
    : "You're all caught up.";

  return (
    <div className="browser-voice-notifications-menu" ref={rootRef}>
      <button
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={open ? "Hide notifications" : "Show notifications"}
        className={`browser-voice-icon-button browser-voice-notification-button${open ? " is-active" : ""}`}
        onClick={() => setOpen((value) => !value)}
        title="Notifications"
        type="button"
      >
        <NotificationBellIcon />
        {items.length ? <em aria-hidden="true">{badge}</em> : null}
      </button>
      {open ? (
        <section aria-label="Notifications" className="browser-voice-notifications-drawer" role="dialog">
          <header className="browser-voice-notifications-drawer-head">
            <span className="browser-voice-eyebrow-label">Vault</span>
            <h2>Notifications</h2>
          </header>
          <div className="browser-voice-notifications-drawer-toolbar">
            <p>{summary}</p>
            <div className="browser-voice-notifications-drawer-actions">
              <button className="browser-voice-pill" disabled={loading} onClick={() => void refresh()} type="button">
                {loading ? "Refreshing..." : "Refresh"}
              </button>
              <button
                className="browser-voice-pill browser-voice-pill-muted"
                disabled={loading || clearingAll || items.length === 0}
                onClick={() => void clearAll()}
                type="button"
              >
                {clearingAll ? "Clearing..." : "Clear all"}
              </button>
            </div>
          </div>
          {error ? <p className="browser-voice-notifications-drawer-error" role="alert">{error}</p> : null}
          <div className="browser-voice-notifications-drawer-body">
            {items.length ? (
              <ul className="browser-voice-notifications-drawer-list">
                {items.map((item) => (
                  <li className="browser-voice-notifications-drawer-item" key={item.notificationId}>
                    <div>
                      <div className="browser-voice-notifications-drawer-meta">
                        <span>{item.kind}</span>
                        <span>{formatNotificationTime(item.createdAt)}</span>
                      </div>
                      <strong>{item.title}</strong>
                      {item.body ? <p>{item.body}</p> : null}
                    </div>
                    <button
                      className="browser-voice-pill browser-voice-pill-muted"
                      disabled={workingId === item.notificationId || clearingAll}
                      onClick={() => void clearOne(item.notificationId)}
                      type="button"
                    >
                      {workingId === item.notificationId ? "Clearing..." : "Clear"}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="browser-voice-notifications-drawer-empty">
                <strong>No notifications yet</strong>
                <p>Vault will show completed work and updates here.</p>
              </div>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}
