/** Plain-language labels for background work, runs and routines. */

export const ACTIVE_WORK_STATES = new Set(["proposed", "ready", "queued", "running", "waiting_approval", "waiting_input", "waiting_event"]);
export const STOPPABLE_WORK_STATES = new Set(["proposed", "ready", "queued", "running", "waiting_approval", "waiting_input"]);

/** The first sentence of an instruction, for a short row title. */
export function shortTitle(text: string, max = 140): string {
  const value = text.trim().replace(/\s+/g, " ");
  // A sentence ends at . ! ? followed by a capitalised word, so "U.S. market" stays whole.
  const sentence = /^(.+?[.!?])(?=\s+["“(]?[A-Z]|$)/.exec(value)?.[1] ?? value;
  return sentence.length > max ? `${sentence.slice(0, max - 1).trimEnd()}…` : sentence;
}

export function workStatusText(state: string): string {
  switch (state) {
    case "proposed": case "ready": case "queued": return "Waiting to start";
    case "running": return "Working";
    case "waiting_approval": return "Waiting for your approval";
    case "waiting_input": case "waiting_event": return "Waiting";
    case "completed": return "Done";
    case "failed": return "Failed";
    case "cancelled": return "Stopped";
    default: return "Outcome not confirmed";
  }
}

export function workStatusTone(state: string): "ready" | "error" | "active" | "muted" {
  if (state === "completed") return "ready";
  if (state === "failed") return "error";
  if (ACTIVE_WORK_STATES.has(state)) return "active";
  return "muted";
}

const REASONS: Record<string, string> = {
  stalled_outcome_unknown: "Vault lost track of this run before it finished, so it can't confirm what happened.",
  execution_outcome_unknown: "The run hit an unexpected error part way through, so Vault can't confirm what happened.",
  execution_interrupted: "Vault restarted while this run was working.",
  effect_outcome_unknown: "It was in the middle of a change when it stopped, so Vault can't confirm the change.",
  cancelled_during_effect: "It was stopped in the middle of a change, so Vault can't confirm the change.",
  validationerror: "The agent's final answer wasn't in the format Vault expects.",
  badrequesterror: "The AI provider rejected the request.",
  agent_incomplete: "The agent reported that it couldn't finish.",
  budget_exhausted: "It used up its time or step limit.",
  run_timeout: "It ran out of time.",
  max_model_turns_exceeded: "It reached its step limit.",
  max_model_turns_exceeded_error: "It reached its step limit.",
  tool_budget_exceeded: "It reached its tool-call limit.",
  not_granted: "It needed something it isn't allowed to use.",
  tool_not_granted: "It needed a tool it isn't allowed to use.",
  approval_denied: "You declined its request.",
  approval_expired: "Its approval request expired.",
  approval_service_unavailable: "Approvals were unavailable, so it couldn't ask you.",
  cancelled: "You stopped it.",
  user_cancelled: "You stopped it.",
  invalid_checkpoint: "Its saved progress couldn't be resumed.",
};

/** Why a run ended, in plain words, or null when it simply finished. */
export function stopReason(state: string, failureCode: string | null | undefined): string | null {
  const code = String(failureCode || "").trim().toLowerCase();
  if (state === "completed" && !code) return null;
  if (code && REASONS[code]) return REASONS[code];
  if (state === "cancelled") return REASONS.cancelled;
  if (state === "unknown") return REASONS.stalled_outcome_unknown;
  if (code) return `It stopped with an error (${code}).`;
  return state === "failed" ? "It failed without recording a reason." : null;
}

export function duration(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds)) return null;
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  return minutes < 60 ? `${minutes}m ${total % 60}s` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function when(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return sameDay ? `Today ${time}` : `${date.toLocaleDateString([], { month: "short", day: "numeric" })}, ${time}`;
}

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function clock(hour: number, minute: number): string {
  const suffix = hour < 12 ? "AM" : "PM";
  const h = hour % 12 === 0 ? 12 : hour % 12;
  return `${h}:${String(minute).padStart(2, "0")} ${suffix}`;
}

function days(field: string): string | null {
  if (field === "*") return null;
  if (field === "1-5") return "Weekdays";
  if (field === "0,6" || field === "6,0") return "Weekends";
  const names: string[] = [];
  for (const part of field.split(",")) {
    const range = /^(\d)-(\d)$/.exec(part);
    if (range) { names.push(`${DAYS[+range[1] % 7].slice(0, 3)}–${DAYS[+range[2] % 7].slice(0, 3)}`); continue; }
    if (!/^\d$/.test(part)) return field;
    names.push(DAYS[+part % 7].slice(0, 3));
  }
  return names.length === 1 ? `${DAYS[DAYS.findIndex(day => day.startsWith(names[0]))]}s` : names.join(", ");
}

/** "Every day at 8:00 AM", "Weekdays at 12:30 PM", "Once, Nov 19, 8:00 PM", or the raw rule. */
export function scheduleText(rule: Record<string, unknown>): string {
  if (rule.kind === "once") {
    const at = when(String(rule.run_at || rule.scheduled_for || ""));
    return at ? `Once, ${at}` : "Once";
  }
  const cron = String(rule.cron || "").trim();
  const fields = cron.split(/\s+/);
  if (fields.length === 5 && /^\d+$/.test(fields[0]) && /^\d+$/.test(fields[1]) && fields[2] === "*" && fields[3] === "*") {
    const at = clock(+fields[1], +fields[0]);
    const on = days(fields[4]);
    return on ? `${on} at ${at}` : `Every day at ${at}`;
  }
  return cron ? `Schedule: ${cron}` : "Scheduled";
}
