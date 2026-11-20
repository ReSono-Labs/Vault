import { request } from "./request";

export type A2AConnection = {
  connectionId: string;
  displayName: string;
  cardUrl: string;
  enabled: boolean;
  agentCard: {
    name?: string;
    description?: string;
    version?: string;
    provider?: { organization?: string; url?: string };
    capabilities?: Record<string, unknown>;
    supportedInterfaces?: Array<{ url?: string; protocolBinding?: string; protocolVersion?: string }>;
    skills?: Array<{ id?: string; name?: string; description?: string; tags?: string[] }>;
  };
};

export type A2ANotification = {
  taskId: string;
  agentName: string;
  state: string;
  summary: string;
  issue: string | null;
  ownerKind: "voice" | "background";
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
};

export const agentNetworkApi = {
  a2aConnections: () => request<{ items: A2AConnection[] }>("/agent2agent/connections"),
  a2aNotifications: () => request<{ items: A2ANotification[] }>("/agent2agent/notifications"),
  a2aListen: () => request<{ cardUrl: string; rpcUrl: string; tokenHint: string }>("/agent2agent/listen"),
  /** The inbound bearer itself: only for an explicit Show or Copy click. */
  a2aListenToken: () => request<{ token: string }>("/agent2agent/listen/token", { method: "POST", body: "{}" }),
  /** Make a new inbound bearer; the old one stops working immediately. */
  a2aListenRotate: () => request<{ cardUrl: string; rpcUrl: string; tokenHint: string }>("/agent2agent/listen/rotate", { method: "POST", body: "{}" }),
  connectA2A: (value: { displayName: string; cardUrl: string; token?: string }) =>
    request<A2AConnection>("/agent2agent/connections", { method: "POST", body: JSON.stringify(value) }),
  removeA2A: (connectionId: string) => request<{ status: string }>(
    `/agent2agent/connections/${encodeURIComponent(connectionId)}`, { method: "DELETE" },
  ),
};
