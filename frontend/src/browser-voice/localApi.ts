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

export type BackgroundRun = {
  runId: string;
  objective: string;
  invocationType: string;
  originId: string;
  state: string;
  cancellationRequested: boolean;
  output: Record<string, unknown> | null;
  failure: { code: string | null; message: string | null } | null;
  failureCode: string | null;
  failureMessage: string | null;
  failureExplanation: string | null;
  modelTurns: number;
  toolCalls: number;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  reasoningEntries: { type: string; createdAt: string; detail: Record<string, unknown> }[];
  progress: {
    label: string;
    fraction: number;
    active: boolean;
    tone: string;
    activity: string;
    modelTurns: number;
    toolCalls: number;
    timeline: { label: string; createdAt: string }[];
  };
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

export type RecoveryCredential = {
  username: string;
  generatedPassword: string;
  mustStoreNow: true;
};

export type VoiceProviderStatus = {
  providerKey: string;
  displayName?: string;
  configured: boolean;
  modelKey: string;
  voice: string;
  backgroundModelKey: string;
  updatedAt: string | null;
  accessMode?: "shared" | "individual";
  connectionMode?: "webrtc" | "provider-websocket";
  protocol?: string;
  voices?: string[];
  voiceModels?: string[];
  selected?: boolean;
  authMethod?: "api_key" | "chatgpt_oauth" | "gemini_oauth" | null;
  apiKeyConnected?: boolean;
  oauthConnected?: boolean;
  negotiatedDataChannel?: boolean;
  dataChannelId?: number | null;
  transport?: string;
};
export type AIProviderCatalog = {
  selectedProviderKey: string;
  items: VoiceProviderStatus[];
};
export type HelpMessage = { role: "user" | "assistant"; content: string };
export type HelpAnswer = {
  answer: string;
  providerKey: string;
  modelKey: string;
  sources: Array<{ label: string; kind: "guide" | "source" | "web"; url?: string }>;
  learned: boolean;
};
export type AccountProviderAccess = {
  userId: string;
  accessMode: "shared" | "individual";
  sharedConfigured: boolean;
  individualConfigured: boolean;
};

export type MailAccount = {
  mailboxAccountId: string;
  mailboxRole: "normal_email" | "agent_mail";
  emailAddress: string;
  displayName: string | null;
  lifecycleStatus: "active" | "disabled" | "disconnected" | "removed";
  syncEnabled: boolean;
  syncStatus: string;
};

export type CalendarAccount = {
  calendarAccountId: string;
  providerType: "ics" | "caldav";
  displayName: string;
  configuration: { feedUrl?: string; calendarUrl?: string };
  status: "active" | "disabled";
  sync: Record<string, unknown>;
  updatedAt: string;
};

export type ExternalMemoryIntegration = {
  integrationId: string;
  displayName: string;
  adapterKind: string;
  grants: ("search" | "propose" | "correct" | "forget")[];
  status: "active" | "revoked";
  createdAt: string;
  revokedAt: string | null;
};

export type ExternalMemoryPairing = {
  pairingId: string;
  displayName: string;
  adapterKind: string;
  grants: ExternalMemoryIntegration["grants"];
  status: "pending";
};

export type A2AConnection = {
  connectionId: string;
  displayName: string;
  cardUrl: string;
  enabled: boolean;
  agentCard: {
    name?: string;
    description?: string;
    version?: string;
    provider?: { organization?: string; url?: string };
    capabilities?: Record<string, unknown>;
    supportedInterfaces?: Array<{ url?: string; protocolBinding?: string; protocolVersion?: string }>;
    skills?: Array<{ id?: string; name?: string; description?: string; tags?: string[] }>;
  };
};

export type A2ANotification = {
  taskId: string;
  agentName: string;
  state: string;
  summary: string;
  issue: string | null;
  ownerKind: "voice" | "background";
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
};

type ApiError = { error?: { message?: string } };

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )resono_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined)
    headers.set("Content-Type", "application/json");
  if ((options.method ?? "GET").toUpperCase() !== "GET") {
    const csrf = csrfToken();
    if (csrf) headers.set("X-ReSono-CSRF", csrf);
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const value = (await response.json().catch(() => ({}))) as T & ApiError;
  if (!response.ok)
    throw new Error(
      value.error?.message ||
        `Local Vault request failed (${response.status}).`,
    );
  return value;
}

