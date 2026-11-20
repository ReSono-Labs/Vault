/** Pure path, size and type helpers for the Workspace file browser. */
import type { WorkspaceFileDirectoryResponse, WorkspaceFileEntry } from "@/browser-voice/localApi";

export const SHARED_FILES_ROOT = "shared";
export const LOCAL_FILES_ROOT = "local";


export function filenameFromPath(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path || "document.md";
}


export function parentFromPath(path: string): string {
  const parts = path.split("/");
  parts.pop();
  return parts.join("/");
}


export function upDirectoryTarget(
  directory: string,
  directoryData: WorkspaceFileDirectoryResponse | null,
): string | null {
  // At the true workspace root there is nowhere to go up to, whatever the listing says.
  if (!String(directoryData ? directoryData.currentDirectory ?? "" : directory).trim()) return null;
  if (directoryData && directoryData.parentDirectory !== null) {
    return directoryData.parentDirectory;
  }
  const normalized = directory.trim();
  if (!normalized) {
    return null;
  }
  return parentFromPath(normalized);
}


export function joinPath(directory: string, name: string): string {
  return directory ? `${directory}/${name}` : name;
}


export function isSharedViewPath(path: string): boolean {
  return path === SHARED_FILES_ROOT || path.startsWith(`${SHARED_FILES_ROOT}/`);
}


export function isLocalViewPath(path: string): boolean {
  return path === LOCAL_FILES_ROOT || path.startsWith(`${LOCAL_FILES_ROOT}/`);
}


export function isProtectedWorkspacePath(path: string): boolean {
  return isSharedViewPath(path) || isLocalViewPath(path);
}


/** People-facing names for the virtual roots; paths (what agents use) stay `local/…` and `shared/…`. */
const ROOT_NAMES: Record<string, string> = { [LOCAL_FILES_ROOT]: "Folders", [SHARED_FILES_ROOT]: "Shared with me" };


export function displayPath(path: string): string {
  const [first, ...rest] = path.split("/");
  const root = ROOT_NAMES[first];
  return root ? [root, ...rest].join(" / ") : path.split("/").join(" / ");
}


export function entryName(entry: WorkspaceFileEntry): string {
  return ROOT_NAMES[entry.path] ?? entry.name;
}


export function entryDetail(entry: WorkspaceFileEntry): string {
  if (entry.kind === "file") return `${typeLabel(entry)} · ${formatBytes(entry.sizeBytes)}`;
  if (entry.path === LOCAL_FILES_ROOT) {
    const count = entry.childCount ?? 0;
    return count ? `${count} ${count === 1 ? "folder" : "folders"} on this computer` : "No folders added yet";
  }
  if (entry.path === SHARED_FILES_ROOT) {
    const count = entry.childCount ?? 0;
    return count ? `From ${count} ${count === 1 ? "person" : "people"}` : "Nothing shared with you yet";
  }
  return typeLabel(entry);
}


export function canWriteInDirectory(directory: string, data: WorkspaceFileDirectoryResponse | null): boolean {
  if (!isProtectedWorkspacePath(directory)) {
    return true;
  }
  return data?.permission === "write";
}


export function normalizeTextFilename(rawName: string): string {
  const name = rawName.trim().replace(/\\/g, "/").split("/").filter(Boolean).join("/");
  if (!name) {
    return "";
  }
  return filenameFromPath(name).includes(".") ? name : `${name}.md`;
}


export function formatBytes(sizeBytes: number | null | undefined): string {
  if (sizeBytes === null || sizeBytes === undefined) {
    return "-";
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
}


export function typeLabel(entry: WorkspaceFileEntry): string {
  if (entry.kind === "directory") {
    // Ordinary folders aren't counted (that would read every folder); don't claim "0 items".
    return entry.childCount == null ? "Folder" : `${entry.childCount} ${entry.childCount === 1 ? "item" : "items"}`;
  }
  if (entry.mimeType?.startsWith("image/")) {
    return "Image";
  }
  if (entry.mimeType === "application/pdf") {
    return "PDF";
  }
  if (entry.editable) {
    return "Editable";
  }
  return "File";
}


export function isPreviewableAsset(mimeType: string | null | undefined): boolean {
  return Boolean(mimeType?.startsWith("image/") || mimeType === "application/pdf");
}


export function shareTargetForEntry(entry: WorkspaceFileEntry, currentDirectory: string): string | null {
  if (isProtectedWorkspacePath(entry.path) || isProtectedWorkspacePath(currentDirectory) || entry.shared || entry.linked) {
    return null;
  }
  return entry.path;
}
