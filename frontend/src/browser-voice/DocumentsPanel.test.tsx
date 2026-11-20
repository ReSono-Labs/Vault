import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DocumentsPanel } from "@/browser-voice/DocumentsPanel";
import { localApi } from "@/browser-voice/localApi";


describe("document page navigation", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows working back and next controls on every document", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const name = String(input).split("/").pop()?.replace(".md", "") ?? "Guide";
      return Promise.resolve(new Response(
        `# ${name}\n\n## First page\n\nFirst content.\n\n## Second page\n\nSecond content.`,
        { status: 200, headers: { "Content-Type": "text/markdown" } },
      ));
    }));

    render(<DocumentsPanel />);

    const next = await screen.findByRole("button", { name: "Next: Second page" });
    expect(screen.getByRole("button", { name: "Back: First page" })).toBeDisabled();
    fireEvent.click(next);
    expect(await screen.findByText("Second content.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back: First page" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Next: Last page" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Hermes & OpenClaw Memory/ }));
    expect(await screen.findByText("First content.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back: First page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next: Second page" })).toBeEnabled();
  });
});

describe("Vault Help suggestions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends a suggestion from the chat window and hides chips after the first message", async () => {
    vi.spyOn(localApi, "askHelp").mockResolvedValue({
      answer: "Connect a provider in Connections.",
      providerKey: "openai",
      modelKey: "gpt-4.1",
      sources: [],
      learned: false,
    });

    render(<DocumentsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Ask Vault Help" }));

    const suggestion = screen.getByRole("button", { name: "How do I connect an AI provider?" });
    expect(suggestion.closest(".browser-voice-help-messages")).not.toBeNull();
    fireEvent.click(suggestion);

    expect(await screen.findByText("Connect a provider in Connections.")).toBeInTheDocument();
    expect(localApi.askHelp).toHaveBeenCalledWith("How do I connect an AI provider?", [], false);
    expect(screen.queryByRole("button", { name: "How do I connect an AI provider?" })).not.toBeInTheDocument();
  });

  it("hides suggestion chips when the user starts typing", async () => {
    render(<DocumentsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Ask Vault Help" }));
    expect(screen.getByRole("button", { name: "Help me fix a common problem." })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Ask Vault Help"), { target: { value: "How do backups work?" } });
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Help me fix a common problem." })).not.toBeInTheDocument();
    });
  });
});
