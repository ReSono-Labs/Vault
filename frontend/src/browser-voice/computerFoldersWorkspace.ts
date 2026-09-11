import type { HostFilesystemMount } from "@/browser-voice/localApi";
import type {
  WorkspaceFileDirectoryResponse,
  WorkspaceFileEntry,
  WorkspaceFileReadResponse,
} from "@/browser-voice/localApi";

const LOCAL_FILES_ROOT = "local";

const EDITABLE_EXTENSIONS = new Set([
  "css",
  "csv",
  "html",
  "js",
  "json",
  "jsx",
  "md",
  "py",
  "sh",
  "sql",
  "ts",
  "tsx",
  "txt",
  "xml",
  "yaml",
  "yml",
]);

function joinViewPath(prefix: string, relative: string): string {
  const head = prefix.replace(/\/+$/, "");
  const tail = relative.replace(/^\/+/, "");
  return tail ? `${head}/${tail}` : head;
}

function parseLocalViewPath(path: string): { mountName: string; relativePath: string } | null {
  const normalized = path.replace(/^\/+/, "").replace(/\/+$/, "");
  if (normalized === LOCAL_FILES_ROOT) {
    return { mountName: "", relativePath: "" };
  }
  if (!normalized.startsWith(`${LOCAL_FILES_ROOT}/`)) {
    return null;
  }
  const remainder = normalized.slice(LOCAL_FILES_ROOT.length + 1);
  const [mountName, ...rest] = remainder.split("/");
  if (!mountName) {
    return null;
  }
  return { mountName, relativePath: rest.join("/") };
}

export function isBrowserLocalMountPath(path: string): boolean {
  const parsed = parseLocalViewPath(path.trim());
  return parsed !== null && parsed.mountName.length > 0;
}

function isEditableFile(name: string, mimeType: string, canWrite: boolean): boolean {
  if (!canWrite) {
    return false;
  }
  if (mimeType.startsWith("text/")) {
    return true;
  }
  const extension = name.includes(".") ? name.split(".").pop()?.toLowerCase() : "";
  return extension ? EDITABLE_EXTENSIONS.has(extension) : false;
}

async function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("resono-vault-computer-folders", 1);
    request.onerror = () => reject(request.error ?? new Error("Computer folder storage failed to open."));
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains("handles")) {
        database.createObjectStore("handles", { keyPath: "mountId" });
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function getDirectoryHandle(mountId: string): Promise<FileSystemDirectoryHandle | null> {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction("handles", "readonly");
    const request = transaction.objectStore("handles").get(mountId);
    request.onerror = () => reject(request.error ?? new Error("Computer folder handle could not be loaded."));
    request.onsuccess = () => {
      const record = request.result as { handle?: FileSystemDirectoryHandle } | undefined;
      resolve(record?.handle ?? null);
    };
    transaction.oncomplete = () => database.close();
  });
}

async function listDirectoryEntries(
  directoryHandle: FileSystemDirectoryHandle,
): Promise<Array<[string, FileSystemHandle]>> {
  const handle = directoryHandle as FileSystemDirectoryHandle & {
    entries?: () => AsyncIterableIterator<[string, FileSystemHandle]>;
  };
  if (typeof handle.entries !== "function") {
    throw new Error("This browser cannot read linked folders.");
  }
  const entries: Array<[string, FileSystemHandle]> = [];
  for await (const entry of handle.entries()) {
    entries.push(entry);
  }
  return entries;
}

async function resolveDirectoryHandle(
  root: FileSystemDirectoryHandle,
  relativePath: string,
): Promise<FileSystemDirectoryHandle> {
  if (!relativePath) {
    return root;
  }
  let current = root;
  for (const part of relativePath.split("/").filter(Boolean)) {
    current = await current.getDirectoryHandle(part);
  }
  return current;
}

async function resolveFileHandle(
  root: FileSystemDirectoryHandle,
  relativePath: string,
): Promise<FileSystemFileHandle> {
  const parts = relativePath.split("/").filter(Boolean);
  if (!parts.length) {
    throw new Error("That file path is invalid.");
  }
  const fileName = parts.pop()!;
  const directory = await resolveDirectoryHandle(root, parts.join("/"));
  return directory.getFileHandle(fileName);
}

function findMount(mounts: HostFilesystemMount[], mountName: string): HostFilesystemMount {
  const mount = mounts.find((item) => item.mountName === mountName);
  if (!mount) {
    throw new Error("That linked folder is unavailable.");
  }
  return mount;
}

async function loadMountRoot(mount: HostFilesystemMount): Promise<FileSystemDirectoryHandle> {
  const handle = await getDirectoryHandle(mount.mountId);
  if (!handle) {
    throw new Error("Re-link this folder in Settings on this browser.");
  }
  return handle;
}

