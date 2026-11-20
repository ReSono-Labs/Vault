import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ChatPanel } from "./ChatPanel";

const api = vi.hoisted(() => ({ recent: vi.fn(), create: vi.fn(), load: vi.fn(), send: vi.fn(), stop: vi.fn(), stream: vi.fn() }));
vi.mock("./api", () => ({ conversationApi: api, genuiApi: { presentation: () => Promise.resolve({ version: 0, config: {}, notice: null, noticePending: false }) } }));
beforeEach(() => {
  api.recent.mockResolvedValue({ items: [] });
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => vi.unstubAllGlobals());

it("keeps the Chat microphone hidden with working Voice delegation available for restoration", async () => {
  const toggle = vi.fn();
  const view = render(<ChatPanel active voiceActive={false} voiceBusy={false} onToggleVoice={toggle} />);
  expect(await screen.findByText("Ask your Vault a question.")).toBeInTheDocument();
  const input = screen.getByLabelText("Message your Vault");
  fireEvent.change(input, { target: { value: "Draft words" } });
  fireEvent.change(input, { target: { value: "Draft" } });
  expect(input).toHaveValue("Draft");
  fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  expect(api.send).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Start Voice" })).not.toBeInTheDocument();
  const microphone = view.container.querySelector<HTMLButtonElement>(".vault-chat-microphone")!;
  expect(microphone).toHaveAttribute("hidden");
  expect(microphone).not.toBeVisible();
  // A temporary visibility restoration must still call the original Voice owner.
  microphone.removeAttribute("hidden");
  fireEvent.click(screen.getByRole("button", { name: "Start Voice" }));
  expect(toggle).toHaveBeenCalledTimes(1);
  microphone.setAttribute("hidden", "");
  view.rerender(<ChatPanel active={false} voiceActive voiceBusy={false} onToggleVoice={toggle} />);
  view.rerender(<ChatPanel active voiceActive voiceBusy={false} onToggleVoice={toggle} />);
  expect(screen.getByLabelText("Message your Vault")).toHaveValue("Draft");
  expect(screen.queryByRole("button", { name: "Stop Voice" })).not.toBeInTheDocument();
  expect(microphone).toHaveAttribute("aria-pressed", "true");
});

it("displays canonical history through actual donor messages without interpreting user HTML", async () => {
  api.recent.mockResolvedValue({ items: [{ conversationId: "old", title: "Old chat", historyVersion: 1, state: "open" }] });
  api.load.mockResolvedValue({ conversationId: "old", historyVersion: 1, state: "open", turns: [
    { turnId: "t", input: "<script>user text</script>", answer: "Original answer", state: "completed" },
  ] });
  render(<ChatPanel active voiceActive={false} voiceBusy={false} onToggleVoice={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Open chat options" }));
  fireEvent.click(await screen.findByRole("button", { name: "Old chat" }));
  expect(await screen.findByText("Original answer")).toBeInTheDocument();
  expect(screen.getByText("<script>user text</script>")).toBeInTheDocument();
  expect(document.querySelector(".vault-chat script")).toBeNull();
  expect(api.send).not.toHaveBeenCalled();
});

it("renders Vault's Markdown replies safely and keeps the owner's text literal", async () => {
  api.recent.mockResolvedValue({ items: [{ conversationId: "md", title: "Brief", historyVersion: 1, state: "open" }] });
  api.load.mockResolvedValue({ conversationId: "md", historyVersion: 1, state: "open", turns: [
    { turnId: "t", input: "**not bold**", state: "completed", answer: [
      "Nightly brief complete.", "",
      "- **Markets:** Mixed close.", "- See [the report](https://example.com/report).", "",
      "| City | Temp |", "| --- | --- |", "| Boston | 41 |", "",
      "```", "print('hi')", "```", "",
      "<script>alert(1)</script>", "", "Try [bad](javascript:alert(1)) here.",
    ].join("\n") },
  ] });
  render(<ChatPanel active voiceActive={false} voiceBusy={false} onToggleVoice={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Open chat options" }));
  fireEvent.click(await screen.findByRole("button", { name: "Brief" }));
  const bold = await screen.findByText("Markets:");
  expect(bold.tagName).toBe("STRONG");
  expect(bold.closest("li")).not.toBeNull();
  const link = screen.getByRole("link", { name: "the report" });
  expect(link).toHaveAttribute("href", "https://example.com/report");
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(screen.getByRole("columnheader", { name: "City" }).closest(".vault-chat-table-wrap")).not.toBeNull();
  expect(screen.getByRole("cell", { name: "Boston" })).toBeInTheDocument();
  expect(screen.getByText("print('hi')").closest("pre")).not.toBeNull();
  expect(document.querySelector(".vault-chat script")).toBeNull();
  expect(screen.getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
  const bad = screen.getByText("bad");
  expect(bad.getAttribute("href") ?? "").not.toMatch(/javascript/i);
  // The owner's own message is never interpreted.
  expect(screen.getByText("**not bold**")).toBeInTheDocument();
});

it("copies a sent message and a reply from the buttons beside the ratings", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  vi.stubGlobal("isSecureContext", true);
  api.recent.mockResolvedValue({ items: [{ conversationId: "cp", title: "Copy chat", historyVersion: 1, state: "open" }] });
  api.load.mockResolvedValue({ conversationId: "cp", historyVersion: 1, state: "open", turns: [
    { turnId: "t1", input: "What changed today?", state: "completed", answer: "**Two** things changed." },
    { turnId: "t2", input: null, state: "completed", answer: "Your routine ran." },
  ] });
  render(<ChatPanel active voiceActive={false} voiceBusy={false} onToggleVoice={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Open chat options" }));
  fireEvent.click(await screen.findByRole("button", { name: "Copy chat" }));
  const message = await screen.findByRole("button", { name: "Copy message" });
  const replies = screen.getAllByRole("button", { name: "Copy reply" });
  expect(replies).toHaveLength(2);   // one beside 👍/👎, one under the reply Vault sent on its own
  expect(replies[0].closest(".vault-feedback-bar")).not.toBeNull();
  fireEvent.click(message);
  expect(writeText).toHaveBeenLastCalledWith("What changed today?");
  expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  fireEvent.click(replies[0]);
  expect(writeText).toHaveBeenLastCalledWith("**Two** things changed.");
});
