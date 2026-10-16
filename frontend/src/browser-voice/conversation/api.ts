import { request } from "@/browser-voice/localApi";

export type TurnState = "submitted" | "running" | "completed" | "failed" | "interrupted";
export type ChatAttachment = { id: string; name: string; mime: string; hash: string; size: number; coverage: string };
import type { CardLayout } from "@/browser-voice/genui/layouts";
export type { CardLayout };
export type CardItem = { title?: string; detail?: string; time?: string; state?: "done" | "needs_you" | "optional" | "pending";
  text?: string; done?: boolean; label?: string; value?: string; trend?: "up" | "down" | "flat"; amount?: number;
  source?: string; url?: string; rating?: string; distance?: string; status?: string;
  condition?: "sun" | "partly" | "cloud" | "rain" | "snow" | "storm" | "fog" | "wind" | "night" };
/** Server-validated display card (genui/catalog.py). Rendered only by registered Vault components. */
export type VaultCard = { version: number; layout: CardLayout; title?: string; fallbackText: string; body?: string;
  items?: CardItem[]; columns?: string[]; rows?: string[][]; chartKind?: "line" | "bar" };
export type ChatCardPart = { cardId: string; card: VaultCard; sources: string[] };
export type ChatTurn = { turnId: string; input: string; answer: string | null; state: TurnState; attachments?: ChatAttachment[]; ui?: ChatCardPart[] };
export type ChatHeader = { conversationId: string; title: string; historyVersion: number; state: string };
export type ChatHistory = ChatHeader & { turns: ChatTurn[]; nextBefore?: number | null };
export type TurnStatus = { conversationId: string; turnId: string; input: string; historyVersion: number; state: TurnState };
export type SendRequest = { submissionKey: string; input: string; expectedHistoryVersion: number; attachmentIds?: string[] };
const path = (id: string) => `/conversations/${encodeURIComponent(id)}`;
export type Preparation = { revision: number; state: string; toolState?: string;
  memories: { id: string; text: string; methods: string[] }[];
  tools: { id: string; name?: string; description: string; kind: string }[] };
export type FeedbackState = { verdict: "up" | "down" | null; chosenLayout: string | null; hasPreviews: boolean; shown: string[] };
export type PresentationPreview = { layout: CardLayout | "text"; card: VaultCard | null };
export type Alternatives = { current: { layout: string; card: VaultCard | null; text: string }; previews: PresentationPreview[] };
export type PresentationNotice = { summary: string; layout: string; replaced: string; events: number; share: number;
  example: VaultCard | null; version: number };
export type PresentationState = { version: number; config: Record<string, unknown>; notice: PresentationNotice | null; noticePending: boolean };
const turnPath = (id: string, turn: string) => `${path(id)}/turns/${encodeURIComponent(turn)}`;
export const genuiApi = {
  feedback: (id: string, turn: string, verdict: "up" | "down" | null) => request<FeedbackState>(`${turnPath(id, turn)}/feedback`,
    { method: "POST", body: JSON.stringify({ verdict }) }),
  alternatives: (id: string, turn: string) => request<Alternatives>(`${turnPath(id, turn)}/alternatives`, { method: "POST", body: "{}" }),
  choose: (id: string, turn: string, layout: string) => request<FeedbackState>(`${turnPath(id, turn)}/choice`,
    { method: "POST", body: JSON.stringify({ layout }) }),
  presentation: () => request<PresentationState>("/conversations/genui/presentation"),
  keep: (version: number) => request<PresentationState>("/conversations/genui/presentation/keep", { method: "POST", body: JSON.stringify({ version }) }),
  undo: (version: number) => request<PresentationState>("/conversations/genui/presentation/undo", { method: "POST", body: JSON.stringify({ version }) }),
  reset: () => request<PresentationState & { removedFeedback: number }>("/conversations/genui/presentation/reset", { method: "POST", body: "{}" }),
  exportFeedback: (includeText: boolean) => request<Record<string, unknown>>(`/conversations/genui/feedback/export?includeText=${includeText ? 1 : 0}`),
};
export const conversationApi = {
  livePreference: (signal?: AbortSignal) => request<{ enabled: boolean; epoch: number }>("/live-memory", { signal }),
  setLivePreference: (enabled: boolean, expectedEpoch: number) => request<{ enabled: boolean; epoch: number }>("/live-memory",
    { method: "POST", body: JSON.stringify({ enabled, expectedEpoch }) }),
  prepare: (id: string, value: { utteranceId: string; revision: number; text: string; composing: boolean }, signal?: AbortSignal) =>
    request(`${path(id)}/preparation`, { method: "POST", body: JSON.stringify(value), signal }),
  preparation: (id: string, utterance: string, revision: number, signal?: AbortSignal) =>
    request<Preparation>(`${path(id)}/preparation?utteranceId=${encodeURIComponent(utterance)}&revision=${revision}`, { signal }),
  discardPreparation: (id: string, utteranceId: string) => request(`${path(id)}/preparation`,
    { method: "DELETE", body: JSON.stringify({ utteranceId }) }),
  attach: (id: string, value: { uploadKey: string; name: string; dataBase64: string }) =>
    request<ChatAttachment>(`${path(id)}/attachments`, { method: "POST", body: JSON.stringify(value) }),
  removeAttachment: (id: string, attachment: string) => request(`${path(id)}/attachments/${encodeURIComponent(attachment)}`,
    { method: "DELETE", body: "{}" }),
  recent: (signal?: AbortSignal) => request<{ items: ChatHeader[] }>("/conversations", { signal }),
  create: (createKey: string) => request<ChatHeader>("/conversations", { method: "POST", body: JSON.stringify({ createKey }) }),
  load: (id: string, signal?: AbortSignal) => request<ChatHistory>(path(id), { signal }),
  older: (id: string, before: number, signal?: AbortSignal) =>
    request<ChatHistory>(`${path(id)}?before=${before}`, { signal }),
  endSession: (id: string, expectedHistoryVersion: number) => request(`${path(id)}/end-session`,
    { method: "POST", body: JSON.stringify({ expectedHistoryVersion }) }),
  activity: (id: string) => request(`${path(id)}/activity`, { method: "POST", body: "{}" }),
  send: (id: string, value: SendRequest) => request<TurnStatus>(`${path(id)}/turns`, { method: "POST", body: JSON.stringify(value) }),
  turnStatus: (id: string, turn: string) => request<TurnStatus>(`${path(id)}/turns/${encodeURIComponent(turn)}`),
  stop: (id: string, turn: string) => request<TurnStatus>(`${path(id)}/turns/${encodeURIComponent(turn)}/stop`, { method: "POST", body: "{}" }),
  stream: (id: string, turn: string) => new EventSource(`${path(id)}/turns/${encodeURIComponent(turn)}/events`, { withCredentials: true }),
};
