import { useEffect, useRef, useState } from "react";
import { CARD_LAYOUTS } from "@/browser-voice/genui/layouts";
import { conversationApi as api, type CardLayout, type ChatAttachment, type ChatCardPart, type ChatHeader, type ChatTurn, type SendRequest, type TurnState } from "./api";
import { useLivePreparation } from "./useLivePreparation";

const activeTurn = (state: string) => state === "submitted" || state === "running";
const errorText = (error: unknown) => error instanceof Error ? error.message : "Chat request failed.";
/** Browsers report dropped/aborted connections as a bare TypeError ("Load failed" in Safari). */
const isNetworkError = (error: unknown) => error instanceof TypeError;
export const SELECTED_CHAT_KEY = "resono_vault_chat_selected";
const storedChat = () => { try { return sessionStorage.getItem(SELECTED_CHAT_KEY); } catch { return null; } };
const storeChat = (id: string | null) => { try { if (id) sessionStorage.setItem(SELECTED_CHAT_KEY, id); else sessionStorage.removeItem(SELECTED_CHAT_KEY); } catch { /* private mode */ } };
/** Retry idempotent reads across a transient network drop (page flips, mobile radio changes). */
async function retrying<T>(read: () => Promise<T>, signal: AbortSignal): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    try { return await read(); }
    catch (error) {
      if (signal.aborted || attempt >= 2 || !isNetworkError(error)) throw error;
      await new Promise(resolve => setTimeout(resolve, 600 * (attempt + 1)));
      if (signal.aborted) throw error;
    }
  }
}
const LAYOUTS: readonly string[] = CARD_LAYOUTS;
/** Shape check only; the server already validated content. Unknown layouts are dropped, never rendered. */
const isCardPart = (value: any): value is ChatCardPart => Boolean(value) && typeof value.cardId === "string"
  && Boolean(value.card) && LAYOUTS.includes(value.card.layout) && typeof value.card.fallbackText === "string"
  && Array.isArray(value.sources);

