import { request } from "./request";

export const voiceApi = {
  startVoice: (value: {
    providerKey: string;
    modelKey: string;
    connectionMode: "webrtc" | "provider-websocket";
    voice?: string;
    offerSdp?: string;
  }) =>
    request<{
      voiceRealtimeSessionId: string;
      liveTranscription?: boolean;
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
  startVoiceTranscription: (id: string) => request<{ clientSecret: string }>(
    `/voice/sessions/${encodeURIComponent(id)}/preparation/transcription`, { method: "POST", body: "{}" }),
  prepareVoice: (id: string, value: { utteranceId: string; revision: number; text: string; composing: boolean }) =>
    request<{ enabled?: boolean }>(`/voice/sessions/${encodeURIComponent(id)}/preparation`, { method: "POST", body: JSON.stringify(value) }),
  voicePreparation: (id: string, utterance: string, revision: number) =>
    request<import("../conversation/api").Preparation>(`/voice/sessions/${encodeURIComponent(id)}/preparation?utteranceId=${encodeURIComponent(utterance)}&revision=${revision}`),
  voicePreparationDelivered: (id: string, utteranceId: string, memoryCount: number, toolCount = 0) =>
    request(`/voice/sessions/${encodeURIComponent(id)}/preparation/delivered`,
      { method: "POST", body: JSON.stringify({ utteranceId, memoryCount, toolCount }) }),
  discardVoicePreparation: (id: string) => request(`/voice/sessions/${encodeURIComponent(id)}/preparation`, { method: "DELETE" }),
  closeVoice: (id: string, capture?: { transcriptCaptureFailures: number }) =>
    request<{ status: string }>(
      `/voice/sessions/${encodeURIComponent(id)}/close`,
      {
        method: "POST",
        body: JSON.stringify(capture ?? {}),
        keepalive: true,
      },
    ),
  captureVoiceEvent: (
    id: string,
    value: {
      providerEventId: string;
      eventType: string;
      role: "user" | "assistant";
      transcriptText?: string;
      transcriptEntryIndex?: number;
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
  /**
   * Run a Voice tool call. The server keeps running a call whose request was dropped (mobile
   * networks and tunnels can cut long requests such as Web search), so a network failure or a
   * "pending" answer is retried with the same toolCallId until the stored result is returned.
   */
  callVoiceTool: async (
    id: string,
    value: {
      name: string;
      toolCallId: string;
      arguments: Record<string, unknown>;
      userUtterance?: string;
      userUtteranceId?: number;
    },
  ) => {
    type ToolResult = {
      content: Array<{ type: "text"; text: string }>;
      isError: boolean;
      structuredContent?: Record<string, unknown>;
      resonoSessionUpdate?: Record<string, unknown>;
      pending?: boolean;
    };
    const deadline = Date.now() + 90_000;
    for (let attempt = 0; ; attempt += 1) {
      try {
        const result = await request<ToolResult>(`/voice/sessions/${encodeURIComponent(id)}/tools/call`, {
          method: "POST",
          body: JSON.stringify(value),
        });
        if (!result.pending) return result;
      } catch (caught) {
        // Only connection failures are retried; an HTTP error from Vault is a real answer.
        if (!(caught instanceof TypeError)) throw caught;
      }
      if (Date.now() > deadline)
        throw new Error("The tool is taking too long to respond. Please try again.");
      await new Promise(resolve => setTimeout(resolve, Math.min(400 + attempt * 200, 1500)));
    }
  },
    finalizeVoice: (id: string) =>
    request<{
      learning: "completed" | "already_completed";
      memoryCount: number;
      summary: string;
    }>(`/voice/sessions/${encodeURIComponent(id)}/finalize`, {
      method: "POST",
      body: "{}",
    }),
};
