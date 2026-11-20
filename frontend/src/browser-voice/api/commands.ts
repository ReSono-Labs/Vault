import { request } from "./request";

export type CommandSettings = { enabled: boolean; available: boolean };

/** A command an agent asked to run in Chat, waiting for the person's Run / Don't run. */
export type PendingCommand = {
  requestId: string;
  directory: string;
  command: string;
  state: "pending" | "approved";
  expiresAt: string;
};

export const commandsApi = {
  commandSettings: () => request<CommandSettings>("/commands/settings"),
  setCommandsEnabled: (enabled: boolean) =>
    request<CommandSettings>("/admin/commands/settings", { method: "POST", body: JSON.stringify({ enabled }) }),
  pendingCommands: (conversationId: string) =>
    request<{ items: PendingCommand[] }>(`/commands/pending?conversationId=${encodeURIComponent(conversationId)}`),
  decideCommand: (requestId: string, approve: boolean) =>
    request<{ requestId: string; state: string }>(
      `/commands/${encodeURIComponent(requestId)}/${approve ? "approve" : "deny"}`,
      { method: "POST", body: "{}" },
    ),
};
