import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useConversation } from "@/browser-voice/conversation/useConversation";
import { ChatPanel } from "@/browser-voice/conversation/ChatPanel";

const api = vi.hoisted(() => ({ attach: vi.fn(), removeAttachment: vi.fn(), older: vi.fn(), activity: vi.fn(), recent: vi.fn(),
  create: vi.fn(), load: vi.fn(), send: vi.fn(), stop: vi.fn(), stream: vi.fn(), endSession: vi.fn() }));
vi.mock("@/browser-voice/conversation/api", () => ({ conversationApi: api }));
class Stream extends EventTarget {
  closed = false;
  onerror: (() => void) | null = null;
  close() { this.closed = true; }
  emit(sequence: number, kind: string, payload: object, turnId = "t") {
    this.dispatchEvent(new MessageEvent("conversation", { data: JSON.stringify({ sequence, kind, payload, turnId }) }));
  }
}
const header = { conversationId: "c", historyVersion: 1, title: "Test", state: "open" };
const timeline = { cardId: "k1", sources: ["calendar_list_events"], card: { version: 1, layout: "timeline", title: "Saturday",
  fallbackText: "Saturday plan", items: [{ time: "17:00", title: "<b>Cake</b>", state: "done" }, { time: "19:30", title: "Dinner", state: "needs_you" }] } };
const options = { cardId: "k2", sources: ["web_search"], card: { version: 1, layout: "options", title: "Dinner for 6",
  fallbackText: "Pick dinner", items: [{ title: "Lucia's", detail: "4.7 · 0.8 mi" }, { title: "Kin Thai" }] } };

beforeEach(() => {
  vi.clearAllMocks();
  api.recent.mockResolvedValue({ items: [header] });
  api.create.mockResolvedValue(header);
  api.load.mockResolvedValue({ ...header, turns: [] });
  api.send.mockResolvedValue({ ...header, turnId: "t", input: "Plan", state: "running" });
  api.activity.mockResolvedValue({});
  api.endSession.mockResolvedValue({});
  api.stream.mockImplementation(() => new Stream());
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});

it("streams a layout hint, then validated cards, and keeps them on the finished turn", async () => {
  const { result } = renderHook(() => useConversation(true));
  act(() => result.current.setDraft("Plan"));
  api.load.mockResolvedValue({ ...header, turns: [{ turnId: "t", input: "Plan", answer: null, state: "running" }] });
  await act(() => result.current.send());
  await waitFor(() => expect(api.stream).toHaveBeenCalled());
  const stream = api.stream.mock.results.at(-1)!.value as Stream;
  act(() => stream.emit(1, "ui_hint", { layouts: ["timeline", "html"], visualProbability: .9 }));
  expect(result.current.liveHint).toEqual(["timeline"]);
  act(() => {
    stream.emit(2, "ui", timeline);
    stream.emit(3, "ui", { cardId: "bad", sources: [], card: { layout: "iframe", fallbackText: "x" } });
    stream.emit(4, "text_delta", { text: "Here is Saturday." });
  });
  expect(result.current.liveCards.map(c => c.cardId)).toEqual(["k1"]);
  api.load.mockResolvedValue({ ...header, turns: [{ turnId: "t", input: "Plan", answer: "Here is Saturday.", state: "completed", ui: [timeline] }] });
  act(() => stream.emit(5, "terminal", { state: "completed" }));
  await waitFor(() => expect(result.current.running).toBeNull());
  expect(result.current.liveCards).toEqual([]);
  expect(result.current.turns[0].ui?.[0].cardId).toBe("k1");
});

it("renders history cards as text-only components and sends a tapped option as the next message", async () => {
  api.load.mockResolvedValue({ ...header, turns: [{ turnId: "t", input: "Plan", answer: "Two options.", state: "completed",
    ui: [timeline, options] }] });
  render(<ChatPanel active voiceActive={false} voiceBusy={false} onToggleVoice={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Open chat options" }));
  fireEvent.click(await screen.findByRole("button", { name: "Test" }));
  expect(await screen.findByRole("region", { name: "Saturday" })).toBeInTheDocument();
  expect(screen.getByText("<b>Cake</b>")).toBeInTheDocument();
  expect(document.querySelector(".vault-card b b")).toBeNull();
  expect(screen.getByText("Needs you")).toBeInTheDocument();
  expect(screen.getByText("Calendar")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Lucia's/ }));
  await waitFor(() => expect(api.send).toHaveBeenCalledTimes(1));
  expect(api.send.mock.calls[0][1].input).toBe("Lucia's");
  expect(screen.getByLabelText("Message your Vault")).toHaveValue("");
});
