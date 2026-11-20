import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToolRoutingSwitch } from "./ToolRoutingSwitch";

function response(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => vi.unstubAllGlobals());

describe("Live Tool Routing switch", () => {
  it("explains and disables itself without an OpenAI API key", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({ enabled: true, available: false, reason: "Add an OpenAI API key." })));
    render(<ToolRoutingSwitch active />);
    expect(await screen.findByText("Add an OpenAI API key.")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Live Tool Routing" })).toBeDisabled();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("turns off separately from Live Memory", async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      response(init?.method === "POST" ? { enabled: false, available: true, reason: null }
        : { enabled: true, available: true, reason: null }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ToolRoutingSwitch active />);
    const toggle = await screen.findByRole("switch", { name: "Live Tool Routing" });
    await vi.waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    await vi.waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "false"));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ enabled: false });
  });
});
