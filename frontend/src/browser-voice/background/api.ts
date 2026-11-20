import { request } from "@/browser-voice/localApi";

export type CanonicalWorkStatus = "queued" | "running" | "working" | "needs-you" | "done" | "failed" | "unknown";

export type LinkedCanonicalTask = {
  taskId: string;
  text: string;
  status: string;
  completedAt?: string | null;
  updatedAt?: string | null;
};

export type SanitizedWorkResult = {
  status: string | null;
  summary: string | null;
  artifact_references: string[];
  verification_summary: string | null;
};

export type BackgroundWorkItem = {
  workId: string;
  state: string;
  statusLabel: CanonicalWorkStatus;
  intentVersion: number;
  objective: string;
  workerId: string | null;
  workerGeneration: number | null;
  roleKey: string | null;
  grantId?: string | null;
  routineId?: string | null;
  taskId: string | null;
  task: LinkedCanonicalTask | null;
  pendingActionId: string | null;
  result: SanitizedWorkResult | null;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  activeSeconds?: number | null;
  runId?: string | null;
  failureCode?: string | null;
  completedAt?: string | null;
  modelTurns?: number | null;
  toolCalls?: number | null;
};

export type BackgroundReasoningEntry = { type: string; createdAt: string; detail: Record<string, unknown> };

export type BackgroundWorkDetail = BackgroundWorkItem & {
  brief?: { objective?: string | null; successCriteria?: string[]; expectedResult?: string | null; contextSummary?: string | null };
  reasoningEntries?: BackgroundReasoningEntry[];
};

export type BackgroundActionItem = {
  actionId: string;
  actionHash: string;
  scheduleKind?: string | null;
  conversationId?: string | null;
  voiceSessionId?: string | null;
  workId?: string | null;
  intentVersion?: number | null;
  workerGeneration?: number | null;
  kind: string;
  title: string;
  detail: string;
  detailLines?: string[];
  state: string;
  expiresAt: string | null;
  createdAt?: string | null;
  channels: ("browser" | "link")[];
};

export type WebsiteOwnerApprovalItem = {
  id: string;
  conversationId?: string | null;
  voiceSessionId?: string | null;
  actionHash?: string;
  kind: string;
  title: string;
  detail: string;
  detailLines?: string[];
  createdAt?: string;
  expiresAt?: string;
};

export type BackgroundWorkerItem = {
  workerId: string;
  roleKey: string;
  purpose: string;
  instructions: string;
  toolNames: string[];
  resourcePolicy: Record<string, unknown>;
  limits?: Record<string, unknown>;
  generation: number;
  status: string;
  createdAt?: string;
  updatedAt?: string;
};

export type BackgroundRoutineItem = {
  routineId: string;
  version: number;
  rule: Record<string, unknown>;
  timezone: string;
  nextDueAt: string | null;
  grantId?: string;
  status: string;
  objective: string;
  createdAt?: string;
  updatedAt?: string;
};

export type QuietHoursConfig = {
  start?: string;
  end?: string;
  timezone?: string;
};

export type BackgroundPreferences = {
  enabled: boolean;
  optIn: boolean;
  quietHours: QuietHoursConfig;
  approvedGrantIds: string[];
  standingScope: string;
  updatedAt?: string | null;
};

function makeDecisionId(actionId: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `dec-${actionId}-${crypto.randomUUID()}`;
  }
  return `dec-${actionId}-${Date.now()}`;
}

export const backgroundApi = {
  preferences: () => request<BackgroundPreferences>("/background/preferences"),
  savePreferences: (payload: {
    enabled?: boolean;
    quietHours?: QuietHoursConfig;
    approvedGrantIds?: string[];
  }) =>
    request<BackgroundPreferences>("/background/preferences", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  workList: () => request<{ items: BackgroundWorkItem[] }>("/background/work"),
  work: (workId: string) => request<BackgroundWorkDetail>(`/background/work/${encodeURIComponent(workId)}`),
  cancelWork: (workId: string) =>
    request<{ workId: string; state: string; statusLabel: CanonicalWorkStatus }>(
      `/background/work/${encodeURIComponent(workId)}/cancel`,
      {
        method: "POST",
        body: "{}",
      },
    ),
  linkWorkTask: (workId: string, taskId: string | null) =>
    request<BackgroundWorkItem>(`/background/work/${encodeURIComponent(workId)}/task`, {
      method: "POST",
      body: JSON.stringify({ taskId }),
    }),
  actions: () => request<{ items: BackgroundActionItem[] }>("/background/actions"),
  decideAction: (actionId: string, actionHash: string, choice: "allow_once" | "deny", decisionId?: string) =>
    request<{ actionId: string; decisionId: string; state: string; workerId?: string; grantId?: string; routineId?: string }>(
      `/background/actions/${encodeURIComponent(actionId)}/decision`,
      {
        method: "POST",
        body: JSON.stringify({
          actionHash,
          choice,
          decisionId: decisionId || makeDecisionId(actionId),
        }),
      },
    ),
  websiteApprovals: () => request<{ items: WebsiteOwnerApprovalItem[] }>("/approvals"),
  decideWebsiteApproval: (approvalId: string, choice: "allow_once" | "deny", actionHash?: string) =>
    request<{ status: string }>(`/approvals/${encodeURIComponent(approvalId)}/decision`, {
      method: "POST",
      body: JSON.stringify(actionHash ? { choice, actionHash } : { choice }),
    }),
  workers: () => request<{ items: BackgroundWorkerItem[] }>("/background/workers"),
  workerAction: (workerId: string, op: "pause" | "reset" | "delete", generation: number) =>
    request<{ workerId: string; generation: number; status: string }>(
      `/background/workers/${encodeURIComponent(workerId)}/${op}`,
      {
        method: "POST",
        body: JSON.stringify({ generation }),
      },
    ),
  routines: () => request<{ items: BackgroundRoutineItem[] }>("/background/routines"),
  routineAction: (routineId: string, op: "pause" | "cancel") =>
    request<{ routineId: string; status: string }>(
      `/background/routines/${encodeURIComponent(routineId)}/${op}`,
      {
        method: "POST",
        body: "{}",
      },
    ),
};
