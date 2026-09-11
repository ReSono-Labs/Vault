import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BrowserVoiceApp,
  voiceStartErrorMessage,
} from "@/browser-voice/BrowserVoiceApp";

function response(value: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(value), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("standalone Browser Voice shell", () => {
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
      await screen.findByRole("heading", { name: "Configure AI" }),
    ).toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "Agents" })).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "Agents" }));
    expect(await screen.findByText("No external agents are connected.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "External agents" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Agent2Agent" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Memory only/i)).not.toBeInTheDocument();
    const activitySummary = await screen.findByText("Finished the requested repository review.");
    fireEvent.click(activitySummary.closest("button")!);
    expect(await screen.findByRole("heading", { name: "OpenClaw" })).toBeInTheDocument();
    expect(screen.getByText("Background Agent")).toBeInTheDocument();
    expect(screen.getAllByText("Finished the requested repository review.")).toHaveLength(2);
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
    expect(screen.queryByRole("heading", { level: 3, name: "Vault Memory access" })).not.toBeInTheDocument();
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
    expect(await screen.findByRole("heading", { level: 2, name: "Vault Memory" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Vault Memory access" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Connection name")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add agent memory" }));
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
