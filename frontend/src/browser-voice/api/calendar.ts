import { request } from "./request";

export type CalendarAccount = {
  calendarAccountId: string;
  providerType: "ics" | "caldav";
  displayName: string;
  configuration: { feedUrl?: string; calendarUrl?: string };
  status: "active" | "disabled";
  sync: Record<string, unknown>;
  updatedAt: string;
};

export const calendarApi = {
  calendarAccounts: () =>
    request<{ items: CalendarAccount[] }>("/calendar/accounts"),
  connectCalendar: (value: {
    providerType: "ics" | "caldav";
    displayName?: string;
    credentials: {
      feedUrl?: string;
      calendarUrl?: string;
      username?: string;
      password?: string;
    };
    validateConnection: boolean;
  }) =>
    request<CalendarAccount>("/calendar/accounts", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  removeCalendar: (calendarAccountId: string) =>
    request<{ status: string }>(
      `/calendar/accounts/${encodeURIComponent(calendarAccountId)}`,
      { method: "DELETE" },
    ),
};
