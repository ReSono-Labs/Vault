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

  it("does not echo server errors as successful values", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: "Denied locally." } }), {
      status: 403, headers: { "Content-Type": "application/json" },
    })));
    await expect(localApi.me()).rejects.toThrow("Denied locally.");
  });
});
