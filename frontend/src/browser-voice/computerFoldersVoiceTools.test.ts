import { describe, expect, it } from "vitest";
import { shouldFulfillBrowserLocalVoiceTool } from "@/browser-voice/computerFoldersVoiceTools";
import type { HostFilesystemMount } from "@/browser-voice/localApi";

const browserMount: HostFilesystemMount = {
  mountId: "m1",
  mountName: "Documents",
  mountPath: "local/Documents",
  permission: "read",
  source: "browser",
  status: "active",
  createdAt: "2026-09-11T00:00:00Z",
};

const helperMount: HostFilesystemMount = {
  ...browserMount,
  mountId: "m2",
  mountName: "Projects",
  mountPath: "local/Projects",
  source: "helper",
};

describe("browser-local Voice workspace tools", () => {
  it("fulfills nested list and read for whatever mount is currently linked", () => {
    const taxMount: HostFilesystemMount = { ...browserMount, mountName: "Tax-2024", mountPath: "local/Tax-2024" };
    expect(
      shouldFulfillBrowserLocalVoiceTool(
        "workspace_list_directory",
        { path: "local/Tax-2024/invoices/q1" },
        [taxMount],
      ),
    ).toBe(true);
    expect(
      shouldFulfillBrowserLocalVoiceTool(
        "workspace_read_file",
        { fileKey: "local/Tax-2024/notes.md" },
        [taxMount],
      ),
    ).toBe(true);
  });

  it("does not intercept helper mounts, vault paths, or shared paths", () => {
    expect(
      shouldFulfillBrowserLocalVoiceTool(
        "workspace_list_directory",
        { directory: "local/Projects" },
        [helperMount],
      ),
    ).toBe(false);
    expect(
      shouldFulfillBrowserLocalVoiceTool(
        "workspace_list_directory",
        { directory: "notes" },
        [browserMount],
      ),
    ).toBe(false);
    expect(
      shouldFulfillBrowserLocalVoiceTool(
        "workspace_list_directory",
        { directory: "shared/alice/Reports" },
        [browserMount],
      ),
    ).toBe(false);
    expect(
      shouldFulfillBrowserLocalVoiceTool(
        "workspace_search_files",
        { query: "invoice", directory: "shared/alice/Reports" },
        [browserMount],
      ),
    ).toBe(false);
  });
});
