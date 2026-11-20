import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BackgroundApprovals } from "@/browser-voice/background/BackgroundApprovals";

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("BackgroundApprovals", () => {
  it("recommends a new specialist role with explicit scope and approves it once", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/background/actions") {
        return response({
          items: [
            {
              actionId: "act-worker-1",
              actionHash: "a".repeat(64),
              kind: "worker_create",
              title: "Create inbox-triage specialist",
              detail: "Triage incoming newsletters and summarize urgent threads",
              detailLines: [
                "Role: inbox-triage",
                "Purpose: Triage incoming newsletters and summarize urgent threads",
                "Tools: email_list, email_read",
              ],
              state: "pending",
              expiresAt: "2026-11-17T23:59:59Z",
              channels: ["browser", "link"],
            },
          ],
        });
      }
      if (path === "/approvals") {
        return response({ items: [] });
      }
      if (path === "/background/actions/act-worker-1/decision" && init?.method === "POST") {
        return response({
          actionId: "act-worker-1",
          decisionId: "dec-1",
          state: "completed",
          workerId: "worker-1",
        });
      }
      return response({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDecided = vi.fn();

    render(<BackgroundApprovals isDeviceOwner onDecided={onDecided} />);

    expect(await screen.findByText("Create inbox-triage specialist")).toBeInTheDocument();
    expect(screen.getByText(/Tools: email_list, email_read/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Allow once" }));

    await vi.waitFor(() => expect(onDecided).toHaveBeenCalled());
    const decisionCall = fetchMock.mock.calls.find(
      ([path, init]) =>
        String(path) === "/background/actions/act-worker-1/decision" && init?.method === "POST",
    );
    expect(decisionCall).toBeDefined();
    const sentBody = JSON.parse(String(decisionCall?.[1]?.body || "{}"));
    expect(sentBody.choice).toBe("allow_once");
    expect(sentBody.actionHash).toBe("a".repeat(64));
    expect(typeof sentBody.decisionId).toBe("string");
  });

  it("denies a pending action and shows only browser decision for secondary users without owner phone option", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/background/actions") {
        return response({
          items: [
            {
              actionId: "act-task-2",
              actionHash: "b".repeat(64),
              workId: "work-2",
              kind: "tasks",
              title: "Review tasks",
              detail: "Add task: Prepare quarterly review",
              detailLines: ["Add task: Prepare quarterly review"],
              state: "pending",
              expiresAt: "2026-11-17T23:59:59Z",
              channels: ["browser"],
            },
          ],
        });
      }
      if (path === "/approvals") {
        return response({ items: [] });
      }
      if (path === "/background/actions/act-task-2/decision" && init?.method === "POST") {
        return response({
          actionId: "act-task-2",
          decisionId: "dec-2",
          state: "denied",
        });
      }
      return response({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDecided = vi.fn();

    render(<BackgroundApprovals isDeviceOwner={false} onDecided={onDecided} />);

    expect(await screen.findByText("Review tasks")).toBeInTheDocument();
    expect(screen.queryByText(/Link phone/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Deny" }));

    await vi.waitFor(() => expect(onDecided).toHaveBeenCalled());
    const decisionCall = fetchMock.mock.calls.find(
      ([path, init]) =>
        String(path) === "/background/actions/act-task-2/decision" && init?.method === "POST",
    );
    expect(decisionCall).toBeDefined();
    const sentBody = JSON.parse(String(decisionCall?.[1]?.body || "{}"));
    expect(sentBody.choice).toBe("deny");
    expect(sentBody.actionHash).toBe("b".repeat(64));
  });
});

it("lists only this session's pending approvals and opens the tapped card", async () => {
  const action = (actionId: string, title: string, conversationId: string) => ({
    actionId, title, conversationId, actionHash: "a".repeat(64), kind: "routine_create",
    detail: `Details for ${title}`, state: "pending",
  });
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => response({
    items: String(input) === "/background/actions" ? [
      action("first", "Morning routine", "chat"),
      action("second", "Evening routine", "chat"),
      action("foreign", "Other chat routine", "other-chat"),
    ] : [],
  })));
  render(<BackgroundApprovals conversationId="chat" />);
  const morning = await screen.findByRole("button", { name: "Morning routine" });
  expect(screen.queryByText("Other chat routine")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Approve recurring schedule" })).not.toBeInTheDocument();
  fireEvent.click(morning);
  expect(screen.getByText("Details for Morning routine")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Approve recurring schedule" })).toBeInTheDocument();
});
