import "./BackgroundSettings.css";
import { useCallback, useEffect, useState } from "react";
import {
  backgroundApi,
  type BackgroundPreferences,
  type BackgroundRoutineItem,
  type BackgroundWorkerItem,
} from "@/browser-voice/background/api";
import { scheduleText, shortTitle, when } from "@/browser-voice/background/workText";

export function BackgroundSettings() {
  const [preferences, setPreferences] = useState<BackgroundPreferences | null>(null);
  const [workers, setWorkers] = useState<BackgroundWorkerItem[]>([]);
  const [routines, setRoutines] = useState<BackgroundRoutineItem[]>([]);
  const [quietStart, setQuietStart] = useState("22:00");
  const [quietEnd, setQuietEnd] = useState("07:00");
  const [quietTimezone, setQuietTimezone] = useState("UTC");
  const [error, setError] = useState<string | null>(null);
  const [openRoutineId, setOpenRoutineId] = useState<string | null>(null);
  const openRoutine = routines.find((routine) => routine.routineId === openRoutineId) ?? null;

  const refresh = useCallback(async () => {
    try {
      const [prefRes, workerRes, routineRes] = await Promise.all([
        backgroundApi.preferences(),
        backgroundApi.workers(),
        backgroundApi.routines(),
      ]);
      setPreferences(prefRes);
      setQuietStart(String(prefRes.quietHours?.start || "22:00"));
      setQuietEnd(String(prefRes.quietHours?.end || "07:00"));
      setQuietTimezone(String(prefRes.quietHours?.timezone || "UTC"));
      setWorkers(workerRes.items ?? []);
      setRoutines(routineRes.items ?? []);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Background settings could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function toggleOptIn() {
    if (!preferences) return;
    try {
      const updated = await backgroundApi.savePreferences({
        enabled: !preferences.enabled,
        quietHours: { start: quietStart, end: quietEnd, timezone: quietTimezone },
      });
      setPreferences(updated);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update background observation.");
    }
  }

  async function saveQuietHours() {
    try {
      const updated = await backgroundApi.savePreferences({
        enabled: Boolean(preferences?.enabled),
        quietHours: { start: quietStart, end: quietEnd, timezone: quietTimezone },
      });
      setPreferences(updated);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save quiet hours.");
    }
  }

  async function handleWorkerOp(
    worker: BackgroundWorkerItem,
    op: "pause" | "reset" | "delete",
  ) {
    try {
      const res = await backgroundApi.workerAction(worker.workerId, op, worker.generation);
      setWorkers((current) =>
        op === "delete"
          ? current.filter((w) => w.workerId !== worker.workerId)
          : current.map((w) =>
              w.workerId === worker.workerId
                ? { ...w, generation: res.generation, status: res.status }
                : w,
            ),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Specialist update failed.");
    }
  }

  async function handleRoutineOp(
    routine: BackgroundRoutineItem,
    op: "pause" | "cancel",
  ) {
    try {
      const res = await backgroundApi.routineAction(routine.routineId, op);
      setRoutines((current) =>
        op === "cancel"
          ? current.filter((r) => r.routineId !== routine.routineId)
          : current.map((r) =>
              r.routineId === routine.routineId ? { ...r, status: res.status } : r,
            ),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Routine update failed.");
    }
  }

  return (
    <section aria-label="Background Assistant Settings" className="browser-voice-background-settings">
      <div className="browser-voice-section-head">
        <div>
          <h3>Observation and quiet hours</h3>
          <p>
            {preferences?.standingScope ||
              "Allows read and preparation checks on committed Chat/Voice turns and connected mail/calendar. Specialist creation and external writes still require your approval."}
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-label="Automatic background observation"
          aria-checked={Boolean(preferences?.enabled)}
          className="browser-voice-agent-switch"
          onClick={() => void toggleOptIn()}
        >
          <span />
        </button>
      </div>

      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}

      <fieldset className="browser-voice-background-quiet-hours">
        <legend>Quiet hours</legend>
        <div className="browser-voice-background-time-fields">
          <label>
            <span>Start</span>
            <input
              aria-label="Quiet hours start"
              type="text"
              value={quietStart}
              onChange={(e) => setQuietStart(e.target.value)}
            />
          </label>
          <label>
            <span>End</span>
            <input
              aria-label="Quiet hours end"
              type="text"
              value={quietEnd}
              onChange={(e) => setQuietEnd(e.target.value)}
            />
          </label>
          <label>
            <span>Timezone</span>
            <input
              aria-label="Quiet hours timezone"
              type="text"
              value={quietTimezone}
              onChange={(e) => setQuietTimezone(e.target.value)}
            />
          </label>
        </div>
        <button
          type="button"
          className="browser-voice-submit"
          onClick={() => void saveQuietHours()}
        >
          Save quiet hours
        </button>
      </fieldset>

      <div className="browser-voice-section-head">
        <div>
          <h3>Specialist roles</h3>
          <p>Approved specialists with scoped tools and instructions.</p>
        </div>
      </div>
      {workers.length === 0 ? (
        <p className="browser-voice-background-empty">No specialist roles approved yet.</p>
      ) : (
        <div className="browser-voice-agent-list">
          {workers.map((worker) => (
            <article key={worker.workerId} className="browser-voice-agent-row">
              <div className="browser-voice-background-row-details">
                <strong>{worker.roleKey}</strong>
                <p>{worker.purpose}</p>
                <small>Tools: {worker.toolNames.join(", ") || "read-only"}</small>
                <small>Status: {worker.status}</small>
              </div>
              <div className="browser-voice-run-actions">
                <button
                  type="button"
                  aria-label={`Pause specialist ${worker.roleKey}`}
                  className="browser-voice-pill browser-voice-pill-muted"
                  onClick={() => void handleWorkerOp(worker, "pause")}
                >
                  Pause
                </button>
                <button
                  type="button"
                  aria-label={`Reset specialist ${worker.roleKey}`}
                  className="browser-voice-pill browser-voice-pill-muted"
                  onClick={() => void handleWorkerOp(worker, "reset")}
                >
                  Reset
                </button>
                <button
                  type="button"
                  aria-label={`Delete specialist ${worker.roleKey}`}
                  className="browser-voice-pill browser-voice-run-remove"
                  onClick={() => void handleWorkerOp(worker, "delete")}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="browser-voice-section-head">
        <div>
          <h3>Routines</h3>
          <p>Scheduled background checks and recurring briefs.</p>
        </div>
      </div>
      {routines.length === 0 ? (
        <p className="browser-voice-background-empty">No background routines configured.</p>
      ) : openRoutine ? (
        <RoutineDetail
          onBack={() => setOpenRoutineId(null)}
          onCancel={() => void handleRoutineOp(openRoutine, "cancel").then(() => setOpenRoutineId(null))}
          onPause={() => void handleRoutineOp(openRoutine, "pause")}
          routine={openRoutine}
        />
      ) : (
        <div className="vault-work-list">
          {routines.map((routine) => (
            <article key={routine.routineId} className="vault-work-row">
              <button aria-label={`Open routine ${shortTitle(routine.objective)}`} className="vault-work-open"
                onClick={() => setOpenRoutineId(routine.routineId)} type="button">
                <strong>{shortTitle(routine.objective)}</strong>
                <small>
                  <span className={`browser-voice-state is-${routine.status === "active" ? "ready" : "muted"}`}>{routineStatusText(routine.status)}</span>
                  <span>{scheduleText(routine.rule)}</span>
                  {routine.status === "active" && routine.nextDueAt ? <span>Next {when(routine.nextDueAt)}</span> : null}
                </small>
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function routineStatusText(status: string): string {
  return status === "active" ? "Active" : status === "paused" ? "Paused" : status.replaceAll("_", " ");
}

function RoutineDetail({ routine, onBack, onPause, onCancel }: {
  routine: BackgroundRoutineItem; onBack: () => void; onPause: () => void; onCancel: () => void;
}) {
  const facts: [string, string | null][] = [
    ["Status", routineStatusText(routine.status)],
    ["Schedule", scheduleText(routine.rule)],
    ["Time zone", routine.timezone],
    ["Next run", routine.status === "active" ? when(routine.nextDueAt) : null],
    ["Created", when(routine.createdAt)],
  ];
  return (
    <div className="vault-routine-detail">
      <button className="browser-voice-pill vault-back" onClick={onBack} type="button">← Routines</button>
      <p className="vault-work-text">{routine.objective}</p>
      <dl className="vault-work-facts">
        {facts.filter(([, value]) => value).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
      </dl>
      <div className="browser-voice-run-actions">
        {routine.status === "active" ? (
          <button type="button" aria-label={`Pause routine ${routine.objective}`}
            className="browser-voice-pill browser-voice-pill-muted" onClick={onPause}>Pause</button>
        ) : null}
        <button type="button" aria-label={`Cancel routine ${routine.objective}`}
          className="browser-voice-pill browser-voice-run-remove" onClick={onCancel}>Cancel routine</button>
      </div>
    </div>
  );
}
