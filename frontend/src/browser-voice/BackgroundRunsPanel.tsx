import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { localApi, type BackgroundRun } from "@/browser-voice/localApi";
import { BackgroundApprovals } from "@/browser-voice/background/BackgroundApprovals";
import { backgroundApi, type BackgroundWorkDetail, type BackgroundWorkItem } from "@/browser-voice/background/api";
import {
  ACTIVE_WORK_STATES, STOPPABLE_WORK_STATES, duration, shortTitle, stopReason, when, workStatusText, workStatusTone,
} from "@/browser-voice/background/workText";
import { PageHeader, PageSection } from "@/browser-voice/presentation/ManagementLayout";
import { whenVisible } from "@/browser-voice/polling";

const HISTORY_PAGE = 10;

/** The element that scrolls the page: the app frame on phones, the window on desktop. */
function scroller(): { get: () => number; set: (top: number) => void } {
  const frame = document.querySelector<HTMLElement>(".browser-voice-app-frame");
  if (frame && frame.scrollHeight > frame.clientHeight + 1) return { get: () => frame.scrollTop, set: top => { frame.scrollTop = top; } };
  return { get: () => window.scrollY, set: top => window.scrollTo(0, top) };
}

export function BackgroundRunsPanel({
  isDeviceOwner = false,
  onOpenTask,
}: {
  isDeviceOwner?: boolean;
  onOpenTask?: (taskId: string) => void;
} = {}) {
  const [items, setItems] = useState<BackgroundWorkItem[] | null>(null);
  const [legacy, setLegacy] = useState<BackgroundRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [historyShown, setHistoryShown] = useState(HISTORY_PAGE);
  const [stopping, setStopping] = useState<string[]>([]);
  const listTop = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await backgroundApi.workList();
      setItems(result.items);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Background work could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(whenVisible(() => void refresh()), 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    // Runs from before the coordinated background system, kept readable but out of the way.
    localApi.backgroundRuns().then(result => setLegacy(result.items)).catch(() => undefined);
  }, []);
  // Back returns to the same place in the list.
  useLayoutEffect(() => {
    if (openId === null && listTop.current !== null) { scroller().set(listTop.current); listTop.current = null; }
    if (openId !== null) scroller().set(0);
  }, [openId]);

  async function stop(workId: string) {
    setStopping(current => [...current, workId]);
    try { await backgroundApi.cancelWork(workId); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The run could not be stopped."); }
    finally { setStopping(current => current.filter(id => id !== workId)); }
  }
  function open(workId: string) { listTop.current = scroller().get(); setOpenId(workId); }

  const working = (items ?? []).some(item => item.state === "running");
  const status = <span className={`browser-voice-state ${working ? "is-ready" : ""}`}>{items === null ? "Loading" : working ? "Working" : "Idle"}</span>;
  if (openId) {
    const summary = (items ?? []).find(item => item.workId === openId) ?? null;
    return <WorkDetail initial={summary} onBack={() => setOpenId(null)} onOpenTask={onOpenTask}
      onStop={() => void stop(openId)} stopping={stopping.includes(openId)} workId={openId} />;
  }

  const active = (items ?? []).filter(item => ACTIVE_WORK_STATES.has(item.state));
  const history = (items ?? []).filter(item => !ACTIVE_WORK_STATES.has(item.state));
  const knownRuns = new Set((items ?? []).map(item => item.runId).filter(Boolean));
  const earlier = legacy.filter(run => !knownRuns.has(run.runId));

  return (
    <section className="browser-voice-agents vault-page vault-work-page" aria-labelledby="background-work-title">
      <PageHeader actions={status} description="Routines, specialists and tasks Vault runs for you. Open one to see what happened."
        title="Background work" titleId="background-work-title" />
      <BackgroundApprovals isDeviceOwner={isDeviceOwner} onDecided={() => void refresh()} />
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}

      <PageSection title="Active" titleId="background-work-active">
        {items === null ? <p className="browser-voice-management-empty" role="status">Loading…</p>
          : active.length ? <div className="vault-work-list">{active.map(item =>
            <WorkRow item={item} key={item.workId} onOpen={() => open(item.workId)}
              onStop={() => void stop(item.workId)} stopping={stopping.includes(item.workId)} />)}</div>
          : <p className="browser-voice-management-empty">Nothing running.</p>}
      </PageSection>

      <PageSection title="History" titleId="background-work-history">
        {history.length ? <>
          <div className="vault-work-list">{history.slice(0, historyShown).map(item =>
            <WorkRow item={item} key={item.workId} onOpen={() => open(item.workId)} />)}</div>
          {history.length > historyShown ? <button className="browser-voice-pill vault-work-more" onClick={() => setHistoryShown(count => count + HISTORY_PAGE)} type="button">
            Show more ({history.length - historyShown})</button> : null}
        </> : items === null ? null : <p className="browser-voice-management-empty">No finished work yet.</p>}
      </PageSection>

      {earlier.length ? <details className="vault-section vault-work-earlier">
        <summary>Earlier runs from this session ({earlier.length})</summary>
        <div className="vault-work-list">{earlier.map(run => <EarlierRun key={run.runId} onDeleted={() => setLegacy(list => list.filter(item => item.runId !== run.runId))} run={run} />)}</div>
      </details> : null}
    </section>
  );
}

