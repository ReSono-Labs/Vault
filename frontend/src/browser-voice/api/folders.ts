import { request } from "./request";

export type FolderPermission = "read" | "write";

export type FolderStatus = "ok" | "unavailable" | "drive_disconnected" | "not_accessible";

/** A folder the user added; agents reach it at `path` (local/{name}). */
export type UserFolder = {
  folderId: string;
  name: string;
  path: string;
  location: string;
  permission: FolderPermission;
  maxPermission: FolderPermission;
  createdByVault: boolean;
  /** Hidden files (names starting with ".") are shown in this folder and everything inside it. */
  includeHidden: boolean;
  /** Switched on by the master account for the access this folder is inside. */
  hiddenFromAccess: boolean;
  /** Master account, or a folder this person made in Vault. */
  canChangeHidden: boolean;
  status: FolderStatus;
  statusMessage: string | null;
};

export type FolderList = {
  available: boolean;
  hasAccess: boolean;
  /** Master account: can add any folder Vault can see. */
  canAddAnywhere: boolean;
  folders: UserFolder[];
};

/** A place the user may add folders from (a folder the admin gave them access to). */
export type FolderPlace = {
  grantId: string;
  label: string;
  canWrite: boolean;
  status: FolderStatus;
  statusMessage: string | null;
};

export type FolderBrowse = {
  grantId?: string;
  locationId?: string;
  path: string;
  breadcrumbs: Array<{ label: string; path: string }>;
  directories: Array<{ name: string; path: string }>;
  canCreate: boolean;
};

export type FolderLocations = {
  available: boolean;
  locations: Array<{ locationId: string; label: string; kind: string; status: FolderStatus; statusMessage: string | null }>;
  places: Array<{ label: string; locationId: string; path: string; kind: string }>;
};

/** Admin view: a folder one person has been given access to. */
export type FolderAccess = {
  grantId: string;
  label: string;
  locationId: string;
  path: string;
  maxPermission: FolderPermission;
  includeHidden: boolean;
  folderCount: number;
  status: FolderStatus;
  statusMessage: string | null;
};

export const foldersApi = {
  folders: () => request<FolderList>("/folders"),
  folderPlaces: () => request<{ items: FolderPlace[] }>("/folders/places"),
  browseFolder: (grantId: string, path = "") =>
    request<FolderBrowse>(`/folders/browse?grantId=${encodeURIComponent(grantId)}&path=${encodeURIComponent(path)}`),
  addFolder: (value: {
    grantId: string;
    path: string;
    name: string;
    permission: FolderPermission;
    create?: boolean;
    newFolderName?: string;
    includeHidden?: boolean;
  }) => request<UserFolder>("/folders", { method: "POST", body: JSON.stringify(value) }),
  setFolderHidden: (folderId: string, includeHidden: boolean) =>
    request<UserFolder>(`/folders/${encodeURIComponent(folderId)}/hidden`, {
      method: "POST",
      body: JSON.stringify({ includeHidden }),
    }),
  setFolderPermission: (folderId: string, permission: FolderPermission) =>
    request<UserFolder>(`/folders/${encodeURIComponent(folderId)}/permission`, {
      method: "POST",
      body: JSON.stringify({ permission }),
    }),
  removeFolder: (folderId: string) =>
    request<{ status: string }>(`/folders/${encodeURIComponent(folderId)}/remove`, { method: "POST", body: "{}" }),
  setupVaultFolder: () => request<UserFolder>("/folders/setup/vault-folder", { method: "POST", body: "{}" }),
  adminAddFolder: (value: {
    locationId: string;
    path: string;
    name: string;
    permission: FolderPermission;
    create?: boolean;
    newFolderName?: string;
    includeHidden?: boolean;
  }) => request<UserFolder>("/admin/folders/add", { method: "POST", body: JSON.stringify(value) }),
  setupAddFolder: (value: { locationId: string; path: string; permission: FolderPermission }) =>
    request<UserFolder>("/folders/setup/add", { method: "POST", body: JSON.stringify(value) }),
  folderLocations: () => request<FolderLocations>("/admin/folders/locations"),
  browseLocation: (locationId: string, path = "") =>
    request<FolderBrowse>(
      `/admin/folders/browse?locationId=${encodeURIComponent(locationId)}&path=${encodeURIComponent(path)}`,
    ),
  folderAccess: (userId: string) =>
    request<{ items: FolderAccess[] }>(`/admin/users/${encodeURIComponent(userId)}/folder-access`),
  giveFolderAccess: (
    userId: string,
    value: { locationId: string; path: string; maxPermission: FolderPermission; includeHidden?: boolean },
  ) =>
    request<FolderAccess>(`/admin/users/${encodeURIComponent(userId)}/folder-access`, {
      method: "POST",
      body: JSON.stringify(value),
    }),
  setFolderAccessPermission: (grantId: string, maxPermission: FolderPermission) =>
    request<FolderAccess>(`/admin/folder-access/${encodeURIComponent(grantId)}/permission`, {
      method: "POST",
      body: JSON.stringify({ maxPermission }),
    }),
  setFolderAccessHidden: (grantId: string, includeHidden: boolean) =>
    request<FolderAccess>(`/admin/folder-access/${encodeURIComponent(grantId)}/hidden`, {
      method: "POST",
      body: JSON.stringify({ includeHidden }),
    }),
  removeFolderAccess: (grantId: string) =>
    request<{ status: string }>(`/admin/folder-access/${encodeURIComponent(grantId)}/remove`, {
      method: "POST",
      body: "{}",
    }),
};
