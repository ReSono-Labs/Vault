import { fileBase64, request } from "./request";

export type LocalExtension = {
  extensionId: string;
  kind: "plugin" | "skill" | "mcp";
  identity: string;
  displayName: string;
  version: string | null;
  description: string | null;
  state: "enabled" | "disabled" | "removed";
  configuration: Record<string, unknown>;
};

export type LocalTool = {
  name: string;
  description: string;
  category: string;
  effectClass: "read" | "write" | "delete";
  audiences: ("voice" | "background")[];
  builtIn: boolean;
};

export type ExtensionGrant = {
  capabilityName: string;
  agentKind: "voice" | "background";
  enabled: boolean;
  effectClass: "read" | "write" | "delete" | null;
};

export type BuiltinPlugin = {
  key: "markets" | "weather" | "news" | "local_events" | "agent_mail" | "tasks" | "agent2agent" | "agent2agent_collab";
  name: string;
  description: string;
  enabled: boolean;
  builtIn: true;
  canDelete: false;
  configuration: Record<string, unknown>;
  updatedAt: string | null;
};

export type McpAccountStatus = {
  account: "personal" | "shared" | "none";
  kind: "headers" | "oauth" | null;
  expiresAt: number | null;
  scope: string | null;
  renewable?: boolean;
  updatedAt?: string | null;
  isSharedAccount: boolean;
  sharedAccountAvailable: boolean;
  sharedWith?: string[];
};

type McpAccountAction =
  | { action: "sign-in"; redirectUri: string }
  | { action: "disconnect" }
  | { action: "share"; shared: boolean }
  | { action: "share-grant"; userId: string; granted: boolean }
  | { action: "client"; clientId: string; clientSecret?: string };

export const extensionsApi = {
  mcpAccount: (extensionId: string) =>
    request<McpAccountStatus>(`/extensions/${encodeURIComponent(extensionId)}/account`),
  mcpAccountAction: <T = McpAccountStatus>(extensionId: string, body: McpAccountAction) =>
    request<T>(`/extensions/${encodeURIComponent(extensionId)}/account`, {
      method: "POST", body: JSON.stringify(body),
    }),
  extensions: () => request<{ items: LocalExtension[] }>("/extensions"),
  pluginConnections: (extensionId: string) => request<{ items: LocalExtension[] }>(
    `/extensions/${encodeURIComponent(extensionId)}/connections`,
  ),
  savePluginSettings: (extensionId: string, values: Record<string, unknown>) =>
    request<LocalExtension>(`/extensions/${encodeURIComponent(extensionId)}/settings`, {
      method: "POST",
      body: JSON.stringify({ values }),
    }),
  saveExtensionSettings: (extensionId: string, values: Record<string, unknown>) =>
    request<LocalExtension>(`/extensions/${encodeURIComponent(extensionId)}/settings`, {
      method: "POST",
      body: JSON.stringify({ values }),
    }),
  preflightMcpPackage: async (file: File) => {
    const encoded = await fileBase64(file);
    return request<{
      token: string;
      identity: string;
      replacement: boolean;
      diagnostics?: string[];
      migration?: {
        onConflict: string;
        requiresDecision: boolean;
        databaseConflict?: string | null;
        workspaceConflict?: string | null;
      };
    }>(
      "/extensions/mcp-packages/preflight",
      {
        method: "POST",
        body: JSON.stringify({
          archiveBase64: encoded,
          filename: file.name,
          audience: ["voice", "background"],
        }),
      },
    );
  },
  confirmMcpPackage: (token: string, replace: boolean, replaceMigration = false) =>
    request<LocalExtension>("/extensions/confirm", {
      method: "POST",
      body: JSON.stringify({ kind: "mcp-package", token, replace, replaceMigration }),
    }),
  discoverPluginTools: (extensionId: string) => request<{ items: string[] }>(
    `/extensions/${encodeURIComponent(extensionId)}/discover`,
    { method: "POST", body: "{}" },
  ),
  grantPluginTool: (extensionId: string, value: { targetUserId: string; agentKind: "voice" | "background"; capabilityName: string; enabled: boolean; effectClass: "read" | "write" | "delete" }) => request<{ status: string }>(
    `/extensions/${encodeURIComponent(extensionId)}/grants`,
    { method: "POST", body: JSON.stringify(value) },
  ),
  extensionGrants: (extensionId: string) => request<{ items: ExtensionGrant[] }>(
    `/extensions/${encodeURIComponent(extensionId)}/grants`,
  ),
  builtinPlugins: () => request<{ items: BuiltinPlugin[] }>("/builtin-plugins"),
  updateBuiltinPlugin: (key: BuiltinPlugin["key"], value: { enabled?: boolean; configuration?: Record<string, unknown> }) =>
    request<BuiltinPlugin>(`/builtin-plugins/${encodeURIComponent(key)}`, { method: "POST", body: JSON.stringify(value) }),
  tools: () => request<{ items: LocalTool[] }>("/tools"),
  extensionRuntime: () => request<{ safeMode: boolean }>("/extensions/runtime"),
  safeMode: (enabled: boolean) =>
    request<{ safeMode: boolean }>("/extensions/safe-mode", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  extensionState: (
    extensionId: string,
    state: "enabled" | "disabled" | "removed",
  ) =>
    request<LocalExtension>(
      `/extensions/${encodeURIComponent(extensionId)}/state`,
      {
        method: "POST",
        body: JSON.stringify({ state }),
      },
    ),
  /** Import from a folder the person was given (Settings -> Folders), same checks as a file. */
  folderPreflight: (kind: "plugin" | "skill" | "mcp-package", grantId: string, path: string) =>
    request<{ token: string; identity: string; replacement: boolean; diagnostics?: string[] } & Record<string, unknown>>(
      "/extensions/folder-preflight",
      { method: "POST", body: JSON.stringify({ kind, grantId, path, audience: ["voice", "background"] }) },
    ),
  preflight: async (kind: "plugin" | "skill" | "mcp", file: File) => {
    const encoded = await fileBase64(file);
    const path =
      kind === "mcp"
        ? "/extensions/mcp/preflight"
        : `/extensions/${kind}s/preflight`;
    const body =
      kind === "mcp"
        ? { documentBase64: encoded, audience: ["voice", "background"] }
        : {
            archiveBase64: encoded,
            filename: file.name,
            audience: ["voice", "background"],
          };
    return request<
      | {
          token: string;
          identity: string;
          replacement: boolean;
          diagnostics?: string[];
          migration?: { requiresDecision: boolean };
        }
      | {
          items: Array<{
            token: string;
            identity: string;
            replacement: boolean;
          }>;
        }
    >(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  confirmExtension: (
    kind: "plugin" | "skill" | "mcp",
    token: string,
    replace: boolean,
    replaceMigration = false,
    localShare?: { folderId: string; createdDuringImport: boolean } | null,
    replaceWorkspaceImport = false,
  ) =>
    request<LocalExtension>("/extensions/confirm", {
      method: "POST",
      body: JSON.stringify({
        kind,
        token,
        replace,
        replaceMigration,
        replaceWorkspaceImport,
        ...(localShare
          ? {
              localShareFolderId: localShare.folderId,
              localShareCreatedDuringImport: localShare.createdDuringImport,
            }
          : {}),
      }),
    }),
};
