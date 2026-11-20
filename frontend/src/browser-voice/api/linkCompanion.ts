import { request } from "./request";

export const linkCompanionApi = {
  linkCompanion: () => request<{ status: string; displayName?: string; pairingId?: string; pairedAt?: string }>("/link-companion"),
  linkCompanionPairing: (code: string) =>
    request<{ pairingId: string; displayName: string; status: string }>(
      `/link-companion/pairing/${encodeURIComponent(code)}`,
    ),
  approveLinkCompanionPairing: (pairingId: string) =>
    request<{ status: string; displayName: string }>(
      `/link-companion/pairing/${encodeURIComponent(pairingId)}/approve`,
      { method: "POST", body: "{}" },
    ),
  unpairLinkCompanion: () =>
    request<{ status: string }>("/link-companion/unpair", { method: "POST", body: "{}" }),
};
