import { request } from "./request";

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
  textModels?: string[];
  selected?: boolean;
  authMethod?: "api_key" | "chatgpt_oauth" | "gemini_oauth" | "xai_oauth" | null;
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

export type AccountProviderAccess = {
  userId: string;
  accessMode: "shared" | "individual";
  sharedConfigured: boolean;
  individualConfigured: boolean;
};

export const providersApi = {
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
  selectProvider: (providerKey: string) => request<{ selectedProviderKey: string }>(
    `/providers/${encodeURIComponent(providerKey)}/select`, { method: "POST", body: "{}" },
  ),
  selectProviderAuth: (providerKey: string, authMethod: "api_key" | "chatgpt_oauth" | "gemini_oauth" | "xai_oauth") =>
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
  startXaiOAuth: () => request<{ authSessionId: string; verificationUrl: string; userCode: string; expiresAt: number; pollIntervalSeconds: number }>(
    "/providers/xai/oauth/start", { method: "POST", body: "{}" },
  ),
  pollXaiOAuth: (authSessionId: string) => request<{ status: "pending" | "completed" }>(
    "/providers/xai/oauth/poll", { method: "POST", body: JSON.stringify({ authSessionId }) },
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
};
