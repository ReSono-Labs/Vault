import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Agent2AgentPanel } from "@/browser-voice/Agent2AgentPanel";
import { BackgroundRunsPanel } from "@/browser-voice/BackgroundRunsPanel";
import { BackgroundApprovals } from "@/browser-voice/background/BackgroundApprovals";
import { CommandApprovals } from "@/browser-voice/commands/CommandApprovals";
import { whenVisible } from "@/browser-voice/polling";

let visibility: DocumentVisibilityState = "visible";

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

const runningWork = {
  workId: "w1", state: "running", statusLabel: "running", intentVersion: 1, objective: "Sort the inbox", workerId: null,
  workerGeneration: null, roleKey: null, taskId: null, task: null, pendingActionId: null, result: null,
  createdAt: "2026-11-19T10:00:00Z", updatedAt: "2026-11-19T10:00:00Z",
};

function stubFetch() {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/background/work") return response({ items: [runningWork] });
    if (path === "/background/work/w1") return response(runningWork);
    if (path === "/builtin-plugins") return response({ items: [] });
    if (path === "/link-companion") return response({ status: "unpaired" });
    return response({ items: [] });
  });
  vi.stubGlobal("fetch", fetchMock);
  return (prefix: string) => fetchMock.mock.calls.filter(([input]) => String(input) === prefix || String(input).startsWith(`${prefix}?`)).length;
}

/** Let pending fetches and state updates settle, then move the poll clock on. */
async function tick(ms: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

beforeEach(() => {
  visibility = "visible";
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout"] });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(document, "visibilityState");
});

describe("polling pauses while the page is hidden", () => {
  it("whenVisible skips the tick only while hidden", () => {
    const fn = vi.fn();
    const wrapped = whenVisible(fn);
    wrapped();
    visibility = "hidden";
    wrapped();
    visibility = "visible";
    wrapped();
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("Chat approvals pause while hidden and resume when visible", async () => {
    const calls = stubFetch();
    render(<BackgroundApprovals conversationId="c1" pollIntervalMs={1500} />);
    await tick(0);
    const first = calls("/background/actions");
    expect(first).toBe(1);
    visibility = "hidden";
    await tick(6000);
    expect(calls("/background/actions")).toBe(first);
    visibility = "visible";
    await tick(1500);
    expect(calls("/background/actions")).toBe(first + 1);
  });

  it("Voice approvals keep polling while hidden (owner decision 7-C)", async () => {
    const calls = stubFetch();
    render(<BackgroundApprovals voiceSessionId="v1" pollIntervalMs={1500} pollWhileHidden />);
    await tick(0);
    visibility = "hidden";
    await tick(4500);
    expect(calls("/background/actions")).toBe(1 + 3);
  });

  it("command approvals pause while hidden", async () => {
    const calls = stubFetch();
    render(<CommandApprovals conversationId="c1" running onDecided={() => undefined} />);
    await tick(0);
    visibility = "hidden";
    await tick(6000);
    expect(calls("/commands/pending")).toBe(1);
    visibility = "visible";
    await tick(2000);
    expect(calls("/commands/pending")).toBe(2);
  });

  it("the Background work list and an open running item pause while hidden", async () => {
    const calls = stubFetch();
    render(<BackgroundRunsPanel />);
    await tick(0);
    expect(calls("/background/work")).toBe(1);
    visibility = "hidden";
    await tick(9000);
    expect(calls("/background/work")).toBe(1);
    visibility = "visible";
    await tick(3000);
    expect(calls("/background/work")).toBe(2);

    fireEvent.click(screen.getByRole("button", { name: "Open Sort the inbox" }));
    await tick(0);
    const detail = calls("/background/work/w1");
    expect(detail).toBe(1);
    visibility = "hidden";
    await tick(9000);
    expect(calls("/background/work/w1")).toBe(detail);
    visibility = "visible";
    await tick(3000);
    expect(calls("/background/work/w1")).toBe(detail + 1);
  });

  it("External agents pause while hidden", async () => {
    const calls = stubFetch();
    render(<Agent2AgentPanel />);
    await tick(0);
    expect(calls("/agent2agent/connections")).toBe(1);
    visibility = "hidden";
    await tick(15000);
    expect(calls("/agent2agent/connections")).toBe(1);
    visibility = "visible";
    await tick(5000);
    expect(calls("/agent2agent/connections")).toBe(2);
  });
});
