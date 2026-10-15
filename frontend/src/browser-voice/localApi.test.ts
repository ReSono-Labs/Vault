import { localApi } from "@/browser-voice/localApi";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("local Browser Voice API", () => {
  beforeEach(() => {
    document.cookie = "resono_csrf=csrf-proof; Path=/";
  });

  it("uses same-origin cookies and CSRF without browser token storage", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ safeMode: true }), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await localApi.safeMode(true);
    expect(fetchMock).toHaveBeenCalledWith("/extensions/safe-mode", expect.objectContaining({
      credentials: "same-origin",
      method: "POST",
    }));
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("X-ReSono-CSRF")).toBe("csrf-proof");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("loads extension grants without treating GET as a mutation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await localApi.extensionGrants("ext-1");
    expect(fetchMock).toHaveBeenCalledWith("/extensions/ext-1/grants", expect.objectContaining({
      credentials: "same-origin",
    }));
    expect(fetchMock.mock.calls[0][1].method ?? "GET").toBe("GET");
  });

  it("does not echo server errors as successful values", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: "Denied locally." } }), {
      status: 403, headers: { "Content-Type": "application/json" },
    })));
    await expect(localApi.me()).rejects.toThrow("Denied locally.");
  });

  it("sends transcript failure acknowledgment with the existing scoped close request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "closed" }), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await localApi.closeVoice("voice-1", { transcriptCaptureFailures: 2 });
    expect(fetchMock).toHaveBeenCalledWith("/voice/sessions/voice-1/close", expect.objectContaining({
      method: "POST", credentials: "same-origin", body: JSON.stringify({ transcriptCaptureFailures: 2 }),
    }));
    expect((fetchMock.mock.calls[0][1].headers as Headers).get("X-ReSono-CSRF")).toBe("csrf-proof");
  });

  it("captures original provider completion without inventing a transcript entry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ accepted: true }), {
      status: 201, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const value = { providerEventId: "event-1", eventType: "response.done", role: "assistant" as const,
      providerPayload: { type: "response.done", response: { id: "response-1", status: "completed", output: [] } } };
    await localApi.captureVoiceEvent("voice-1", value);
    expect(fetchMock).toHaveBeenCalledWith("/voice/sessions/voice-1/events", expect.objectContaining({
      method: "POST", body: JSON.stringify(value), credentials: "same-origin",
    }));
    expect(fetchMock.mock.calls[0][1].body).not.toContain("transcriptEntryIndex");
  });

  it("recovers a Voice tool call whose request was dropped by retrying the same toolCallId", async () => {
    const ok = { content: [{ type: "text", text: "done" }], isError: false };
    const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError("Load failed"))
      .mockResolvedValueOnce(json({ pending: true }, 202))
      .mockResolvedValueOnce(json(ok));
    vi.stubGlobal("fetch", fetchMock);
    const result = await localApi.callVoiceTool("voice", { name: "web_search", toolCallId: "call-1", arguments: { query: "x" } });
    expect(result).toEqual(ok);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(new Set(fetchMock.mock.calls.map(([, init]) => init.body)).size).toBe(1);
    fetchMock.mockReset().mockResolvedValueOnce(json({ error: { message: "Tool is not granted." } }, 403));
    await expect(localApi.callVoiceTool("voice", { name: "web_search", toolCallId: "call-2", arguments: {} }))
      .rejects.toThrow("Tool is not granted.");  // real HTTP errors are not retried
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