function WorkRow({ item, onOpen, onStop, stopping = false }: {
  item: BackgroundWorkItem; onOpen: () => void; onStop?: () => void; stopping?: boolean;
}) {
  const time = ACTIVE_WORK_STATES.has(item.state)
    ? (item.state === "running" && item.activeSeconds != null ? `Running ${duration(item.activeSeconds)}` : when(item.createdAt))
    : when(item.completedAt || item.updatedAt);
  return <article className="vault-work-row">
    <button aria-label={`Open ${shortTitle(item.objective || "Background work")}`} className="vault-work-open" onClick={onOpen} type="button">
      <strong>{shortTitle(item.objective || "Background work")}</strong>
      <small>
        <span className={`browser-voice-state is-${workStatusTone(item.state)}`}>{workStatusText(item.state)}</span>
        {item.roleKey ? <span>{item.roleKey}</span> : null}
        {time ? <span>{time}</span> : null}
      </small>
    </button>
    {onStop && STOPPABLE_WORK_STATES.has(item.state)
      ? <button className="browser-voice-pill" disabled={stopping} onClick={onStop} type="button">{stopping ? "Stopping…" : "Stop"}</button>
      : null}
  </article>;
}

function WorkDetail({ workId, initial, onBack, onStop, stopping, onOpenTask }: {
  workId: string; initial: BackgroundWorkItem | null; onBack: () => void; onStop: () => void; stopping: boolean;
  onOpenTask?: (taskId: string) => void;
}) {
  const [detail, setDetail] = useState<BackgroundWorkDetail | null>(initial);
  const [error, setError] = useState<string | null>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { backRef.current?.focus(); }, []);
  useEffect(() => {
    let current = true;
    const load = () => backgroundApi.work(workId).then(value => { if (current) { setDetail(value); setError(null); } })
      .catch(caught => { if (current) setError(caught instanceof Error ? caught.message : "Details could not be loaded."); });
    void load();
    const timer = window.setInterval(whenVisible(() => { if (detail === null || ACTIVE_WORK_STATES.has(detail.state)) void load(); }), 3000);
    return () => { current = false; window.clearInterval(timer); };
  }, [workId, detail?.state]);

  const item = detail;
  const reason = item ? stopReason(item.state, item.failureCode) : null;
  const facts: [string, string | null][] = item ? [
    ["Specialist", item.roleKey],
    ["Started", when(item.startedAt || item.createdAt)],
    ["Finished", ACTIVE_WORK_STATES.has(item.state) ? null : when(item.completedAt || item.updatedAt)],
    ["Run time", duration(item.activeSeconds)],
    ["Steps", item.modelTurns != null || item.toolCalls != null ? `${item.modelTurns ?? 0} model turns · ${item.toolCalls ?? 0} tool calls` : null],
    ["From", item.routineId ? "A routine" : null],
  ] : [];
  return <section className="browser-voice-agents vault-page vault-work-detail" aria-labelledby="background-work-detail-title">
    <button className="browser-voice-pill vault-back" onClick={onBack} ref={backRef} type="button">← Background work</button>
    {item ? <>
      <header className="vault-work-detail-head">
        <span className={`browser-voice-state is-${workStatusTone(item.state)}`}>{workStatusText(item.state)}</span>
        <h2 id="background-work-detail-title">{shortTitle(item.objective || "Background work")}</h2>
      </header>
      {STOPPABLE_WORK_STATES.has(item.state)
        ? <button className="browser-voice-pill" disabled={stopping} onClick={onStop} type="button">{stopping ? "Stopping…" : "Stop run"}</button> : null}
      {reason ? <div className="browser-voice-run-error-detail vault-work-reason"><strong>Why it stopped</strong><p>{reason}</p></div> : null}
      <dl className="vault-work-facts">{facts.filter(([, value]) => value).map(([label, value]) =>
        <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {item.result?.summary ? <PageSection title="Result" titleId="background-work-result">
        <p className="vault-work-text">{item.result.summary}</p>
        {item.result.verification_summary ? <p className="vault-work-note">{item.result.verification_summary}</p> : null}
      </PageSection> : null}
      {item.task && onOpenTask ? <button className="browser-voice-pill" onClick={() => onOpenTask(item.task!.taskId)} type="button">Task: {item.task.text}</button> : null}
      <PageSection title="Instruction" titleId="background-work-instruction">
        <p className="vault-work-text">{item.brief?.objective || item.objective}</p>
        {item.brief?.contextSummary ? <p className="vault-work-note">{item.brief.contextSummary}</p> : null}
      </PageSection>
      {item.reasoningEntries?.length ? <PageSection title="Reasoning summaries" titleId="background-work-reasoning">
        {item.reasoningEntries.map((entry, index) => <div className="browser-voice-reasoning-entry" key={`${entry.createdAt}-${index}`}>
          <time dateTime={entry.createdAt}>{when(entry.createdAt)}</time>
          <p>{entry.type === "reasoning_summary" ? String(entry.detail.summary || "Reasoning summary unavailable.")
            : `${String(entry.detail.phase || "Agent evidence")}: ${String(entry.detail.summary || "Evidence recorded.")}`}</p>
        </div>)}
      </PageSection> : null}
      {item.failureCode ? <p className="vault-work-code">Code: {item.failureCode}</p> : null}
    </> : error ? null : <p role="status">Loading…</p>}
    {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
  </section>;
}

function EarlierRun({ run, onDeleted }: { run: BackgroundRun; onDeleted: () => void }) {
  const finished = !["accepted", "queued", "running", "reviewing", "repairing"].includes(run.state);
  return <article className="vault-work-row">
    <details className="vault-work-open">
      <summary><strong>{shortTitle(run.objective)}</strong>
        <small><span>{run.state.replaceAll("_", " ")}</span><span>{when(run.completedAt || run.createdAt)}</span>
          <span>{run.modelTurns} model turns · {run.toolCalls} tool calls</span></small></summary>
      <p className="vault-work-text">{run.objective}</p>
      {run.failure ? <p className="vault-work-note">{stopReason(run.state, run.failureCode) ?? run.failureExplanation}</p> : null}
      {(run.reasoningEntries ?? []).map((entry, index) => <p className="vault-work-note" key={index}>{String(entry.detail.summary || "")}</p>)}
    </details>
    {finished ? <button className="browser-voice-pill browser-voice-pill-muted" onClick={() => void localApi.deleteBackgroundRun(run.runId).then(onDeleted)} type="button">Delete</button> : null}
  </article>;
}