export function useConversation(active: boolean) {
  const [items, setItems] = useState<ChatHeader[]>([]);
  // Stay in the chat you were working in across page flips and reloads; logout clears it.
  const [selected, setSelected] = useState<string | null>(storedChat);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [attachments, setAttachments] = useState<(ChatAttachment & { conversation: string; preview?: string })[]>([]);
  const [uploading, setUploading] = useState(false);
  const attachmentRef = useRef(attachments);
  attachmentRef.current = attachments;
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [draft, setDraft] = useState("");
  const [version, setVersion] = useState(0);
  const [running, setRunning] = useState<string | null>(null);
  const [liveText, setLiveText] = useState("");
  const [liveCards, setLiveCards] = useState<ChatCardPart[]>([]);
  const [liveHint, setLiveHint] = useState<CardLayout[]>([]);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [retryable, setRetryable] = useState(false);
  const mounted = useRef(true);
  const drafts = useRef(new Map<string, string>());
  const sendLock = useRef(false);
  const uploadLock = useRef(false);
  const selectionEpoch = useRef(0);
  const createKey = useRef(crypto.randomUUID());
  const pending = useRef<{ conversation: string | null; request: SendRequest } | null>(null);
  const draftConversation = useRef<Promise<string> | null>(null);
  const activity = useRef({ id: "", at: 0 });
  function editDraft(value: string) {
    setDraft(value);
    // Text-free heartbeat is independent of Live Memory and never reviews drafts.
    if (active && selected && (activity.current.id !== selected || Date.now()-activity.current.at >= 15000)) {
      activity.current = { id: selected, at: Date.now() };
      void api.activity(selected).catch(() => {}); // No authority bypass or text fallback.
    }
  }
  async function ensureConversation() {
    if (selected) return selected;
    if (!draftConversation.current) draftConversation.current = api.create(createKey.current)
      .then(value => value.conversationId).catch(error => { draftConversation.current = null; throw error; });
    return draftConversation.current;
  }
  const preparation = useLivePreparation(active && !running && !sending && !loading && !attachments.length && !uploading, draft, selected, ensureConversation);
  useEffect(() => { mounted.current = true; return () => {
    mounted.current = false;
    for (const item of attachmentRef.current) { if (item.preview) URL.revokeObjectURL(item.preview); }
  }; }, []);

  useEffect(() => {
    if (!active) return;
    let current = true;
    const abort = new AbortController();
    void retrying(() => api.recent(abort.signal), abort.signal).then(value => { if (current) setItems(value.items); })
      .catch(error => { if (current && !abort.signal.aborted) setError(errorText(error)); });
    return () => { current = false; abort.abort(); };
  }, [active, reload]);

  useEffect(() => {
    if (!active || !selected) return;
    let current = true;
    const abort = new AbortController();
    setLoading(true);
    void retrying(() => api.load(selected, abort.signal), abort.signal).then(value => {
      if (!current) return;
      setTurns(value.turns); setNextBefore(value.nextBefore ?? null); setVersion(value.historyVersion);
      setRunning(value.turns.find(turn => activeTurn(turn.state))?.turnId ?? null);
      setLoading(false);
    }).catch(error => {
      if (!current || abort.signal.aborted) return;
      setLoading(false);
      if (isNetworkError(error)) { setError("Couldn't reach Vault. Check your connection and try again."); return; }
      // The remembered chat no longer exists here (deleted, other workspace): start fresh, quietly.
      storeChat(null); setSelected(null); setTurns([]);
    });
    return () => { current = false; abort.abort(); };
  }, [active, selected, reload]);

  useEffect(() => {
    if (!active || !selected || !running) return;
    const stream = api.stream(selected, running);
    let current = true, cursor = 0, answer = "";
    let cards: ChatCardPart[] = [];
    setLiveCards([]); setLiveHint([]);
    setStatus("Preparing response…");
    stream.addEventListener("conversation", event => {
      if (!current) return;
      try {
        const value = JSON.parse((event as MessageEvent).data);
        if (value.turnId !== running || !Number.isSafeInteger(value.sequence) || value.sequence <= cursor) return;
        cursor = value.sequence;
        if (value.kind === "text_delta" && typeof value.payload.text === "string") {
          answer += value.payload.text; setLiveText(answer); setStatus("Responding…");
        } else if (value.kind === "assistant_final" && typeof value.payload.text === "string") {
          answer = value.payload.text; setLiveText(answer);
        } else if (value.kind === "ui_hint" && Array.isArray(value.payload.layouts)) {
          setLiveHint(value.payload.layouts.filter((layout: string) => LAYOUTS.includes(layout)) as CardLayout[]);
        } else if (value.kind === "ui" && isCardPart(value.payload)) {
          cards = [...cards, { cardId: value.payload.cardId, card: value.payload.card, sources: value.payload.sources }];
          setLiveCards(cards);
        } else if (value.kind === "tool_status") {
          setStatus(`Tool ${value.payload.name}: ${value.payload.state}`);
        } else if (value.kind === "error") {
          setError(value.payload.code === "turn_interrupted" ? "Response stopped. Completed actions were not undone." : "Response failed. An action may already have completed; inspect history before trying again.");
        } else if (value.kind === "terminal") {
          current = false; stream.close();
          setTurns(previous => previous.map(turn => turn.turnId === running
            ? { ...turn, answer: answer || null, state: value.payload.state as TurnState, ...(cards.length ? { ui: cards } : {}) } : turn));
          setRunning(null); setStatus(""); setLiveCards([]); setLiveHint([]); setReload(value => value + 1);
        }
      } catch { setError("Invalid response event. Reopen the session to reload canonical history."); stream.close(); }
    });
    stream.addEventListener("unavailable", () => { if (current) setStatus("Stream busy; reconnecting…"); });
    stream.onerror = () => {
      if (!current) return;
      setStatus("Reconnecting to response…");
      // A dropped stream must not leave a finished reply looking stuck: ask the server directly.
      void api.turnStatus(selected, running).then(value => {
        if (current && !activeTurn(value.state)) {
          current = false; stream.close(); setRunning(null); setStatus(""); setLiveCards([]); setLiveHint([]);
          setReload(previous => previous + 1);
        }
      }).catch(() => {});
    };
    return () => { current = false; stream.close(); };
  }, [active, selected, running, reload]);

  function select(id: string | null) {
    if (sendLock.current || uploadLock.current || (id !== null && id === selected)) return;
    for (const item of attachments) {
      if (item.preview) URL.revokeObjectURL(item.preview);
      void api.removeAttachment(item.conversation,item.id).catch(() => {});
    }
    setAttachments([]);
    // Navigation never cancels a response. End only the previous idle segment;
    // its saved conversation remains resumable with a fresh segment.
    if (selected && selected !== id && !running && !loading && turns.length) {
      void api.endSession(selected, version).catch(() => {
        // History remains canonical/resumable on a stale-version or capacity
        // failure. Do not retry blindly against a different segment/history.
      });
    }
    preparation.clear(); draftConversation.current = null;
    selectionEpoch.current += 1;
    drafts.current.set(selected ?? "new", draft);
    setSelected(id); storeChat(id); setDraft(id === null ? "" : drafts.current.get(id) ?? "");
    setTurns([]); setNextBefore(null); setVersion(0); setRunning(null); setLiveText(""); setLiveCards([]); setLiveHint([]); setStatus(""); setError(null);
    pending.current = null; setRetryable(false);
    if (id === null) createKey.current = crypto.randomUUID();
  }

  /** ``text`` sends a card choice (for example a tapped option) instead of the draft; the draft is kept. */
  async function send(retry = false, text?: string) {
    const input = text ?? draft;
    if (sendLock.current || running || loading || uploadLock.current || (!retry && (retryable || !input.trim()))) return;
    if (text !== undefined && attachments.length) return;
    preparation.clear(false);
    if (!retry && (input.includes("\0") || new TextEncoder().encode(input).length > 65536)) {
      setError("Message must be valid text within 65536 UTF-8 bytes. Shorten it before sending.");
      return;
    }
    sendLock.current = true; setSending(true); setError(null);
    const work = retry ? pending.current : {
      conversation: selected, request: { submissionKey: crypto.randomUUID(), input, expectedHistoryVersion: version, ...(attachments.length ? { attachmentIds: attachments.map(a => a.id) } : {}) },
    };
    if (!work) { sendLock.current = false; setSending(false); return; }
    pending.current = work;
    try {
      if (!work.conversation) work.conversation = await ensureConversation();
      if (!mounted.current) return;
      const value = await api.send(work.conversation, work.request);
      if (!mounted.current) return;
      setSelected(work.conversation); storeChat(work.conversation); setVersion(value.historyVersion);
      if (text === undefined) setDraft(previous => previous === work.request.input ? "" : previous);
      for (const item of attachments) { if (item.preview) URL.revokeObjectURL(item.preview); }
      setAttachments([]);
      if (text === undefined) drafts.current.delete(selected ?? "new");
      setTurns(previous => previous.some(turn => turn.turnId === value.turnId) ? previous : [...previous, {
        turnId: value.turnId, input: value.input, answer: null, state: value.state,
      }]);
      setRunning(activeTurn(value.state) ? value.turnId : null);
      setLiveText(""); setRetryable(false); pending.current = null; setReload(value => value + 1);
    } catch (error) {
      if (mounted.current) { setError(errorText(error)); setRetryable(true); }
    } finally {
      sendLock.current = false;
      if (mounted.current) setSending(false);
    }
  }

  async function attachFiles(files: File[]) {
    if (uploadLock.current || sendLock.current || retryable || files.length === 0) return;
    if (files.length + attachments.length > 4) { setError("Attach at most four files per message."); return; }
    if (files.some(file => file.size > 5 * 1024 * 1024 || file.size === 0)) {
      setError("Each attachment must contain 1 byte to 5 MiB."); return;
    }
    const epoch = selectionEpoch.current;
    uploadLock.current = true;
    setUploading(true); setError(null); preparation.clear();
    try {
      const conversation = await ensureConversation();
      for (const file of files) {
        const encoded = await new Promise<string>((resolve,reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(new Error("File could not be read."));
          reader.onload = () => resolve(String(reader.result).split(",")[1]);
          reader.readAsDataURL(file);
        });
        const value = await api.attach(conversation,{ uploadKey: crypto.randomUUID(), name: file.name, dataBase64: encoded });
        if (!mounted.current || epoch !== selectionEpoch.current) {
          await api.removeAttachment(conversation,value.id); return;
        }
        setAttachments(current => [...current,{...value,conversation,
          preview: value.mime.startsWith("image/") ? URL.createObjectURL(file) : undefined}]);
      }
    } catch (error) { if (mounted.current && epoch === selectionEpoch.current) setError(errorText(error)); }
    finally { uploadLock.current = false; if (mounted.current) setUploading(false); }
  }
  async function removeAttachment(id: string) {
    if (sending || retryable) return;
    const item = attachments.find(a => a.id === id);
    if (!item) return;
    try {
      await api.removeAttachment(item.conversation,id);
      if (item.preview) URL.revokeObjectURL(item.preview);
      setAttachments(current => current.filter(a => a.id !== id)); preparation.clear();
    } catch (error) { setError(errorText(error)); }
  }
  async function loadOlder() {
    if (!selected || nextBefore === null || loadingOlder) return;
    const epoch = selectionEpoch.current;
    const conversation = selected;
    setLoadingOlder(true);
    try {
      const page = await api.older(conversation, nextBefore);
      if (!mounted.current || epoch !== selectionEpoch.current) return;
      setTurns(current => [...page.turns.filter(t => !current.some(c => c.turnId === t.turnId)), ...current]);
      setNextBefore(page.nextBefore ?? null);
    } catch (error) {
      if (mounted.current && epoch === selectionEpoch.current) setError(errorText(error));
    } finally { if (mounted.current) setLoadingOlder(false); }
  }
  async function stop() {
    if (!selected || !running) return;
    const epoch = selectionEpoch.current;
    try { await api.stop(selected, running); if (mounted.current && epoch === selectionEpoch.current) setStatus("Stopping…"); }
    catch (error) { if (mounted.current && epoch === selectionEpoch.current) setError(errorText(error)); }
  }
  return { items, selected, turns, draft, setDraft: editDraft, running, liveText, liveCards, liveHint, choose: (text: string) => send(false, text), status, loading, sending, error,
    preparation, retryable, select, send, stop, attachments, uploading, attachFiles, removeAttachment, nextBefore, loadingOlder, loadOlder, refresh: () => setReload(value => value + 1) };
}
