import { describe, expect, it } from "vitest";
import type { WorkspaceFileDirectoryResponse, WorkspaceFileEntry } from "@/browser-voice/localApi";
import {
  canWriteInDirectory,
  displayPath,
  entryDetail,
  entryName,
  filenameFromPath,
  formatBytes,
  isPreviewableAsset,
  isProtectedWorkspacePath,
  joinPath,
  normalizeTextFilename,
  parentFromPath,
  shareTargetForEntry,
  typeLabel,
  upDirectoryTarget,
} from "@/browser-voice/workspaceFiles";

const file = (value: Partial<WorkspaceFileEntry>): WorkspaceFileEntry => ({ kind: "file", name: "a.md", path: "a.md", ...value });
const listing = (value: Partial<WorkspaceFileDirectoryResponse>): WorkspaceFileDirectoryResponse =>
  ({ currentDirectory: "", parentDirectory: null, entries: [], ...value }) as WorkspaceFileDirectoryResponse;

describe("workspace file helpers", () => {
  it("splits and joins paths", () => {
    expect(filenameFromPath("notes/today.md")).toBe("today.md");
    expect(filenameFromPath("")).toBe("document.md");
    expect(parentFromPath("notes/sub/today.md")).toBe("notes/sub");
    expect(parentFromPath("today.md")).toBe("");
    expect(joinPath("", "a.md")).toBe("a.md");
    expect(joinPath("notes", "a.md")).toBe("notes/a.md");
  });

  it("finds the directory to go up to", () => {
    expect(upDirectoryTarget("", null)).toBeNull();
    expect(upDirectoryTarget("notes/sub", null)).toBe("notes");
    expect(upDirectoryTarget("x", listing({ currentDirectory: "notes/sub", parentDirectory: "notes" }))).toBe("notes");
    expect(upDirectoryTarget("notes", listing({ currentDirectory: "", parentDirectory: "anything" }))).toBeNull();
  });

  it("names the virtual roots for people and keeps paths for agents", () => {
    expect(displayPath("local/Projects/a")).toBe("Folders / Projects / a");
    expect(displayPath("shared")).toBe("Shared with me");
    expect(displayPath("notes/a.md")).toBe("notes / a.md");
    expect(entryName(file({ kind: "directory", name: "local", path: "local" }))).toBe("Folders");
    expect(entryName(file({ name: "a.md" }))).toBe("a.md");
    expect(isProtectedWorkspacePath("shared/x")).toBe(true);
    expect(isProtectedWorkspacePath("local")).toBe(true);
    expect(isProtectedWorkspacePath("localnotes")).toBe(false);
  });

  it("describes entries", () => {
    expect(entryDetail(file({ sizeBytes: 2048, editable: true }))).toBe("Editable · 2.0 KB");
    expect(entryDetail(file({ kind: "directory", path: "local", childCount: 1 }))).toBe("1 folder on this computer");
    expect(entryDetail(file({ kind: "directory", path: "local", childCount: 0 }))).toBe("No folders added yet");
    expect(entryDetail(file({ kind: "directory", path: "shared", childCount: 2 }))).toBe("From 2 people");
    expect(entryDetail(file({ kind: "directory", path: "shared" }))).toBe("Nothing shared with you yet");
    expect(typeLabel(file({ kind: "directory", childCount: null }))).toBe("Folder");
    expect(typeLabel(file({ kind: "directory", childCount: 1 }))).toBe("1 item");
    expect(typeLabel(file({ mimeType: "image/png" }))).toBe("Image");
    expect(typeLabel(file({ mimeType: "application/pdf" }))).toBe("PDF");
    expect(typeLabel(file({}))).toBe("File");
  });

  it("formats sizes", () => {
    expect(formatBytes(null)).toBe("-");
    expect(formatBytes(undefined)).toBe("-");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });

  it("decides write access, names, previews and share targets", () => {
    expect(canWriteInDirectory("notes", null)).toBe(true);
    expect(canWriteInDirectory("local/x", null)).toBe(false);
    expect(canWriteInDirectory("local/x", listing({ permission: "write" } as Partial<WorkspaceFileDirectoryResponse>))).toBe(true);
    expect(normalizeTextFilename("  ")).toBe("");
    expect(normalizeTextFilename("plan")).toBe("plan.md");
    expect(normalizeTextFilename("a\\b.txt")).toBe("a/b.txt");
    expect(isPreviewableAsset("image/jpeg")).toBe(true);
    expect(isPreviewableAsset("text/plain")).toBe(false);
    expect(isPreviewableAsset(null)).toBe(false);
    expect(shareTargetForEntry(file({ kind: "directory", path: "notes" }), "")).toBe("notes");
    expect(shareTargetForEntry(file({ kind: "directory", path: "local/x" }), "")).toBeNull();
    expect(shareTargetForEntry(file({ kind: "directory", path: "notes", shared: true } as Partial<WorkspaceFileEntry>), "")).toBeNull();
  });
});
