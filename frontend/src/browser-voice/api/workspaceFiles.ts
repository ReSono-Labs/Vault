import { csrfToken, request, type ApiError } from "./request";

export type WorkspaceFileEntry = {
  kind: "directory" | "file";
  name: string;
  path: string;
  sizeBytes?: number | null;
  childCount?: number | null;
  mimeType?: string | null;
  editable?: boolean | null;
  projectionVersion?: number | null;
  updatedAt?: string | null;
  shared?: boolean;
  linked?: boolean;
  shareId?: string | null;
  sharedFrom?: string | null;
  permission?: "read" | "write" | null;
  pathArea?: string | null;
};

export type WorkspaceFileDirectoryResponse = {
  currentDirectory: string;
  parentDirectory: string | null;
  entries: WorkspaceFileEntry[];
  shareId?: string | null;
  permission?: "read" | "write" | null;
  pathArea?: string | null;
};

export type WorkspaceFileReadResponse = {
  fileKey: string;
  filename: string;
  contentMarkdown: string;
  sizeBytes: number;
  mimeType: string | null;
  editable: boolean;
  projectionVersion: number;
  updatedAt: string;
};

export type WorkspaceFileMutationResponse = {
  status: string;
  message: string;
  affectedCount: number;
  path?: string | null;
  destinationPath?: string | null;
};

export type WorkspaceFolderShare = {
  shareId: string;
  folderPath: string;
  granteeUserId: string;
  granteeDisplayName: string;
  granteeUsername: string;
  permission: "read" | "write";
};

function workspaceFilesPath(directory?: string | null, shareId?: string | null) {
  const params = new URLSearchParams();
  if (directory) params.set("directory", directory);
  if (shareId) params.set("shareId", shareId);
  const suffix = params.toString();
  return `/workspace-files${suffix ? `?${suffix}` : ""}`;
}

function shareQuery(shareId?: string | null, leading = false) {
  if (!shareId) return "";
  return `${leading ? "?" : "&"}shareId=${encodeURIComponent(shareId)}`;
}

export const workspaceFilesApi = {
  listWorkspaceFiles: (directory?: string | null, shareId?: string | null) =>
    request<WorkspaceFileDirectoryResponse>(workspaceFilesPath(directory, shareId)),
  readWorkspaceFile: (fileKey: string, shareId?: string | null) =>
    request<WorkspaceFileReadResponse>(
      `/workspace-files/read?fileKey=${encodeURIComponent(fileKey)}${shareQuery(shareId)}`,
    ),
  saveWorkspaceFile: (fileKey: string, contentMarkdown: string, shareId?: string | null) =>
    request<WorkspaceFileMutationResponse>(`/workspace-files/files${shareQuery(shareId, true)}`, {
      method: "PUT",
      body: JSON.stringify({ fileKey, contentMarkdown, shareId }),
    }),
  createWorkspaceTextFile: (fileKey: string, contentMarkdown = "", shareId?: string | null) =>
    request<WorkspaceFileMutationResponse>("/workspace-files/text", {
      method: "POST",
      body: JSON.stringify({ fileKey, contentMarkdown, shareId }),
    }),
  createWorkspaceDirectory: (directory: string, shareId?: string | null) =>
    request<WorkspaceFileMutationResponse>("/workspace-files/directories", {
      method: "POST",
      body: JSON.stringify({ directory, shareId }),
    }),
  uploadWorkspaceFiles: async (directory: string | null, files: FileList | File[], shareId?: string | null) => {
    const form = new FormData();
    if (directory) form.append("directory", directory);
    if (shareId) form.append("shareId", shareId);
    Array.from(files).forEach((file) => form.append("files", file));
    const headers = new Headers();
    const csrf = csrfToken();
    if (csrf) headers.set("X-ReSono-CSRF", csrf);
    const response = await fetch("/workspace-files/upload", {
      method: "POST",
      headers,
      body: form,
      credentials: "same-origin",
    });
    const value = (await response.json().catch(() => ({}))) as WorkspaceFileMutationResponse & ApiError;
    if (!response.ok) throw new Error(value.error?.message || `Upload failed (${response.status}).`);
    return value;
  },
  moveWorkspacePath: (sourcePath: string, destinationPath: string, shareId?: string | null) =>
    request<WorkspaceFileMutationResponse>("/workspace-files/move", {
      method: "POST",
      body: JSON.stringify({ sourcePath, destinationPath, shareId }),
    }),
  deleteWorkspacePath: (path: string, recursive: boolean, shareId?: string | null) =>
    request<WorkspaceFileMutationResponse>("/workspace-files/delete", {
      method: "POST",
      body: JSON.stringify({ path, recursive, shareId }),
    }),
  downloadWorkspaceFile: async (fileKey: string, shareId?: string | null) => {
    const response = await fetch(
      `/workspace-files/download?fileKey=${encodeURIComponent(fileKey)}${shareQuery(shareId)}`,
      { credentials: "same-origin" },
    );
    if (!response.ok) throw new Error(`Download failed (${response.status}).`);
    const blob = await response.blob();
    return {
      blob,
      contentType: response.headers.get("content-type") || blob.type || "application/octet-stream",
    };
  },
  listWorkspaceShares: (folderPath: string) =>
    request<{ items: WorkspaceFolderShare[] }>(
      `/workspace-files/shares?folderPath=${encodeURIComponent(folderPath)}`,
    ),
  saveWorkspaceShare: (folderPath: string, granteeUserId: string, permission: "read" | "write") =>
    request<WorkspaceFolderShare>("/workspace-files/shares", {
      method: "POST",
      body: JSON.stringify({ folderPath, granteeUserId, permission }),
    }),
  revokeWorkspaceShare: (shareId: string) =>
    request<{ status: string }>(`/workspace-files/shares/${encodeURIComponent(shareId)}/revoke`, {
      method: "POST",
      body: "{}",
    }),
};
