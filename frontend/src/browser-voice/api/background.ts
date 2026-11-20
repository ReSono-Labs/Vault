import { request } from "./request";

export type BackgroundRun = {
  runId: string;
  objective: string;
  invocationType: string;
  originId: string;
  state: string;
  cancellationRequested: boolean;
  output: Record<string, unknown> | null;
  failure: { code: string | null; message: string | null } | null;
  failureCode: string | null;
  failureMessage: string | null;
  failureExplanation: string | null;
  modelTurns: number;
  toolCalls: number;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  reasoningEntries: { type: string; createdAt: string; detail: Record<string, unknown> }[];
  progress: {
    label: string;
    fraction: number;
    active: boolean;
    tone: string;
    activity: string;
    modelTurns: number;
    toolCalls: number;
    timeline: { label: string; createdAt: string }[];
  };
};

export type VaultTask = {
  taskId: string;
  text: string;
  status: "open" | "completed";
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
};

export const backgroundApi = {
  backgroundRuns: () => request<{ items: BackgroundRun[] }>("/background/runs"),
  deleteBackgroundRun: (runId: string) => request<{ runId: string; deleted: boolean }>(
    `/background/runs/${encodeURIComponent(runId)}`,
    { method: "DELETE" },
  ),
};
