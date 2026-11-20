import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BackgroundSettings } from "@/browser-voice/background/BackgroundSettings";

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("BackgroundSettings", () => {
  it("shows explicit standing scope when opting in, updates quiet hours, and controls workers and routines without worker inboxes", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/background/preferences" && (!init?.method || init.method === "GET")) {
        return response({
          enabled: false,
          optIn: false,
          quietHours: { start: "22:00", end: "07:00", timezone: "UTC" },
          approvedGrantIds: [],
          standingScope:
            "Allows read and preparation checks on committed Chat/Voice turns and connected mail/calendar. Specialist creation and external writes still require your approval.",
        });
      }
      if (path === "/background/preferences" && init?.method === "POST") {
        const body = JSON.parse(String(init.body || "{}"));
        return response({
          enabled: Boolean(body.enabled),
          optIn: Boolean(body.enabled),
          quietHours: body.quietHours || { start: "22:00", end: "07:00", timezone: "UTC" },
          approvedGrantIds: [],
          standingScope:
            "Allows read and preparation checks on committed Chat/Voice turns and connected mail/calendar. Specialist creation and external writes still require your approval.",
        });
      }
      if (path === "/background/workers" && (!init?.method || init.method === "GET")) {
        return response({
          items: [
            {
              workerId: "w-1",
              roleKey: "inbox-triage",
              purpose: "Triage incoming newsletters and summarize urgent threads",
              instructions: "Inspect headers and summarize.",
              toolNames: ["email_list", "email_read"],
              resourcePolicy: {},
              generation: 2,
              status: "idle",
            },
          ],
        });
      }
      if (path === "/background/workers/w-1/pause" && init?.method === "POST") {
        return response({ workerId: "w-1", generation: 3, status: "paused" });
      }
      if (path === "/background/workers/w-1/reset" && init?.method === "POST") {
        return response({ workerId: "w-1", generation: 4, status: "idle" });
      }
      if (path === "/background/workers/w-1/delete" && init?.method === "POST") {
        return response({ workerId: "w-1", generation: 5, status: "deleted" });
      }
      if (path === "/background/routines" && (!init?.method || init.method === "GET")) {
        return response({
          items: [
            {
              routineId: "rt-1",
              version: 1,
              rule: { kind: "cron", cron: "0 8 * * *" },
              timezone: "America/New_York",
              nextDueAt: "2026-11-18T13:00:00Z",
              status: "active",
              objective: "Morning inbox brief",
            },
          ],
        });
      }
      if (path === "/background/routines/rt-1/pause" && init?.method === "POST") {
        return response({ routineId: "rt-1", status: "paused" });
      }
      return response({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<BackgroundSettings />);

    // Standing scope is explicitly shown
    expect(
      await screen.findByText(/Specialist creation and external writes still require your approval/i),
    ).toBeInTheDocument();

    // Worker purpose and tool scope are shown without any worker inbox UI
    expect(screen.getByText("inbox-triage")).toBeInTheDocument();
    expect(
      screen.getByText("Triage incoming newsletters and summarize urgent threads"),
    ).toBeInTheDocument();
    expect(screen.getByText(/email_list, email_read/)).toBeInTheDocument();
    expect(screen.queryByText(/inbox messages/i)).not.toBeInTheDocument();

    // Opt in switch
    fireEvent.click(screen.getByRole("switch", { name: /Automatic background observation/i }));
    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([path, init]) => String(path) === "/background/preferences" && init?.method === "POST",
        ),
      ).toBe(true),
    );

    // Save quiet hours
    fireEvent.change(screen.getByLabelText(/Quiet hours start/i), { target: { value: "21:30" } });
    fireEvent.click(screen.getByRole("button", { name: /Save quiet hours/i }));
    await vi.waitFor(() => {
      const qhCall = fetchMock.mock.calls.find(
        ([path, init]) =>
          String(path) === "/background/preferences" &&
          init?.method === "POST" &&
          String(init.body || "").includes("21:30"),
      );
      expect(qhCall).toBeDefined();
    });

    // Pause, reset, delete worker send expected generation
    fireEvent.click(screen.getByRole("button", { name: "Pause specialist inbox-triage" }));
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([path, init]) => String(path) === "/background/workers/w-1/pause" && init?.method === "POST",
      );
      expect(call).toBeDefined();
      expect(JSON.parse(String(call?.[1]?.body || "{}")).generation).toBe(2);
    });

    fireEvent.click(screen.getByRole("button", { name: "Reset specialist inbox-triage" }));
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([path, init]) => String(path) === "/background/workers/w-1/reset" && init?.method === "POST",
      );
      expect(call).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete specialist inbox-triage" }));
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([path, init]) =>
          String(path) === "/background/workers/w-1/delete" && init?.method === "POST",
      );
      expect(call).toBeDefined();
    });

    // Routines show a short row with their schedule; Pause is in the routine's details.
    expect(screen.getByText("Every day at 8:00 AM")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open routine Morning inbox brief" }));
    expect(screen.getByRole("button", { name: "← Routines" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pause routine Morning inbox brief" }));
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([path, init]) =>
          String(path) === "/background/routines/rt-1/pause" && init?.method === "POST",
      );
      expect(call).toBeDefined();
    });
  });
});
