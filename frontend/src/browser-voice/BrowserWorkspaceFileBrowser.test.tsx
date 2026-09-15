import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BrowserWorkspaceFileBrowser } from "@/browser-voice/BrowserWorkspaceFileBrowser";
import { localApi } from "@/browser-voice/localApi";

vi.mock("@/browser-voice/localApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/browser-voice/localApi")>();
  return {
    ...actual,
    localApi: {
      ...actual.localApi,
      deleteWorkspacePath: vi.fn(),
      listWorkspaceFiles: vi.fn(),
      readWorkspaceFile: vi.fn(),
      hostFilesystemMounts: vi.fn(),
      localUsers: vi.fn(),
      listWorkspaceShares: vi.fn(),
    },
  };
});

describe("BrowserWorkspaceFileBrowser", () => {
  beforeEach(() => {
    vi.mocked(localApi.listWorkspaceFiles).mockReset();
    vi.mocked(localApi.deleteWorkspacePath).mockReset();
    vi.mocked(localApi.readWorkspaceFile).mockReset();
    vi.mocked(localApi.hostFilesystemMounts).mockReset();
    vi.mocked(localApi.hostFilesystemMounts).mockResolvedValue({ items: [] });
    vi.mocked(localApi.listWorkspaceFiles).mockResolvedValue({
      currentDirectory: "",
      parentDirectory: null,
      entries: [],
    });
  });

  it("loads workspace files when expanded", async () => {
    render(<BrowserWorkspaceFileBrowser initiallyExpanded />);
    await waitFor(() => expect(localApi.listWorkspaceFiles).toHaveBeenCalledTimes(1));
    expect(localApi.listWorkspaceFiles).toHaveBeenCalledWith(null);
  });

  it("opens a row directly and reveals confirmed delete only after a left swipe", async () => {
    vi.mocked(localApi.listWorkspaceFiles).mockResolvedValue({
      currentDirectory: "",
      parentDirectory: null,
      entries: [
        {
          kind: "file",
          name: "notes.md",
          path: "notes.md",
          sizeBytes: 12,
          childCount: null,
          mimeType: "text/markdown",
          editable: true,
          projectionVersion: 3,
          updatedAt: "2026-08-10T12:00:00Z",
        },
      ],
    });
    vi.mocked(localApi.readWorkspaceFile).mockResolvedValue({
      fileKey: "notes.md",
      filename: "notes.md",
      contentMarkdown: "hello",
      sizeBytes: 12,
      mimeType: "text/markdown",
      editable: true,
      projectionVersion: 3,
      updatedAt: "2026-08-10T12:00:00Z",
    });
    vi.mocked(localApi.deleteWorkspacePath).mockResolvedValue({
      status: "ok",
      message: "Deleted.",
      affectedCount: 1,
      path: "notes.md",
      destinationPath: null,
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<BrowserWorkspaceFileBrowser initiallyExpanded />);
    let row = await screen.findByRole("button", { name: "Open file notes.md" });
    fireEvent.click(row);
    await waitFor(() => expect(localApi.readWorkspaceFile).toHaveBeenCalledWith("notes.md"));

    row = screen.getByRole("button", { name: "Open file notes.md" });
    fireEvent.pointerDown(row, { clientX: 160, clientY: 20, pointerId: 1 });
    fireEvent.pointerMove(row, { clientX: 90, clientY: 22, pointerId: 1 });
    fireEvent.pointerUp(row, { clientX: 90, clientY: 22, pointerId: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(confirm).toHaveBeenCalledWith('Delete file "notes.md"?');
    await waitFor(() => expect(localApi.deleteWorkspacePath).toHaveBeenCalledWith("notes.md", false));
    confirm.mockRestore();
  });

  it("closes an open file preview", async () => {
    vi.mocked(localApi.listWorkspaceFiles).mockResolvedValue({
      currentDirectory: "",
      parentDirectory: null,
      entries: [
        {
          kind: "file",
          name: "notes.md",
          path: "notes.md",
          sizeBytes: 12,
          childCount: null,
          mimeType: "text/markdown",
          editable: true,
          projectionVersion: 3,
          updatedAt: "2026-08-10T12:00:00Z",
        },
      ],
    });
    vi.mocked(localApi.readWorkspaceFile).mockResolvedValue({
      fileKey: "notes.md",
      filename: "notes.md",
      contentMarkdown: "hello",
      sizeBytes: 12,
      mimeType: "text/markdown",
      editable: true,
      projectionVersion: 3,
      updatedAt: "2026-08-10T12:00:00Z",
    });

    render(<BrowserWorkspaceFileBrowser initiallyExpanded />);
    fireEvent.click(await screen.findByRole("button", { name: "Open file notes.md" }));
    expect(await screen.findByRole("button", { name: "Close preview of notes.md" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close preview of notes.md" }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Close preview of notes.md" })).not.toBeInTheDocument();
    });
    expect(screen.getByText("Open a file to preview or edit it.")).toBeInTheDocument();
  });

  it("keeps the folder title above the up-one-folder control", async () => {
    vi.mocked(localApi.listWorkspaceFiles).mockResolvedValue({
      currentDirectory: "Projects",
      parentDirectory: "",
      entries: [],
    });

    render(<BrowserWorkspaceFileBrowser initiallyExpanded />);
    const list = await screen.findByLabelText("Workspace files");
    await screen.findByRole("button", { name: "Up one folder" });
    const children = Array.from(list.children);
    expect(children[0]).toHaveClass("browser-voice-files-directory");
    expect(children[children.length - 1]).toHaveAttribute("aria-label", "Up one folder");
  });
});