export const localApi = {
  askHelp: (message: string, history: HelpMessage[], searchWeb: boolean) =>
    request<HelpAnswer>("/help/ask", {
      method: "POST",
      body: JSON.stringify({ message, history, searchWeb }),
    }),
  setupStatus: () => request<{ setupComplete: boolean }>("/identity/status"),
  establishSetupSession: (setupCredential: string) =>
    request<{ status: string }>("/identity/setup-session", {
      method: "POST",
      body: JSON.stringify({ setupCredential }),
    }),
  me: () => request<{ user: LocalUser }>("/me"),
  onboard: (value: {
    setupCredential: string;
    displayName: string;
    experienceStyle: string;
  }) =>
    request<{ user: LocalUser; recovery: RecoveryCredential }>(
      "/identity/onboard",
      {
        method: "POST",
        body: JSON.stringify(value),
      },
    ),
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
  selectWorkspace: (workspaceId: string) =>
    request<{ user: LocalUser }>("/workspaces/select", {
      method: "POST",
      body: JSON.stringify({ workspaceId }),
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
  backgroundRuns: () => request<{ items: BackgroundRun[] }>("/background/runs"),
  cancelBackgroundRun: (runId: string) => request<BackgroundRun>(
    `/background/runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST", body: "{}" },
  ),
  deleteBackgroundRun: (runId: string) => request<{ runId: string; deleted: boolean }>(
    `/background/runs/${encodeURIComponent(runId)}`,
    { method: "DELETE" },
  ),
  extensionRuntime: () => request<{ safeMode: boolean }>("/extensions/runtime"),
  providers: () => request<AIProviderCatalog>("/providers/catalog"),
  voiceProvider: (providerKey = "openai") => request<VoiceProviderStatus>(`/providers/${encodeURIComponent(providerKey)}`),
  setVoiceProvider: (providerKey: string, value: {
    apiKey?: string;
    modelKey: string;
    backgroundModelKey: string;
    voice: string;
  }) =>
    request<VoiceProviderStatus>(`/providers/${encodeURIComponent(providerKey)}`, {
      method: "POST",
      body: JSON.stringify(value),
    }),
  removeVoiceProvider: (providerKey = "openai") =>
    request<{ status: string }>(`/providers/${encodeURIComponent(providerKey)}`, { method: "DELETE" }),
  selectProvider: (providerKey: string) => request<{ selectedProviderKey: string }>(
    `/providers/${encodeURIComponent(providerKey)}/select`, { method: "POST", body: "{}" },
  ),
  selectProviderAuth: (providerKey: string, authMethod: "api_key" | "chatgpt_oauth" | "gemini_oauth") =>
    request<VoiceProviderStatus>(`/providers/${encodeURIComponent(providerKey)}/auth-method`, {
      method: "POST", body: JSON.stringify({ authMethod }),
    }),
  disconnectProviderOAuth: (providerKey: string) => request<VoiceProviderStatus>(
    `/providers/${encodeURIComponent(providerKey)}/oauth`, { method: "DELETE" },
  ),
  startChatGptOAuth: () => request<{ authSessionId: string; verificationUrl: string; userCode: string; expiresAt: number; pollIntervalSeconds: number }>(
    "/providers/openai/oauth/start", { method: "POST", body: "{}" },
  ),
  pollChatGptOAuth: (authSessionId: string) => request<{ status: "pending" | "completed" }>(
    "/providers/openai/oauth/poll", { method: "POST", body: JSON.stringify({ authSessionId }) },
  ),
  startGeminiOAuth: (redirectUri: string) => request<{ authorizationUrl: string }>(
    "/providers/gemini/oauth/start", { method: "POST", body: JSON.stringify({ redirectUri }) },
  ),
  accountProviderAccess: (userId: string, providerKey = "openai") =>
    request<AccountProviderAccess>(`/providers/${encodeURIComponent(providerKey)}/users/${encodeURIComponent(userId)}`),
  setAccountProviderAccess: (userId: string, value: {
    accessMode: "shared" | "individual";
    apiKey?: string;
  }, providerKey = "openai") => request<AccountProviderAccess>(`/providers/${encodeURIComponent(providerKey)}/users/${encodeURIComponent(userId)}`, {
    method: "POST",
    body: JSON.stringify(value),
  }),
  mailAccounts: () => request<{ items: MailAccount[] }>("/mail/accounts"),
  agentMailAccounts: () => request<{ items: MailAccount[] }>("/mail/agent-accounts"),
  connectMail: (value: {
    displayName?: string;
    credentials: {
      emailAddress: string;
      imap: {
        host: string;
        port: number;
        username: string;
        password: string;
        useTls: true;
      };
      smtp: {
        host: string;
        port: number;
        username: string;
        password: string;
        useTls: true;
      };
    };
    validateConnection: boolean;
  }) =>
    request<MailAccount>("/mail/accounts", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  connectAgentMail: (value: {
    displayName?: string;
    credentials: { emailAddress: string; imap: { host: string; port: number; username: string; password: string; useTls: true }; smtp: { host: string; port: number; username: string; password: string; useTls: true } };
    validateConnection: boolean;
  }) => request<MailAccount>("/mail/agent-accounts", { method: "POST", body: JSON.stringify(value) }),
  calendarAccounts: () =>
    request<{ items: CalendarAccount[] }>("/calendar/accounts"),
  connectCalendar: (value: {
    providerType: "ics" | "caldav";
    displayName?: string;
    credentials: {
      feedUrl?: string;
      calendarUrl?: string;
      username?: string;
      password?: string;
    };
    validateConnection: boolean;
  }) =>
    request<CalendarAccount>("/calendar/accounts", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  externalMemoryIntegrations: () =>
    request<{ items: ExternalMemoryIntegration[] }>("/external-memory/integrations"),
  createExternalMemoryIntegration: (value: {
    displayName: string;
    adapterKind: string;
    grants: ExternalMemoryIntegration["grants"];
  }) => request<ExternalMemoryIntegration & { credential: string }>(
    "/external-memory/integrations", { method: "POST", body: JSON.stringify(value) },
  ),
  externalMemoryPairing: (code: string) =>
    request<ExternalMemoryPairing>(
      `/external-memory/integrations/pairing/${encodeURIComponent(code)}`,
    ),
  approveExternalMemoryPairing: (pairingId: string) =>
    request<ExternalMemoryIntegration>(
      `/external-memory/integrations/pairing/${encodeURIComponent(pairingId)}/approve`,
      { method: "POST", body: "{}" },
    ),
  revokeExternalMemoryIntegration: (integrationId: string) =>
    request<{ status: string }>(
      `/external-memory/integrations/${encodeURIComponent(integrationId)}/revoke`,
      { method: "POST", body: "{}" },
    ),
  removeExternalMemoryIntegration: (integrationId: string) =>
    request<{ status: string }>(
      `/external-memory/integrations/${encodeURIComponent(integrationId)}`,
      { method: "DELETE", body: "{}" },
    ),
  hostFilesystemSettings: () => request<HostFilesystemSettings>("/host-filesystem/settings"),
  saveHostFilesystemSettings: (value: { enabled: boolean; helperBaseUrl?: string; currentPassword?: string }) =>
    request<HostFilesystemSettings>("/host-filesystem/settings", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  hostFilesystemIntegrations: () => request<{ items: HostFilesystemIntegration[] }>("/host-filesystem/integrations"),
  hostFilesystemPairing: (code: string) =>
    request<HostFilesystemPairing>(`/host-filesystem/integrations/pairing/${encodeURIComponent(code)}`),
  linkCompanion: () => request<{ status: string; displayName?: string; pairingId?: string; pairedAt?: string }>("/link-companion"),
  linkCompanionPairing: (code: string) =>
    request<{ pairingId: string; displayName: string; status: string }>(
      `/link-companion/pairing/${encodeURIComponent(code)}`,
    ),
  approveLinkCompanionPairing: (pairingId: string) =>
    request<{ status: string; displayName: string }>(
      `/link-companion/pairing/${encodeURIComponent(pairingId)}/approve`,
      { method: "POST", body: "{}" },
    ),
  unpairLinkCompanion: () =>
    request<{ status: string }>("/link-companion/unpair", { method: "POST", body: "{}" }),
  approveHostFilesystemPairing: (pairingId: string) =>
    request<HostFilesystemIntegration>(
      `/host-filesystem/integrations/pairing/${encodeURIComponent(pairingId)}/approve`,
      { method: "POST", body: "{}" },
    ),
  hostFilesystemMounts: () => request<{ items: HostFilesystemMount[] }>("/host-filesystem/mounts"),
  registerHostFilesystemMount: (value: {
    mountId: string;
    mountName: string;
    permission: "read" | "write";
    hostPath?: string;
    source?: "browser" | "helper";
  }) =>
    request<HostFilesystemMount>("/host-filesystem/mounts", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  revokeHostFilesystemMount: (mountId: string) =>
    request<{ status: string }>(`/host-filesystem/mounts/${encodeURIComponent(mountId)}/revoke`, {
      method: "POST",
      body: "{}",
    }),
  a2aConnections: () => request<{ items: A2AConnection[] }>("/agent2agent/connections"),
  a2aNotifications: () => request<{ items: A2ANotification[] }>("/agent2agent/notifications"),
  a2aListen: () => request<{ cardUrl: string; rpcUrl: string; token: string }>("/agent2agent/listen"),
  notifications: () => request<{ items: VaultNotification[]; unreadCount: number }>("/notifications"),
  clearNotification: (notificationId: string) =>
    request<{ status: string; notificationId: string }>(`/notifications/${encodeURIComponent(notificationId)}/clear`, {
      method: "POST",
      body: "{}",
    }),
  clearAllNotifications: () => request<{ status: string; clearedCount: number }>("/notifications/clear", {
    method: "POST",
    body: "{}",
  }),
  activeTasks: () => request<{ tasks: VaultTask[] }>("/tasks/active"),
  connectA2A: (value: { displayName: string; cardUrl: string; token?: string }) =>
    request<A2AConnection>("/agent2agent/connections", { method: "POST", body: JSON.stringify(value) }),
  removeA2A: (connectionId: string) => request<{ status: string }>(
    `/agent2agent/connections/${encodeURIComponent(connectionId)}`, { method: "DELETE" },
  ),
  syncCalendar: (calendarAccountId: string) =>
    request<Record<string, unknown>>(
      `/calendar/accounts/${encodeURIComponent(calendarAccountId)}/sync`,
      { method: "POST", body: "{}" },
    ),
  removeCalendar: (calendarAccountId: string) =>
    request<{ status: string }>(
      `/calendar/accounts/${encodeURIComponent(calendarAccountId)}`,
      { method: "DELETE" },
    ),
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
    localShare?: { mountId: string; mountName: string; permission: "read" | "write" } | null,
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
              localShareMountId: localShare.mountId,
              localShareMountName: localShare.mountName,
              localSharePermission: localShare.permission,
            }
          : {}),
      }),
    }),
  startVoice: (value: {
    providerKey: string;
    modelKey: string;
    connectionMode: "webrtc" | "provider-websocket";
    voice?: string;
    offerSdp?: string;
  }) =>
    request<{
      voiceRealtimeSessionId: string;
      connectionMode: "webrtc" | "provider-websocket";
      clientSecret: string | null;
      sdpAnswer: string | null;
      sessionUpdate: Record<string, unknown> | null;
      connectGreetingEvent: Record<string, unknown> | null;
      protocol: string;
      websocketUrl: string | null;
      websocketProtocol: string | null;
      inputSampleRate: number | null;
      outputSampleRate: number | null;
    }>("/voice/sessions", { method: "POST", body: JSON.stringify(value) }),
  voicePlan: (value: { providerKey: string; modelKey: string }) =>
    request<{
      transport: string;
      negotiatedDataChannel: boolean;
      dataChannelId: number | null;
    }>(
      `/voice/plan?providerKey=${encodeURIComponent(value.providerKey)}&modelKey=${encodeURIComponent(value.modelKey)}`,
    ),
  closeVoice: (id: string) =>
    request<{ status: string }>(
      `/voice/sessions/${encodeURIComponent(id)}/close`,
      {
        method: "POST",
        body: "{}",
        keepalive: true,
      },
    ),
  captureVoiceEvent: (
    id: string,
    value: {
      providerEventId: string;
      eventType: string;
      role: "user" | "assistant";
      transcriptText: string;
      transcriptEntryIndex: number;
      providerPayload: Record<string, unknown>;
    },
  ) =>
    request<{ accepted: boolean }>(
      `/voice/sessions/${encodeURIComponent(id)}/events`,
      {
        method: "POST",
        body: JSON.stringify(value),
        keepalive: true,
      },
    ),
  callVoiceTool: (
    id: string,
    value: {
      name: string;
      toolCallId: string;
      arguments: Record<string, unknown>;
      userUtterance?: string;
      userUtteranceId?: number;
    },
  ) =>
    request<{
      content: Array<{ type: "text"; text: string }>;
      isError: boolean;
      structuredContent?: Record<string, unknown>;
      resonoSessionUpdate?: Record<string, unknown>;
    }>(`/voice/sessions/${encodeURIComponent(id)}/tools/call`, {
      method: "POST",
      body: JSON.stringify(value),
    }),
    finalizeVoice: (id: string) =>
    request<{
      learning: "completed" | "already_completed";
      memoryCount: number;
      summary: string;
    }>(`/voice/sessions/${encodeURIComponent(id)}/finalize`, {
      method: "POST",
      body: "{}",
    }),
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

export type VaultNotification = {
  notificationId: string;
  kind: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  createdAt: string;
};

export type VaultTask = {
  taskId: string;
  text: string;
  status: "open" | "completed";
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
};

export type HostFilesystemSettings = {
  enabled: boolean;
  helperBaseUrl: string;
};

export type HostFilesystemIntegration = {
  integrationId: string;
  displayName: string;
  adapterKind: string;
  status: string;
  createdAt: string;
  revokedAt?: string | null;
};

export type HostFilesystemPairing = {
  pairingId: string;
  displayName: string;
  adapterKind: string;
  status: string;
};

export type HostFilesystemMount = {
  mountId: string;
  mountName: string;
  mountPath: string;
  permission: "read" | "write";
  source?: "browser" | "helper";
  status: string;
  createdAt: string;
};

export type HostFilesystemPick = {
  mountId: string;
  suggestedName: string;
  hostPath: string;
  hostPathLabel: string;
};

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

async function fileBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
