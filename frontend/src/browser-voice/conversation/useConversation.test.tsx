import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useConversation } from "./useConversation";

const api = vi.hoisted(() => ({ attach: vi.fn(), removeAttachment: vi.fn(), older: vi.fn(), activity: vi.fn(), recent: vi.fn(), create: vi.fn(), load: vi.fn(), send: vi.fn(), stop: vi.fn(), stream: vi.fn(), endSession: vi.fn(), turnStatus: vi.fn() }));
vi.mock("./api", () => ({ conversationApi: api }));
class Stream extends EventTarget {
  closed = false;
  onerror: (() => void) | null = null;
  close() { this.closed = true; }
  emit(sequence: number, kind: string, payload: object, turnId = "t") {
    this.dispatchEvent(new MessageEvent("conversation", { data: JSON.stringify({ sequence, kind, payload, turnId }) }));
  }
}
const header = { conversationId: "c", historyVersion: 1, title: "Test", state: "open" };

describe("scoped Chat controller", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.recent.mockResolvedValue({ items: [header] });
    api.create.mockResolvedValue(header);
    api.load.mockResolvedValue({ ...header, turns: [] });
    api.send.mockResolvedValue({ ...header, turnId: "t", input: "Hello", state: "running" });
    api.stop.mockResolvedValue({});
    api.endSession.mockResolvedValue({});
    api.activity.mockResolvedValue({});
    api.stream.mockImplementation(() => new Stream());
  });

  it("prepends older canonical pages without changing active turn or history version", async () => {
    api.load.mockResolvedValue({ ...header, turns: [{ turnId: "new", input: "New", answer: "Answer", state: "completed" }], nextBefore: 40 });
    api.older.mockResolvedValue({ ...header, turns: [{ turnId: "old", input: "Old", answer: "Earlier", state: "completed" }], nextBefore: null });
    const { result } = renderHook(() => useConversation(true));
    act(() => result.current.select("c"));
    await waitFor(() => expect(result.current.nextBefore).toBe(40));
    await act(() => result.current.loadOlder());
    expect(api.older).toHaveBeenCalledWith("c", 40);
    expect(result.current.turns.map(t => t.turnId)).toEqual(["old", "new"]);
    expect(result.current.nextBefore).toBeNull();
    expect(api.send).not.toHaveBeenCalled();
  });

  it("sends text-free throttled activity for edits independently of preparation", async () => {
    const { result } = renderHook(() => useConversation(true));
    act(() => result.current.select("c"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setDraft("Private unsent text"));
    act(() => result.current.setDraft("Deleted and replaced"));
    expect(api.activity).toHaveBeenCalledTimes(1);
    expect(api.activity).toHaveBeenCalledWith("c");
    expect(api.send).not.toHaveBeenCalled();
  });

  it("ends only an idle previous session on New Chat while preserving saved history", async () => {
    api.load.mockResolvedValue({ ...header, turns: [{ turnId: "t", input: "Hello", answer: "Answer", state: "completed" }] });
    const { result } = renderHook(() => useConversation(true));
    act(() => result.current.select("c"));
    await waitFor(() => expect(result.current.turns).toHaveLength(1));
    act(() => result.current.select(null));
    expect(api.endSession).toHaveBeenCalledWith("c", 1);
    expect(api.stop).not.toHaveBeenCalled();
    expect(result.current.selected).toBeNull();
  });

  it("keeps edits transient and sends once; deduplicates stream and Stop is explicit", async () => {
    const { result } = renderHook(() => useConversation(true));
    act(() => result.current.setDraft("Hel"));
    act(() => result.current.setDraft("Hello"));
    expect(api.send).not.toHaveBeenCalled();
    api.load.mockResolvedValue({ ...header, turns: [{ turnId: "t", input: "Hello", answer: null, state: "running" }] });
    await act(() => result.current.send());
    await waitFor(() => expect(api.stream).toHaveBeenCalled());
    const stream = api.stream.mock.results.at(-1)!.value as Stream;
    act(() => { stream.emit(1, "text_delta", { text: "Answer" }); stream.emit(1, "text_delta", { text: "Answer" }); });
    expect(result.current.liveText).toBe("Answer");
    act(() => result.current.setDraft("Next draft while responding"));
    await act(() => result.current.send());
    expect(api.send).toHaveBeenCalledTimes(1);
    await act(() => result.current.stop());
    expect(api.stop).toHaveBeenCalledWith("c", "t");
    api.load.mockResolvedValue({ ...header, turns: [{ turnId: "t", input: "Hello", answer: "Answer", state: "completed" }] });
    act(() => stream.emit(2, "terminal", { state: "completed" }));
    await waitFor(() => expect(result.current.running).toBeNull());
    expect(result.current.draft).toBe("Next draft while responding");
  });

  it("a dropped stream for a reply that already finished recovers instead of staying stuck", async () => {
    const { result } = renderHook(() => useConversation(true));
    act(() => result.current.setDraft("Hello"));
    api.load.mockResolvedValue({ ...header, turns: [{ turnId: "t", input: "Hello", answer: null, state: "running" }] });
    await act(() => result.current.send());
    await waitFor(() => expect(api.stream).toHaveBeenCalled());
    const stream = api.stream.mock.results.at(-1)!.value as Stream;
    api.turnStatus.mockResolvedValue({ conversationId: "c", turnId: "t", input: "Hello", historyVersion: 2, state: "completed" });
    api.load.mockResolvedValue({ ...header, turns: [{ turnId: "t", input: "Hello", answer: "Done", state: "completed" }] });
    act(() => stream.onerror?.());
    await waitFor(() => expect(result.current.running).toBeNull());
    expect(stream.closed).toBe(true);
    await waitFor(() => expect(result.current.turns[0].answer).toBe("Done"));
  });

  it("remembers the open chat across page flips and remounts; a vanished chat starts fresh", async () => {
    const first = renderHook(() => useConversation(true));
    act(() => first.result.current.select("c"));
    first.unmount();
    const again = renderHook(() => useConversation(true));
    expect(again.result.current.selected).toBe("c");
    again.unmount();
    api.load.mockRejectedValueOnce(new Error("Conversation unavailable."));
    const gone = renderHook(() => useConversation(true));
    await waitFor(() => expect(gone.result.current.selected).toBeNull());
    expect(gone.result.current.error).toBeNull();
    expect(sessionStorage.getItem("resono_vault_chat_selected")).toBeNull();
  });

  it("a transient network drop while loading is retried instead of shown as 'Load failed'", async () => {
    api.load.mockRejectedValueOnce(new TypeError("Load failed"))
      .mockResolvedValueOnce({ ...header, turns: [{ turnId: "t", input: "Hi", answer: "Hello", state: "completed" }] });
    const { result } = renderHook(() => useConversation(true));
    act(() => result.current.select("c"));
    await waitFor(() => expect(result.current.turns).toHaveLength(1), { timeout: 3000 });
    expect(result.current.error).toBeNull();
  });

  it("retries a lost acknowledgment using the exact original key and input", async () => {
    const { result } = renderHook(() => useConversation(true));
    act(() => result.current.setDraft("Hello"));
    api.send.mockRejectedValueOnce(new Error("Acknowledgment lost"));
    await act(() => result.current.send());
    const original = api.send.mock.calls[0];
    act(() => result.current.setDraft("Different unsent text"));
    await act(() => result.current.send());
    expect(api.send).toHaveBeenCalledTimes(1);
    await act(() => result.current.send(true));
    expect(api.send.mock.calls[1]).toEqual(original);
    expect(result.current.draft).toBe("Different unsent text");
  });

  it("rejects oversized UTF-8 drafts locally without creating a session", async () => {
    const { result } = renderHook(() => useConversation(true));
    act(() => result.current.setDraft("🙂".repeat(17000)));
    await act(() => result.current.send());
    expect(result.current.error).toContain("65536 UTF-8 bytes");
    expect(api.create).not.toHaveBeenCalled();
    expect(api.send).not.toHaveBeenCalled();
  });

  it("navigation closes viewing only and preserves draft; history never sends", async () => {
    const { result, rerender, unmount } = renderHook(({ active }) => useConversation(active), { initialProps: { active: true } });
    api.load.mockResolvedValue({ ...header, turns: [{ turnId: "t", input: "Old", answer: null, state: "running" }] });
    act(() => result.current.select("c"));
    await waitFor(() => expect(api.stream).toHaveBeenCalled());
    const stream = api.stream.mock.results.at(-1)!.value as Stream;
    act(() => result.current.setDraft("Transient draft"));
    rerender({ active: false });
    expect(stream.closed).toBe(true);
    expect(api.stop).not.toHaveBeenCalled();
    act(() => stream.emit(1, "text_delta", { text: "late" }));
    expect(result.current.liveText).toBe("");
    rerender({ active: true });
    expect(result.current.draft).toBe("Transient draft");
    expect(api.send).not.toHaveBeenCalled();
    unmount();
    expect((api.stream.mock.results.at(-1)!.value as Stream).closed).toBe(true);
  });

  it("a late history reply cannot replace another selected session", async () => {
    let finish: (value: unknown) => void = () => {};
    api.load.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const { result } = renderHook(() => useConversation(true));
    act(() => result.current.select("c"));
    await waitFor(() => expect(api.load).toHaveBeenCalled());
    act(() => result.current.select("other"));
    await act(async () => { finish({ ...header, turns: [{ turnId: "old", input: "PRIVATE OLD", answer: null, state: "completed" }] }); });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.selected).toBe("other");
    expect(result.current.turns).toEqual([]);
  });
});
