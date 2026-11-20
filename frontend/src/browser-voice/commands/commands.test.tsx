import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommandApprovals } from "@/browser-voice/commands/CommandApprovals";
import { SettingsCommandsSection } from "@/browser-voice/commands/SettingsCommandsSection";

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => vi.unstubAllGlobals());

describe("command approvals in Chat", () => {
  it("runs nothing until the person clicks Run, then tells the agent", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith("/commands/pending"))
        return response({ items: [{ requestId: "r1", directory: "local/Projects/app", command: "npm test", state: "pending", expiresAt: "" }] });
      if (path === "/commands/r1/approve") return response({ requestId: "r1", state: "approved" });
      return response({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDecided = vi.fn();
    render(<CommandApprovals conversationId="c1" running={false} onDecided={onDecided} />);
    expect(await screen.findByText("npm test")).toBeInTheDocument();
    expect(screen.getByText("In local/Projects/app")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await vi.waitFor(() => expect(onDecided).toHaveBeenCalled());
    expect(onDecided.mock.calls[0][0]).toContain("request r1");
    expect(fetchMock.mock.calls.some(([path, init]) => String(path) === "/commands/r1/approve" && init?.method === "POST")).toBe(true);
    expect(screen.queryByText("npm test")).not.toBeInTheDocument();
  });

  it("Don't run denies it", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith("/commands/pending"))
        return response({ items: [{ requestId: "r2", directory: "local/P", command: "rm -rf build", state: "pending", expiresAt: "" }] });
      return response({ requestId: "r2", state: "denied" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDecided = vi.fn();
    render(<CommandApprovals conversationId="c1" running={false} onDecided={onDecided} />);
    fireEvent.click(await screen.findByRole("button", { name: "Don't run" }));
    await vi.waitFor(() => expect(onDecided).toHaveBeenCalledWith("Don't run that command (request r2)."));
    expect(fetchMock.mock.calls.some(([path]) => String(path) === "/commands/r2/deny")).toBe(true);
  });
});

describe("Settings > Commands", () => {
  it("only the master account gets the switch", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({ enabled: false, available: true })));
    const { unmount } = render(<SettingsCommandsSection isAdmin={false} />);
    expect(await screen.findByText(/master account turns this on or off/)).toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    unmount();
    render(<SettingsCommandsSection isAdmin />);
    expect(await screen.findByRole("switch", { name: "Turn commands on" })).toBeEnabled();
  });
});
