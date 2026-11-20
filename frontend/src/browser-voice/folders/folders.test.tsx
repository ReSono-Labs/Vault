/// <reference types="vite/client" />
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsFoldersSection } from "@/browser-voice/folders/SettingsFoldersSection";

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

const projects = {
  folderId: "f1",
  name: "Projects",
  path: "local/Projects",
  location: "Documents/Projects",
  permission: "read",
  maxPermission: "write",
  createdByVault: false,
  status: "ok",
  statusMessage: null,
};

describe("Settings > Folders", () => {
  let folders: Array<typeof projects>;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute("open", "");
    };
    HTMLDialogElement.prototype.close = function () {
      this.removeAttribute("open");
    };
    folders = [];
    fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/folders") {
        if (init?.method === "POST") {
          folders.push(projects);
          return response(projects, 201);
        }
        return response({ available: true, hasAccess: true, folders });
      }
      if (path === "/folders/places")
        return response({ items: [{ grantId: "g1", label: "Documents", canWrite: true, status: "ok", statusMessage: null }] });
      if (path.startsWith("/folders/browse")) {
        const inner = new URL(path, "https://vault.local").searchParams.get("path") || "";
        return response({
          grantId: "g1",
          path: inner,
          breadcrumbs: inner
            ? [{ label: "Documents", path: "" }, { label: "Projects", path: "Projects" }]
            : [{ label: "Documents", path: "" }],
          directories: inner ? [] : [{ name: "Projects", path: "Projects" }],
          canCreate: true,
        });
      }
      if (path === "/folders/f1/remove") {
        folders = [];
        return response({ status: "removed" });
      }
      return response({ error: { message: "unexpected" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("adds a folder by clicking through to it", async () => {
    render(<SettingsFoldersSection />);
    expect(await screen.findByText("No folders yet. Click Add folder to choose one.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add folder" }));
    const list = await screen.findByRole("list", { name: "Folders" });
    fireEvent.click(await within(list).findByRole("button", { name: "Projects" }));
    await screen.findByRole("button", { name: "Projects", current: true });
    fireEvent.click(screen.getByRole("button", { name: "Choose this folder" }));
    expect(await screen.findByLabelText("Name")).toHaveValue("Projects");
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText(/Projects was added/)).toBeInTheDocument();
    const addCall = fetchMock.mock.calls.find(([path, init]) => String(path) === "/folders" && init?.method === "POST");
    expect(JSON.parse(String(addCall?.[1]?.body))).toEqual({
      grantId: "g1",
      path: "Projects",
      name: "Projects",
      permission: "read",
    });
  });

  it("removes a folder after a confirmation that the files stay", async () => {
    folders = [projects];
    render(<SettingsFoldersSection />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(screen.getByText(/The files stay on your computer/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText(/The files are still on your computer/)).toBeInTheDocument();
  });

  it("tells people without access to ask their admin", async () => {
    fetchMock.mockImplementation(() => response({ available: true, hasAccess: false, canAddAnywhere: false, folders: [] }));
    render(<SettingsFoldersSection />);
    expect(await screen.findByText(/hasn't shared any folders with you yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add folder" })).toBeDisabled();
  });

  it("is hidden when folders aren't set up on this computer", async () => {
    fetchMock.mockImplementation(() => response({ available: false, hasAccess: false, folders: [] }));
    const { container } = render(<SettingsFoldersSection />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});

describe("folder wording", () => {
  it("never shows technical words to people", () => {
    const sources = import.meta.glob<string>(["./*.tsx", "!./*.test.tsx"], { query: "?raw", import: "default", eager: true });
    expect(Object.keys(sources).length).toBeGreaterThan(5);
    const banned = /\b(mount|mounts|grant|grants|host path|bind)\b|\/host\//i;
    for (const [name, text] of Object.entries(sources)) {
      const visible = [...text.matchAll(/>([^<>{}]+)</g), ...text.matchAll(/"([^"]*\s[^"]*)"/g), ...text.matchAll(/`([^`]*\s[^`]*)`/g)]
        .map((match) => match[1])
        .filter((value) => !/^[\w-]+(\s[\w-]+)*$/.test(value) || /\s/.test(value))
        .filter((value) => !value.includes("browser-voice-"));
      for (const value of visible) expect(value, `${name}: ${value}`).not.toMatch(banned);
    }
  });
});

describe("Settings > Folders for the master account", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("browses everything Vault can see and adds the folder directly", async () => {
    HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute("open", "");
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/folders") return response({ available: true, hasAccess: true, canAddAnywhere: true, folders: [] });
      if (path === "/admin/folders/locations")
        return response({
          available: true,
          locations: [{ locationId: "home", label: "Home", kind: "home", status: "ok", statusMessage: null }],
          places: [{ label: "Home", locationId: "home", path: "", kind: "home" }],
        });
      if (path.startsWith("/admin/folders/browse"))
        return response({ locationId: "home", path: "", breadcrumbs: [{ label: "Home", path: "" }], directories: [], canCreate: true });
      if (path === "/admin/folders/add" && init?.method === "POST")
        return response({ folderId: "f", name: "Home", path: "local/Home" }, 201);
      return response({ error: { message: "unexpected" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<SettingsFoldersSection />);
    expect(screen.queryByText(/hasn't shared any folders/)).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Add folder" }));
    fireEvent.click(await screen.findByRole("button", { name: "Choose this folder" }));
    fireEvent.click(await screen.findByRole("button", { name: "Add" }));
    expect(await screen.findByText(/Home was added/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([path]) => String(path) === "/folders/places")).toBe(false);
  });
});

describe("hidden files switch", () => {
  afterEach(() => vi.unstubAllGlobals());

  function folder(overrides: Record<string, unknown>) {
    return {
      folderId: "f1", name: "Code", path: "local/Code", location: "Documents/Code", permission: "write",
      maxPermission: "write", createdByVault: true, includeHidden: false, hiddenFromAccess: false,
      canChangeHidden: true, status: "ok", statusMessage: null, ...overrides,
    };
  }

  it("lets people switch it on for a folder they made", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path === "/folders") return response({ available: true, hasAccess: true, canAddAnywhere: false, folders: [folder({})] });
      if (path === "/folders/f1/hidden") return response(folder({ includeHidden: true }));
      return response({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<SettingsFoldersSection />);
    fireEvent.click(await screen.findByRole("button", { name: /Code: hidden files hidden/ }));
    expect(await screen.findByText("Hidden files are now shown in Code.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([path]) => String(path) === "/folders/f1/hidden");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ includeHidden: true });
  });

  it("is locked on folders they didn't make", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({
      available: true, hasAccess: true, canAddAnywhere: false,
      folders: [folder({ createdByVault: false, canChangeHidden: false })],
    })));
    render(<SettingsFoldersSection />);
    expect(await screen.findByRole("button", { name: /Code: hidden files hidden/ })).toBeDisabled();
  });
});
