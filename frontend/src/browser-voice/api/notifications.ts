import { request } from "./request";

export type VaultNotification = {
  notificationId: string;
  kind: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  createdAt: string;
};

export const notificationsApi = {
  notifications: () => request<{ items: VaultNotification[]; unreadCount: number }>("/notifications"),
  clearNotification: (notificationId: string) =>
    request<{ status: string; notificationId: string }>(`/notifications/${encodeURIComponent(notificationId)}/clear`, {
      method: "POST",
      body: "{}",
    }),
  clearAllNotifications: () => request<{ status: string; clearedCount: number }>("/notifications/clear", {
    method: "POST",
    body: "{}",
  }),
};
