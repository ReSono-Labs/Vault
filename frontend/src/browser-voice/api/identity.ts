import { request } from "./request";

export type LocalUser = {
  userId: string;
  username: string;
  displayName: string;
  experienceStyle: string;
  isDeviceOwner: boolean;
  activeWorkspaceId: string;
  passwordMode:
    "user_managed" | "temporary_password" | "master_managed" | "setup_link";
  mustChangePassword: boolean;
  ageGroup: "under_18" | "adult";
};

export type LocalWorkspace = {
  workspaceId: string;
  displayName: string;
  ownerUserId: string;
  membershipType: string;
};

export type PasswordMode =
  "setup_link" | "temporary_password" | "master_managed";

export type ManagedLocalUser = Pick<
  LocalUser,
  | "userId"
  | "username"
  | "displayName"
  | "experienceStyle"
  | "isDeviceOwner"
  | "passwordMode"
  | "mustChangePassword"
  | "ageGroup"
> & { status: string; createdAt: string; activationPending: boolean };

export type ProvisionedLocalUser = {
  userId: string;
  workspaceId: string;
  passwordMode: PasswordMode;
  setupCredential: string | null;
};

export const identityApi = {
  setupStatus: () => request<{ setupComplete: boolean }>("/identity/status"),
  establishSetupSession: (setupCredential: string) =>
    request<{ status: string }>("/identity/setup-session", {
      method: "POST",
      body: JSON.stringify({ setupCredential }),
    }),
  me: () => request<{ user: LocalUser }>("/me"),
  registerOwner: (value: {
    setupCredential: string;
    username: string;
    password: string;
    displayName: string;
    experienceStyle: string;
  }) => request<{ user: LocalUser }>("/identity/register", {
    method: "POST",
    body: JSON.stringify(value),
  }),
  login: (username: string, password: string) =>
    request<{ user: LocalUser }>("/identity/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  activate: (setupCredential: string, newPassword: string) =>
    request<{ user: LocalUser }>("/identity/activate", {
      method: "POST",
      body: JSON.stringify({ setupCredential, newPassword }),
    }),
  logout: () =>
    request<{ status: string }>("/identity/logout", {
      method: "POST",
      body: "{}",
    }),
  workspaces: () => request<{ items: LocalWorkspace[] }>("/workspaces"),
  localUsers: () => request<{ items: ManagedLocalUser[] }>("/local-users"),
  createLocalUser: (value: {
    username: string;
    password?: string;
    passwordMode: PasswordMode;
    ageGroup: "under_18" | "adult";
    displayName: string;
    experienceStyle: string;
  }) =>
    request<ProvisionedLocalUser>("/local-users", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  resetLocalUserPassword: (
    userId: string,
    passwordMode: PasswordMode,
    newPassword?: string,
  ) =>
    request<{ status: string; setupCredential: string | null }>(
      `/local-users/${encodeURIComponent(userId)}/password-reset`,
      {
        method: "POST",
        body: JSON.stringify({ newPassword, passwordMode }),
      },
    ),
  removeLocalUser: (userId: string) =>
    request<{ status: string }>(
      `/local-users/${encodeURIComponent(userId)}/remove`,
      {
        method: "POST",
        body: "{}",
      },
    ),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ status: string }>("/identity/password", {
      method: "POST",
      body: JSON.stringify({ currentPassword, newPassword }),
    }),
};
