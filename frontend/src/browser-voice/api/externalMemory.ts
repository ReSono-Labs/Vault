import { request } from "./request";

export type ExternalMemoryIntegration = {
  integrationId: string;
  displayName: string;
  adapterKind: string;
  grants: ("search" | "propose" | "correct" | "forget")[];
  status: "active" | "revoked";
  createdAt: string;
  revokedAt: string | null;
};

export type ExternalMemoryPairing = {
  pairingId: string;
  displayName: string;
  adapterKind: string;
  grants: ExternalMemoryIntegration["grants"];
  status: "pending";
};

export const externalMemoryApi = {
  externalMemoryIntegrations: () =>
    request<{ items: ExternalMemoryIntegration[] }>("/external-memory/integrations"),
  createExternalMemoryIntegration: (value: {
    displayName: string;
    adapterKind: string;
    grants: ExternalMemoryIntegration["grants"];
  }) => request<ExternalMemoryIntegration & { credential: string }>(
    "/external-memory/integrations", { method: "POST", body: JSON.stringify(value) },
  ),
  externalMemoryPairing: (code: string) =>
    request<ExternalMemoryPairing>(
      `/external-memory/integrations/pairing/${encodeURIComponent(code)}`,
    ),
  approveExternalMemoryPairing: (pairingId: string) =>
    request<ExternalMemoryIntegration>(
      `/external-memory/integrations/pairing/${encodeURIComponent(pairingId)}/approve`,
      { method: "POST", body: "{}" },
    ),
  revokeExternalMemoryIntegration: (integrationId: string) =>
    request<{ status: string }>(
      `/external-memory/integrations/${encodeURIComponent(integrationId)}/revoke`,
      { method: "POST", body: "{}" },
    ),
  removeExternalMemoryIntegration: (integrationId: string) =>
    request<{ status: string }>(
      `/external-memory/integrations/${encodeURIComponent(integrationId)}`,
      { method: "DELETE", body: "{}" },
    ),
};
