import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BrowserVoiceApp } from "@/browser-voice/BrowserVoiceApp";
import { voiceStartErrorMessage, countFailedTranscriptWrites } from "@/browser-voice/useVoiceSession";

function response(value: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(value), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("standalone Browser Voice shell", () => {
  it("counts failed transcript writes after every queued capture settles", async () => {
    let finish: (() => void) | undefined;
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    let settled = false;
    const result = countFailedTranscriptWrites([pending, Promise.reject(new Error("capture failed")), Promise.resolve()])
      .then((count) => { settled = true; return count; });
    await Promise.resolve();
    expect(settled).toBe(false);
    finish!();
    expect(await result).toBe(1);
    expect(await countFailedTranscriptWrites([])).toBe(0);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
    window.history.replaceState({}, "", "/");
  });

  it("uses the server-validated bootstrap proof instead of a stale setup fragment", async () => {
    window.history.replaceState({}, "", "/browser-voice.html?setup=fresh&bootstrap=current-credential#setup=stale-reset-credential");
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      if (String(input) === "/identity/status") return response({ setupComplete: false });
      if (String(input) === "/identity/setup-session") return response({ status: "ready" });
      return response({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<BrowserVoiceApp />);

    expect(await screen.findByRole("heading", { name: "Meet your Vault" })).toBeInTheDocument();
    const setupCall = fetchMock.mock.calls.find(([path]) => String(path) === "/identity/setup-session");
    expect(JSON.parse(String(setupCall?.[1]?.body))).toEqual({ setupCredential: "current-credential" });
    expect(screen.queryByText("Setup credential is invalid.")).not.toBeInTheDocument();
  });

  it("translates browser microphone device failures into useful Voice guidance", () => {
    expect(
      voiceStartErrorMessage(
        new DOMException("Requested device not found", "NotFoundError"),
      ),
    ).toBe(
      "No microphone was found. Connect or enable a microphone, then try again.",
    );
    expect(
      voiceStartErrorMessage(
        new DOMException("Permission denied", "NotAllowedError"),
      ),
    ).toBe(
      "Microphone access is blocked. Allow microphone access for Vault, then try again.",
    );
    expect(
      voiceStartErrorMessage({
        name: "NotFoundError",
        message: "Requested device not found",
      }),
    ).toBe(
      "No microphone was found. Connect or enable a microphone, then try again.",
    );
  });

  it("a temporary-password user can set a new password from a fresh tab (DEF-03)", async () => {
    sessionStorage.clear();
    const calls: { path: string; body?: string }[] = [];
    const user = { userId: "u2", username: "kid", displayName: "Kid", experienceStyle: "warm", isDeviceOwner: false,
      activeWorkspaceId: "w", passwordMode: "temporary", mustChangePassword: true, ageGroup: "adult" };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      calls.push({ path, body: init?.body as string | undefined });
      if (path === "/identity/status") return response({ setupComplete: true });
      if (path === "/me") return response({ user });
      if (path === "/identity/password") return response({ status: "changed" });
      return response({}, 404);
    }));
    render(<BrowserVoiceApp />);
    const button = await screen.findByRole("button", { name: "Set password" });
    expect(button).not.toBeDisabled();
    fireEvent.change(screen.getByLabelText("Temporary password"), { target: { value: "temp-password-1" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "new-password-123" } });
    fireEvent.click(button);
    await waitFor(() => expect(calls.some((call) => call.path === "/identity/password")).toBe(true));
    const sent = JSON.parse(calls.find((call) => call.path === "/identity/password")!.body!);
    expect(sent).toEqual({ currentPassword: "temp-password-1", newPassword: "new-password-123" });
  });

  it("first run asks for the master name once before the personalized experience step", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => response({ setupComplete: false })),
    );
    render(<BrowserVoiceApp />);
    expect(
      await screen.findByRole("heading", { name: "Meet your Vault" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Your name")).toBeInTheDocument();
    expect(screen.queryByLabelText("Experience")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Username")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    expect(screen.queryByText(/verification code/i)).not.toBeInTheDocument();
  });

  it("offers optional age-classified secondary accounts after master recovery", async () => {
    window.history.replaceState({}, "", "/#setup=local-setup");
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/identity/status")
        return response({ setupComplete: false });
      if (path === "/identity/setup-session")
        return response({ status: "ready" });
      if (path === "/identity/register")
        return response(
          {
            user: {
              userId: "u",
              username: "owner",
              displayName: "Owner",
              experienceStyle: "warm",
              isDeviceOwner: true,
              activeWorkspaceId: "w",
              passwordMode: "user_managed",
              mustChangePassword: false,
              ageGroup: "adult",
            },
          },
          201,
        );
      if (path === "/local-users")
        return response(
          {
            userId: "u2",
            workspaceId: "w2",
            passwordMode: "setup_link",
            setupCredential: "secondary-setup",
          },
          201,
        );
      if (path === "/admin/folders/locations")
        return response({
          available: true,
          locations: [{ locationId: "home", label: "Home", kind: "home", status: "ok", statusMessage: null }],
          places: [{ label: "Home", locationId: "home", path: "", kind: "home" }],
        });
      if (path === "/folders/setup/vault-folder")
        return response({ folderId: "f", name: "ReSono Vault", path: "local/ReSono Vault" });
      if (path === "/providers/openai")
        return response({
          providerKey: "openai",
          configured: true,
          modelKey: "gpt-realtime",
          backgroundModelKey: "gpt-5.6-sol",
          voice: "alloy",
          updatedAt: "2026-08-29T00:00:00Z",
        });
      if (path === "/me")
        return response({
          user: {
            userId: "u",
            username: "owner",
            displayName: "Owner",
            experienceStyle: "warm",
            isDeviceOwner: true,
            activeWorkspaceId: "w",
            passwordMode: "user_managed",
            mustChangePassword: false,
            ageGroup: "adult",
          },
        });
      return response({ init }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<BrowserVoiceApp />);
    fireEvent.change(await screen.findByLabelText("Your name"), {
      target: { value: "Owner" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Hello, Owner" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Make it yours" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Warm/ }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Secure your Vault" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "owner-password" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "owner-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", { name: "Add people to your Vault" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add users now" }));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Teen" },
    });
    fireEvent.change(screen.getByLabelText("Username"), {
      target: { value: "teen" },
    });
    fireEvent.change(screen.getByLabelText("Age group"), {
      target: { value: "under_18" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));
    await screen.findByText(/one-time setup link/i);
    const createCall = fetchMock.mock.calls.find(
      ([path]) => String(path) === "/local-users",
    );
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      ageGroup: "under_18",
      passwordMode: "setup_link",
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", { name: "Choose folders for your agents" }),
    ).toBeInTheDocument();
    expect(await screen.findByLabelText(/Create my ReSono Vault folder in Documents/)).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", { name: "Configure AI" }),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([path]) => String(path) === "/folders/setup/vault-folder"),
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Connect and share provider" }));
    fireEvent.change(screen.getByLabelText("OpenAI API key"), {
      target: { value: "sk-local-test" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save AI configuration" }),
    );
    await screen.findByText("AI configuration saved locally.");
    const providerCall = fetchMock.mock.calls.find(
      ([path]) => String(path) === "/providers/openai",
    );
    expect(JSON.parse(String(providerCall?.[1]?.body))).toMatchObject({
      apiKey: "sk-local-test",
      modelKey: "gpt-realtime-2.1",
      backgroundModelKey: "gpt-5.6-sol",
      voice: "alloy",
    });
  });

  it("authenticated navigation exposes capabilities and a dedicated Agent2Agent page", async () => {
    const user = {
      userId: "u",
      username: "owner",
      displayName: "Local Owner",
      experienceStyle: "funny",
      isDeviceOwner: true,
      activeWorkspaceId: "w",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/identity/status")
          return response({ setupComplete: true });
        if (path === "/me") return response({ user });
        if (path === "/extensions") return response({ items: [] });
        if (path === "/agent2agent/notifications") return response({ items: [{
          taskId: "task-1", agentName: "OpenClaw", state: "completed",
          summary: "Finished the requested repository review.", issue: null,
          ownerKind: "background", createdAt: "2026-08-31T12:00:00Z",
          updatedAt: "2026-08-31T12:01:00Z", completedAt: "2026-08-31T12:01:00Z",
        }] });
        if (path === "/builtin-plugins") return response({ items: [{
          key: "agent2agent", name: "Agent2Agent",
          description: "Let Voice and the Background Agent talk to other A2A agents.",
          enabled: false, builtIn: true, canDelete: false, configuration: {}, updatedAt: null,
        }] });
        if (path === "/background/work") return response({ items: [
          { workId: "w-active", state: "running", statusLabel: "running", intentVersion: 1, objective: "Summarize the notes. Then file them.",
            workerId: null, workerGeneration: null, roleKey: "notes-helper", taskId: null, task: null, pendingActionId: null, result: null,
            createdAt: "2026-11-19T12:00:00Z", updatedAt: "2026-11-19T12:00:05Z", startedAt: "2026-11-19T12:00:01Z", activeSeconds: 74,
            runId: "run-w1", failureCode: null, completedAt: null, modelTurns: 1, toolCalls: 2 },
          { workId: "w-old", state: "unknown", statusLabel: "unknown", intentVersion: 1, objective: "Refresh the UAP watch cards.",
            workerId: null, workerGeneration: null, roleKey: "uap_daily_watch", taskId: null, task: null, pendingActionId: null, result: null,
            createdAt: "2026-11-19T08:00:00Z", updatedAt: "2026-11-19T08:01:34Z", startedAt: "2026-11-19T08:00:04Z", activeSeconds: 0,
            runId: "run-w2", failureCode: "stalled_outcome_unknown", completedAt: null, modelTurns: 0, toolCalls: 0 },
        ] });
        if (path === "/background/work/w-old") return response({
          workId: "w-old", state: "unknown", statusLabel: "unknown", intentVersion: 1, objective: "Refresh the UAP watch cards.",
          workerId: null, workerGeneration: null, roleKey: "uap_daily_watch", taskId: null, task: null, pendingActionId: null, result: null,
          createdAt: "2026-11-19T08:00:00Z", updatedAt: "2026-11-19T08:01:34Z", startedAt: "2026-11-19T08:00:04Z", activeSeconds: 0,
          runId: "run-w2", failureCode: "stalled_outcome_unknown", completedAt: null, modelTurns: 0, toolCalls: 0,
          brief: { objective: "Refresh the UAP watch cards.", successCriteria: [], expectedResult: null, contextSummary: null },
          reasoningEntries: [] });
        if (path === "/background/runs") return response({ items: [{
          runId: "run-1", objective: "Summarize the notes", state: "running",
          invocationType: "voice_goal", originId: "session-1",
          cancellationRequested: false, output: null, failure: null, failureCode: null,
          failureMessage: null, failureExplanation: null,
          modelTurns: 1, toolCalls: 2, createdAt: "2026-09-15T12:00:00Z",
          updatedAt: "2026-09-15T12:00:01Z", completedAt: null, reasoningEntries: [],
          progress: {
            label: "Working and checking the result", fraction: 0.52, active: true, tone: "active",
            activity: "Queued for the Background Agent", modelTurns: 1, toolCalls: 2, timeline: [],
          },
        }] });
        return response({ items: [] });
      }),
    );
    render(<BrowserVoiceApp />);
    expect(
      await screen.findByRole("heading", { name: "Voice" }),
    ).toBeInTheDocument();
    expect(screen.getByText("SESSION: IDLE")).toBeInTheDocument();
    expect(
      screen.getByText("Press to start a voice session"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Transcript")).not.toBeInTheDocument();
    expect(screen.queryByText("0 entries")).not.toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Library" }).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "External agents" }).length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: "Devices" }),
    ).not.toBeInTheDocument();
    document.documentElement.scrollTop = 640;
    document.body.scrollTop = 640;
    fireEvent.click(screen.getAllByRole("button", { name: "Library" })[0]);
    expect(
      await screen.findByRole("heading", { level: 2, name: "Agent capabilities" }),
    ).toBeInTheDocument();
    expect(document.documentElement.scrollTop).toBe(0);
    expect(document.body.scrollTop).toBe(0);
    expect(screen.queryByText("Foundry")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Plugin" }));
    expect((await screen.findAllByText(/Built into Vault/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Plugins" })).toBeInTheDocument();
    expect(screen.getByText("Let Voice and the Background Agent talk to other A2A agents.")).toBeInTheDocument();
    expect(screen.queryByText("Collab")).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "External agents" })[0]);
    expect(screen.getByRole("button", { name: "Connect agent" })).toBeDisabled();
    expect(screen.getByText(/Turn on Agent2Agent under Library/)).toBeInTheDocument();
    expect(screen.queryByText("Inbound Agent Card")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "External agents" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Agent2Agent" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Memory only/i)).not.toBeInTheDocument();
    const activitySummary = await screen.findByText("Finished the requested repository review.");
    fireEvent.click(activitySummary.closest("button")!);
    expect(await screen.findByRole("heading", { name: "OpenClaw" })).toBeInTheDocument();
    expect(screen.getAllByText("Background Agent").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Finished the requested repository review.")).toHaveLength(2);
    fireEvent.click(screen.getAllByRole("button", { name: "Background work" })[0]);
    expect(await screen.findByRole("heading", { level: 2, name: "Background work" })).toBeInTheDocument();
    const activeSection = await screen.findByRole("region", { name: "Active" });
    expect(within(activeSection).getByRole("button", { name: "Open Summarize the notes." })).toBeInTheDocument();
    expect(within(activeSection).getByRole("button", { name: "Stop" })).toBeInTheDocument();
    const historySection = screen.getByRole("region", { name: "History" });
    expect(within(historySection).getByText("Outcome not confirmed")).toBeInTheDocument();
    expect(within(historySection).queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
    // The run that predates coordinated work stays readable under Earlier runs.
    expect(screen.getByText(/Earlier runs from this session/)).toBeInTheDocument();
    fireEvent.click(within(historySection).getByRole("button", { name: "Open Refresh the UAP watch cards." }));
    expect(await screen.findByRole("heading", { level: 2, name: "Refresh the UAP watch cards." })).toBeInTheDocument();
    expect(screen.getByText(/Vault lost track of this run before it finished/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop run" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "← Background work" }));
    expect(await screen.findByRole("region", { name: "History" })).toBeInTheDocument();
  });

  it("shows this Vault inbound card when Agent2Agent is on", async () => {
    const user = {
      userId: "u",
      username: "owner",
      displayName: "Local Owner",
      experienceStyle: "funny",
      isDeviceOwner: true,
      activeWorkspaceId: "w",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/identity/status") return response({ setupComplete: true });
        if (path === "/me") return response({ user });
        if (path === "/builtin-plugins") return response({ items: [{
          key: "agent2agent", name: "Agent2Agent",
          description: "Let Voice and the Background Agent talk to other A2A agents.",
          enabled: true, builtIn: true, canDelete: false, configuration: {}, updatedAt: null,
        }] });
        if (path === "/agent2agent/listen") return response({
          cardUrl: "http://127.0.0.1:8768/.well-known/agent-card.json",
          rpcUrl: "http://127.0.0.1:8768/",
          tokenHint: "cret",
        });
        if (path === "/agent2agent/listen/token") return response({ token: "inbound-secret" });
        if (path === "/agent2agent/listen/rotate") return response({
          cardUrl: "http://127.0.0.1:8768/.well-known/agent-card.json", rpcUrl: "http://127.0.0.1:8768/", tokenHint: "wxyz",
        });
        if (path === "/agent2agent/notifications") return response({ items: [] });
        return response({ items: [] });
      }),
    );
    render(<BrowserVoiceApp />);
    await screen.findByRole("heading", { name: "Voice" });
    fireEvent.click(screen.getAllByRole("button", { name: "External agents" })[0]);
    expect(await screen.findByRole("heading", { name: "Inbound Agent Card" })).toBeInTheDocument();
    expect(screen.getByText("http://127.0.0.1:8768/.well-known/agent-card.json")).toBeInTheDocument();
    // Hidden by default; the bearer is fetched only when asked for.
    expect(screen.getByLabelText("Inbound bearer, hidden")).toHaveTextContent(/•+cret$/);
    expect(screen.queryByText("inbound-secret")).not.toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input) === "/agent2agent/listen/token")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(await screen.findByText("inbound-secret")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByText("inbound-secret")).not.toBeInTheDocument();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(await screen.findByText("Copied")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith("inbound-secret");
    expect(screen.queryByText("inbound-secret")).not.toBeInTheDocument();
    // Make new token: confirm first, then only the new hint comes back.
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    fireEvent.click(screen.getByRole("button", { name: "Make new token" }));
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input) === "/agent2agent/listen/rotate")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Make new token" }));
    expect(await screen.findByText("New token made")).toBeInTheDocument();
    expect(screen.getByLabelText("Inbound bearer, hidden")).toHaveTextContent(/•+wxyz$/);
    confirm.mockRestore();
    expect(screen.getByRole("button", { name: "Connect agent" })).toBeEnabled();
    expect(screen.queryByText("Agent2Agent Collab")).not.toBeInTheDocument();
  });

  it("lets the owner switch between OAuth and the saved API key without disconnecting either", async () => {
    const user = { userId: "u", username: "owner", displayName: "Local Owner", experienceStyle: "strict",
      isDeviceOwner: true, activeWorkspaceId: "w" };
    const openai = { providerKey: "openai", configured: true, modelKey: "gpt-realtime-2.1-mini",
      backgroundModelKey: "gpt-5.6-luna", voice: "marin", updatedAt: null, selected: true,
      authMethod: "chatgpt_oauth", apiKeyConnected: true, oauthConnected: true };
    const posts: { path: string; body: string }[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (init?.method === "POST") posts.push({ path, body: String(init.body) });
      if (path === "/identity/status") return response({ setupComplete: true });
      if (path === "/me") return response({ user });
      if (path === "/extensions") return response({ items: [] });
      if (path === "/extensions/runtime") return response({ safeMode: true });
      if (path === "/providers/openai") return response(openai);
      if (path === "/providers/openai/auth-method") return response({ ...openai, authMethod: "api_key" });
      return response({}, 404);
    }));
    render(<BrowserVoiceApp />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Connections" }))[0]);
    expect(await screen.findByText(/An API key saved here is used for live transcription and Web search/)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Use API key" }));
    expect(await screen.findByRole("button", { name: "Use OAuth" })).toBeInTheDocument();
    expect(posts).toContainEqual({ path: "/providers/openai/auth-method", body: JSON.stringify({ authMethod: "api_key" }) });
    expect(screen.getByRole("button", { name: "Disconnect OAuth" })).toBeInTheDocument();
  });

  it("keeps Voice model a dropdown after saving provider settings", async () => {
    const user = { userId: "u", username: "owner", displayName: "Local Owner", experienceStyle: "strict",
      isDeviceOwner: true, activeWorkspaceId: "w" };
    const status = { providerKey: "openai", configured: true, modelKey: "gpt-realtime-2.1", backgroundModelKey: "gpt-5.6-luna",
      voice: "marin", updatedAt: null, authMethod: "api_key", apiKeyConnected: true, oauthConnected: false };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/identity/status") return response({ setupComplete: true });
      if (path === "/me") return response({ user });
      if (path === "/extensions") return response({ items: [] });
      if (path === "/extensions/runtime") return response({ safeMode: true });
      if (path === "/providers/catalog") return response({ selectedProviderKey: "openai", items: [{ ...status,
        displayName: "OpenAI", selected: true, voiceModels: ["gpt-realtime-2.1", "gpt-realtime-2.1-mini"], textModels: ["gpt-5.6-luna"] }] });
      // The save reply carries status only, with no model lists.
      if (path === "/providers/openai" && init?.method === "POST") return response({ ...status, modelKey: "gpt-realtime-2.1-mini" });
      return response({}, 404);
    }));
    render(<BrowserVoiceApp />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Connections" }))[0]);
    const field = await screen.findByRole("combobox", { name: "Voice model" });
    fireEvent.change(field, { target: { value: "gpt-realtime-2.1-mini" } });
    fireEvent.change(screen.getByLabelText("OpenAI API key"), { target: { value: "sk-test" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(screen.getByLabelText("OpenAI API key")).toHaveValue(""));
    const after = screen.getByRole("combobox", { name: "Voice model" });
    expect(after.tagName).toBe("SELECT");
    expect(after).toHaveValue("gpt-realtime-2.1-mini");
    expect(screen.queryByRole("textbox", { name: "Voice model" })).not.toBeInTheDocument();
  });

  it("connections exposes Voice infrastructure, agent memory, Mail, Calendar, and modular MCP", async () => {
    const user = {
      userId: "u",
      username: "owner",
      displayName: "Local Owner",
      experienceStyle: "strict",
      isDeviceOwner: true,
      activeWorkspaceId: "w",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/identity/status")
          return response({ setupComplete: true });
        if (path === "/me") return response({ user });
        if (path === "/extensions") return response({ items: [] });
        if (path === "/extensions/runtime") return response({ safeMode: true });
        if (path === "/providers/openai")
          return response({
            providerKey: "openai",
            configured: false,
            modelKey: "gpt-realtime",
            backgroundModelKey: "gpt-5.6-sol",
            voice: "alloy",
            updatedAt: null,
          });
        if (path === "/mail/accounts")
          return response({
            items: [
              {
                mailboxAccountId: "mail-1",
                mailboxRole: "normal_email",
                emailAddress: "owner@example.test",
                displayName: "Personal mail",
                lifecycleStatus: "active",
                syncEnabled: true,
                syncStatus: "complete",
              },
              {
                mailboxAccountId: "mail-2",
                mailboxRole: "normal_email",
                emailAddress: "work@example.test",
                displayName: "Work mail",
                lifecycleStatus: "active",
                syncEnabled: true,
                syncStatus: "complete",
              },
            ],
          });
        if (path === "/calendar/accounts")
          return response({
            items: [
              {
                calendarAccountId: "calendar-1",
                providerType: "ics",
                displayName: "Family",
                configuration: { feedUrl: "https://example.test/family.ics" },
                status: "active",
                sync: {},
                updatedAt: "2026-08-29T00:00:00Z",
              },
            ],
          });
        if (path === "/external-memory/integrations")
          return response({ items: [] });
        return response({}, 404);
      }),
    );
    render(<BrowserVoiceApp />);
    fireEvent.click(
      (await screen.findAllByRole("button", { name: "Connections" }))[0],
    );
    expect(await screen.findByRole("tab", { name: "AI & Voice", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Provider settings" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3, name: "Mail accounts" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Mail" }));
    expect(
      await screen.findByRole("heading", { level: 3, name: "Mail accounts" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Personal mail")).toBeInTheDocument();
    expect(screen.getByText(/owner@example\.test/)).toBeInTheDocument();
    expect(screen.getByText("Work mail")).toBeInTheDocument();
    expect(screen.getByText(/work@example\.test/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3, name: "Agent access" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add mail account" }));
    expect(
      screen.getByRole("dialog", { name: "Add mail account" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Incoming mail server")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close mail dialog" }));
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));
    expect(screen.getByRole("heading", { level: 3, name: "Calendar accounts" })).toBeInTheDocument();
    expect(screen.getByText("Family")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add calendar" }));
    expect(
      screen.getByRole("dialog", { name: "Add calendar" }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("ICS feed address"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Connection type"), {
      target: { value: "caldav" },
    });
    expect(screen.getByLabelText("CalDAV calendar address")).toBeInTheDocument();
    fireEvent.click((await screen.findAllByRole("button", { name: "Memory" }))[0]);
    expect(await screen.findByRole("heading", { level: 2, name: "Memory" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Agent access" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Connection name")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Connect agent to memory" }));
    expect(screen.getByLabelText("Connection name")).toBeInTheDocument();
    expect(screen.getByText(/automatically accepted until you revoke access/)).toBeInTheDocument();
    for (const excluded of [
      /external ai/i,
      /social posts/i,
      /recipes/i,
      /local events/i,
    ]) {
      expect(screen.queryByText(excluded)).not.toBeInTheDocument();
    }
  });

  it("device owner can manage four-user setup and change the local password", async () => {
    const user = {
      userId: "u",
      username: "owner",
      displayName: "Local Owner",
      experienceStyle: "strict",
      isDeviceOwner: true,
      activeWorkspaceId: "w",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/identity/status")
          return response({ setupComplete: true });
        if (path === "/me") return response({ user });
        if (path === "/workspaces")
          return response({
            items: [
              {
                workspaceId: "w",
                displayName: "Owner's Vault",
                ownerUserId: "u",
                membershipType: "owner",
              },
            ],
          });
        if (path === "/local-users")
          return response({
            items: [
              { ...user, status: "active", createdAt: "2026-08-29T00:00:00Z" },
              {
                ...user,
                userId: "u2",
                username: "second",
                displayName: "Second",
                isDeviceOwner: false,
                status: "active",
                createdAt: "2026-08-29T00:00:01Z",
              },
            ],
          });
        if (path === "/providers/openai/users/u2")
          return response({ userId: "u2", accessMode: "shared", sharedConfigured: true, individualConfigured: false });
        return response({});
      }),
    );
    render(<BrowserVoiceApp />);
    fireEvent.click(
      (await screen.findAllByRole("button", { name: "Account" }))[0],
    );
    expect(
      await screen.findByRole("heading", { level: 3, name: "Password" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: "Local users" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Change password" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add user" }));
    expect(screen.getByRole("button", { name: "Create local user" })).toBeInTheDocument();
    expect(screen.getByText("2 of 4 accounts configured.")).toBeInTheDocument();
    expect(screen.getAllByText(/Master account/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /Second/ }));
    expect(
      await screen.findByRole("button", { name: "Reset password" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(screen.getByLabelText("New password for Second")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete account" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Second/ }));
    expect(screen.queryByRole("button", { name: "Delete account" })).not.toBeInTheDocument();
    expect(screen.getByText("Select an account to manage access.")).toBeInTheDocument();
  });
});
