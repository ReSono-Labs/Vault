import { useEffect, useState } from "react";
import { localApi, type BackgroundRun } from "@/browser-voice/localApi";

type Tab = "logs" | "reasoning";

function elapsed(item: BackgroundRun) {
  const end = item.completedAt ? new Date(item.completedAt) : new Date();
  const seconds = Math.max(0, Math.floor((end.getTime() - new Date(item.createdAt).getTime()) / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function railColor(state: string) {
  if (state === "completed") return "#79eccb";
  if (state === "failed") return "#ff6b6b";
  return "#79edee";
}

export function BackgroundRunsPanel() {
  const [items, setItems] = useState<BackgroundRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("logs");
  const [status, setStatus] = useState("Loading");

  async function refresh() {
    try {
      const result = await localApi.backgroundRuns();
      setItems(result.items);
      setError(null);
      setStatus(result.items.some((item) => item.progress.active) ? "Working" : "Idle");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Background work could not be loaded.");
      setStatus("Unavailable");
    }
  }

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const reasoningItems = items.filter((item) => (item.reasoningEntries ?? []).length);

  return (
    <section className="browser-voice-management-section">
      <header className="browser-voice-management-heading">
        <div>
          <span className="browser-voice-eyebrow-label">Background Agent</span>
          <h2>Delegated work</h2>
          <p>Review work delegated by Voice. This page does not start runs.</p>
        </div>
        <span className={`browser-voice-state ${status === "Working" ? "is-ready" : ""}`}>{status}</span>
      </header>
      <div className="browser-voice-agent-filters" role="tablist" aria-label="Background Agent management">
        <button aria-pressed={tab === "logs"} className={tab === "logs" ? "is-active" : ""} onClick={() => setTab("logs")} type="button">Run logs</button>
        <button aria-pressed={tab === "reasoning"} className={tab === "reasoning" ? "is-active" : ""} onClick={() => setTab("reasoning")} type="button">Reasoning logs</button>
      </div>
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
      {tab === "logs" ? (
        <>
          <div className="browser-voice-section-head">
            <div>
              <span className="browser-voice-eyebrow-label">Run logs</span>
              <h3>Work by session</h3>
              <p>See outcomes, limits, failures, cancellation, and timestamps for each delegated run.</p>
            </div>
          </div>
          {items.length ? items.map((item) => (
            <article className="browser-voice-background-run-row" key={item.runId}>
              <i className="browser-voice-run-rail" style={{ ["--row-accent" as string]: railColor(item.state) }} />
              <div className="browser-voice-run-copy">
                <strong>{item.objective}</strong>
                <small>Session {item.originId} · {item.invocationType.replaceAll("_", " ")} · {new Date(item.createdAt).toLocaleString()}</small>
                <span className={`browser-voice-state ${item.state === "completed" ? "is-ready" : item.state === "failed" ? "is-error" : ""}`}>{item.state.replaceAll("_", " ")}</span>
                <div className={`browser-voice-run-progress ${item.progress.tone}${item.progress.active ? " is-active" : ""}`}>
                  <div className="browser-voice-run-progress-track" aria-hidden="true">
                    <i style={{ width: `${Math.round(Math.max(0, Math.min(1, item.progress.fraction)) * 100)}%` }} />
                  </div>
                  <strong>{item.progress.label}</strong>
                  <p className="browser-voice-run-activity">{item.progress.activity}</p>
                  <small className="browser-voice-run-metrics">{item.progress.modelTurns} model turns · {item.progress.toolCalls} tool calls · {elapsed(item)} elapsed</small>
                  <div className="browser-voice-run-timeline">
                    {(item.progress.timeline ?? []).map((event, index) => (
                      <div key={`${event.createdAt}-${index}`}>
                        <i />
                        <span>{event.label}</span>
                        <time>{new Date(event.createdAt).toLocaleTimeString()}</time>
                      </div>
                    ))}
                  </div>
                </div>
                {item.failure ? (
                  <div className="browser-voice-run-error-detail">
                    <strong>Why this run stopped: {item.failure.message || item.failure.code}</strong>
                    <p>{item.failureExplanation || "The runtime did not record a more specific explanation."}</p>
                  </div>
                ) : null}
              </div>
              <div className="browser-voice-run-actions">
                {["accepted", "queued", "running", "reviewing", "repairing"].includes(item.state) ? (
                  <button className="browser-voice-pill browser-voice-pill-muted" onClick={() => void localApi.cancelBackgroundRun(item.runId).then(refresh)} type="button">Cancel</button>
                ) : (
                  <button className="browser-voice-pill browser-voice-run-remove" onClick={() => void localApi.deleteBackgroundRun(item.runId).then(refresh)} type="button">Delete</button>
                )}
              </div>
            </article>
          )) : <p className="browser-voice-management-empty">No delegated work has run yet.</p>}
        </>
      ) : (
        <>
          <div className="browser-voice-section-head">
            <div>
              <span className="browser-voice-eyebrow-label">Reasoning logs</span>
              <h3>Reasoning summaries by session</h3>
              <p>Timestamped provider-returned summaries and phase evidence. Private chain-of-thought is never exposed.</p>
            </div>
          </div>
          {reasoningItems.length ? reasoningItems.map((item) => (
            <details className="browser-voice-reasoning-run" key={item.runId}>
              <summary>
                <strong>{item.objective}</strong>
                <small>{item.reasoningEntries.length} entries · {item.state.replaceAll("_", " ")} · {new Date(item.createdAt).toLocaleString()}</small>
              </summary>
              {item.reasoningEntries.map((event, index) => (
                <div className="browser-voice-reasoning-entry" key={`${event.createdAt}-${index}`}>
                  <time dateTime={event.createdAt}>{new Date(event.createdAt).toLocaleString()}</time>
                  <p>
                    {event.type === "reasoning_summary"
                      ? String(event.detail.summary || "Reasoning summary unavailable.")
                      : `${String(event.detail.phase || "Agent evidence")}: ${String(event.detail.summary || "Evidence recorded.")}`}
                  </p>
                </div>
              ))}
            </details>
          )) : <p className="browser-voice-management-empty">No provider reasoning summaries or explicit agent evidence have been recorded yet.</p>}
        </>
      )}
    </section>
  );
}