export async function listBrowserLocalRoot(
  mounts: HostFilesystemMount[],
): Promise<WorkspaceFileDirectoryResponse> {
  const entries: WorkspaceFileEntry[] = [];
  for (const mount of mounts) {
    let childCount: number | null = null;
    try {
      const listing = await listBrowserLocalDirectory(
        joinViewPath(LOCAL_FILES_ROOT, mount.mountName),
        mounts,
      );
      childCount = listing.entries.length;
    } catch {
      childCount = null;
    }
    entries.push({
      kind: "directory",
      name: mount.mountName,
      path: joinViewPath(LOCAL_FILES_ROOT, mount.mountName),
      linked: true,
      permission: mount.permission,
      childCount,
    });
  }
  entries.sort((left, right) => left.name.localeCompare(right.name));
  return {
    currentDirectory: LOCAL_FILES_ROOT,
    parentDirectory: "",
    entries,
  };
}

export async function listBrowserLocalDirectory(
  viewPath: string,
  mounts: HostFilesystemMount[],
): Promise<WorkspaceFileDirectoryResponse> {
  const parsed = parseLocalViewPath(viewPath);
  if (!parsed || !parsed.mountName) {
    throw new Error("That local folder path is invalid.");
  }
  const mount = findMount(mounts, parsed.mountName);
  const root = await loadMountRoot(mount);
  const mountPath = joinViewPath(LOCAL_FILES_ROOT, mount.mountName);
  const directoryHandle = await resolveDirectoryHandle(root, parsed.relativePath);
  const currentDirectory = parsed.relativePath ? joinViewPath(mountPath, parsed.relativePath) : mountPath;
  const canWrite = mount.permission === "write";
  const entries: WorkspaceFileEntry[] = [];
  const directoryEntries = await listDirectoryEntries(directoryHandle);

  for (const [name, handle] of directoryEntries) {
    const entryPath = joinViewPath(currentDirectory, name);
    if (handle.kind === "directory") {
      entries.push({
        kind: "directory",
        name,
        path: entryPath,
        linked: true,
        permission: mount.permission,
      });
      continue;
    }
    if (handle.kind !== "file") {
      continue;
    }
    const file = await (handle as FileSystemFileHandle).getFile();
    entries.push({
      kind: "file",
      name,
      path: entryPath,
      sizeBytes: file.size,
      mimeType: file.type || "application/octet-stream",
      editable: isEditableFile(name, file.type || "", canWrite),
      linked: true,
      permission: mount.permission,
    });
  }

  entries.sort((left, right) => {
    if (left.kind !== right.kind) {
      return left.kind === "directory" ? -1 : 1;
    }
    return left.name.localeCompare(right.name);
  });

  const parentDirectory = currentDirectory === mountPath
    ? LOCAL_FILES_ROOT
    : joinViewPath(mountPath, parsed.relativePath.split("/").slice(0, -1).join("/"));

  return {
    currentDirectory,
    parentDirectory,
    entries,
    permission: mount.permission,
  };
}

export async function readBrowserLocalFile(
  fileKey: string,
  mounts: HostFilesystemMount[],
): Promise<WorkspaceFileReadResponse> {
  const parsed = parseLocalViewPath(fileKey);
  if (!parsed || !parsed.mountName) {
    throw new Error("That local file path is invalid.");
  }
  const mount = findMount(mounts, parsed.mountName);
  if (!parsed.relativePath) {
    throw new Error("That path is not a file.");
  }
  const root = await loadMountRoot(mount);
  const fileHandle = await resolveFileHandle(root, parsed.relativePath);
  const file = await fileHandle.getFile();
  const canWrite = mount.permission === "write";
  const editable = isEditableFile(file.name, file.type || "", canWrite);
  let contentMarkdown = "";
  if (editable || file.type.startsWith("text/") || file.name.endsWith(".md")) {
    contentMarkdown = await file.text();
  }

  return {
    fileKey,
    filename: file.name,
    contentMarkdown,
    sizeBytes: file.size,
    mimeType: file.type || "application/octet-stream",
    editable,
    projectionVersion: 1,
    updatedAt: new Date().toISOString(),
  };
}

export async function downloadBrowserLocalFile(
  fileKey: string,
  mounts: HostFilesystemMount[],
): Promise<{ blob: Blob; contentType: string }> {
  const parsed = parseLocalViewPath(fileKey);
  if (!parsed || !parsed.mountName || !parsed.relativePath) {
    throw new Error("That local file path is invalid.");
  }
  const mount = findMount(mounts, parsed.mountName);
  const root = await loadMountRoot(mount);
  const fileHandle = await resolveFileHandle(root, parsed.relativePath);
  const file = await fileHandle.getFile();
  return {
    blob: file,
    contentType: file.type || "application/octet-stream",
  };
}
