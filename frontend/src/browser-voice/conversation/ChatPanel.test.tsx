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
