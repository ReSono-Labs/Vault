import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AssistantRuntimeProvider, MessagePrimitive, ThreadPrimitive, useExternalStoreRuntime,
  type ThreadMessageLike } from "@assistant-ui/react";
import { BrowserVoiceMicrophoneIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";
import { useConversation } from "./useConversation";
import { useChatViewport } from "./useChatViewport";
import { LivePreparationPanel } from "./LivePreparationPanel";
import { genuiApi, type ChatCardPart, type PresentationState } from "./api";
import { CardActionsContext, VaultCardPart, VaultCardSkeletonPart } from "@/browser-voice/genui/VaultCard";
import { AnswerFeedback, FeedbackExport, PresentationNoticeCard } from "@/browser-voice/genui/Feedback";

const PresentationRefresh = createContext<() => void>(() => {});
function FeedbackPart({ data }: { data: unknown }) {
  const value = data as { conversationId: string; turnId: string };
  const refresh = useContext(PresentationRefresh);
  return <AnswerFeedback conversationId={value.conversationId} turnId={value.turnId} onPresentationChanged={refresh} />;
}
import "./conversation.css";

// Registered generative-UI parts; any other data part name renders nothing.
// Assistant text stays in its chat bubble; cards and feedback render as their own entities below it.
function BubbleText({ text }: { text: string }) {
  return text ? <div className="vault-chat-bubble"><span className="vault-chat-message-author">Vault</span>{text}</div> : null;
}
const PARTS = { Text: BubbleText, data: { by_name: { "vault-card": VaultCardPart, "vault-card-skeleton": VaultCardSkeletonPart,
  "vault-feedback": FeedbackPart } } };
function Message({ user = false }: { user?: boolean }) {
  if (user) return <MessagePrimitive.Root className="vault-chat-message is-user">
    <span className="vault-chat-message-author">You</span>
    <MessagePrimitive.Content />
  </MessagePrimitive.Root>;
  return <MessagePrimitive.Root className="vault-chat-message is-assistant">
    <MessagePrimitive.Content components={PARTS} />
  </MessagePrimitive.Root>;
}
type Part = { type: "text"; text: string } | { type: `data-${string}`; data: unknown };
function assistantParts(text: string | null, cards: ChatCardPart[] | undefined, skeleton?: string,
  feedback?: { conversationId: string; turnId: string }): Part[] {
  const parts: Part[] = [];
  if (text) parts.push({ type: "text", text });
  for (const card of cards ?? []) parts.push({ type: "data-vault-card", data: card });
  if (skeleton) parts.push({ type: "data-vault-card-skeleton", data: { layout: skeleton } });
  if (feedback) parts.push({ type: "data-vault-feedback", data: feedback });
  return parts;
}
function UserMessage() { return <Message user />; }

export function ChatPanel({ active, voiceActive, voiceBusy, onToggleVoice }: {
  active: boolean; voiceActive: boolean; voiceBusy: boolean; onToggleVoice: () => void;
}) {
  const chat = useConversation(active);
  const viewportRef = useChatViewport(active);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerRef = useRef<HTMLDialogElement>(null);
  // Chat history lives in the app's top bar beside notifications, only while Chat is open.
  const [headerSlot, setHeaderSlot] = useState<HTMLElement | null>(null);
  useEffect(() => { setHeaderSlot(document.getElementById("vault-header-slot")); }, []);
  const historyButton = active ? <button type="button" className="vault-chat-icon-button vault-chat-history-button"
    aria-label="Open chat options" aria-haspopup="dialog" aria-expanded={drawerOpen} aria-controls="vault-chat-options"
    onClick={() => setDrawerOpen(true)}>
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path d="M4 6h16M4 12h16M4 18h10" /></svg>
  </button> : null;
  useEffect(() => { if (!active) setDrawerOpen(false); }, [active]);
  useEffect(() => {
    const drawer = drawerRef.current;
    if (!drawer) return;
    if (drawerOpen && !drawer.open) drawer.showModal();
    if (!drawerOpen && drawer.open) drawer.close();
  }, [drawerOpen]);
  const messages = useMemo<ThreadMessageLike[]>(() => {
    const result: ThreadMessageLike[] = [];
    for (const turn of chat.turns) {
      result.push({ id: `${turn.turnId}-user`, role: "user", content: [{ type: "text", text: turn.input + (turn.attachments?.length ? "\n\nAttachments: " + turn.attachments.map(a => `${a.name} (${a.coverage})`).join(", ") : "") }] });
      if (turn.answer || turn.ui?.length) result.push({ id: `${turn.turnId}-answer`, role: "assistant",
        content: assistantParts(turn.answer, turn.ui, undefined, turn.state === "completed" && chat.selected
          ? { conversationId: chat.selected, turnId: turn.turnId } : undefined) });
    }
    // A predicted layout shows a skeleton until the first real card streams in.
    const skeleton = chat.liveCards.length ? undefined : chat.liveHint[0];
    if (chat.running && (chat.liveText || chat.liveCards.length || skeleton)) result.push({ id: `${chat.running}-live`,
      role: "assistant", content: assistantParts(chat.liveText, chat.liveCards, skeleton) });
    return result;
  }, [chat.turns, chat.running, chat.liveText, chat.liveCards, chat.liveHint, chat.selected]);
  const [presentation, setPresentation] = useState<PresentationState | null>(null);
  const refreshPresentation = useCallback(() => {
    // The tuner runs in the background after a choice; look again shortly.
    for (const delay of [0, 2500, 8000]) setTimeout(() => {
      genuiApi.presentation().then(setPresentation).catch(() => {});
    }, delay);
  }, []);
  useEffect(() => { if (active) refreshPresentation(); }, [active, refreshPresentation]);
  const cardActions = useMemo(() => ({ choose: (text: string) => { void chat.choose(text); },
    busy: Boolean(chat.running) || chat.sending || chat.loading }), [chat.choose, chat.running, chat.sending, chat.loading]);
  const runtime = useExternalStoreRuntime({ messages, isRunning: Boolean(chat.running),
    convertMessage: (message: ThreadMessageLike) => message,
    onNew: async () => { await chat.send(); }, onCancel: chat.stop });
  return <section ref={viewportRef} className="vault-chat" hidden={!active} aria-label="Chat"
    onDragOver={event => event.preventDefault()} onDrop={event => {
      event.preventDefault(); void chat.attachFiles(Array.from(event.dataTransfer.files));
    }}>
    <dialog ref={drawerRef} id="vault-chat-options" className="vault-chat-drawer"
      aria-labelledby="vault-chat-options-title" onClose={() => setDrawerOpen(false)}>
      <div className="vault-chat-drawer-content">
      <header className="vault-chat-drawer-header"><h2 id="vault-chat-options-title">Your chats</h2>
        <button type="button" autoFocus className="vault-chat-icon-button" aria-label="Close chat options"
          onClick={() => setDrawerOpen(false)}>✕</button></header>
    <aside className="vault-chat-sessions" aria-label="Chat sessions">
      <button type="button" disabled={chat.sending} onClick={() => { void chat.select(null); setDrawerOpen(false); }}>New Chat</button>
      <button type="button" className="vault-chat-memory-toggle" role="switch" aria-label="Live Memory"
        disabled={!chat.preparation.preference || chat.preparation.preferenceBusy}
        aria-checked={chat.preparation.preference?.enabled ?? false} onClick={() => void chat.preparation.toggle()}>
        <span>Live Memory<small>{chat.preparation.preference?.enabled ? "On" : "Off"}</small></span>
        <span className="vault-chat-switch-track" aria-hidden="true"><span /></span></button>
      {chat.preparation.preferenceError ? <small role="alert">{chat.preparation.preferenceError}</small> : null}
      <details className="vault-chat-presentation">
        <summary>Presentation learning</summary>
        <FeedbackExport />
        <button type="button" onClick={() => {
          if (window.confirm("Forget all presentation feedback and learned format preferences for this workspace?"))
            void genuiApi.reset().then(setPresentation).catch(() => {});
        }}>Reset learned formats</button>
      </details>
      <h3>Sessions</h3>
        {chat.items.length === 0 ? <p>No saved chats yet.</p> : chat.items.map(item =>
          <button key={item.conversationId} type="button" disabled={chat.sending}
            aria-current={chat.selected === item.conversationId ? "page" : undefined}
            onClick={() => { void chat.select(item.conversationId); setDrawerOpen(false); }}>{item.title || "Untitled chat"}</button>)}

    </aside>
      </div>
    </dialog>
    <div className="vault-chat-main">
      <h1 className="vault-visually-hidden">Chat</h1>
      {historyButton && !headerSlot ? <div className="vault-chat-header">{historyButton}</div> : null}
      {historyButton && headerSlot ? createPortal(historyButton, headerSlot) : null}
      <CardActionsContext.Provider value={cardActions}>
      <PresentationRefresh.Provider value={refreshPresentation}>
      <AssistantRuntimeProvider runtime={runtime}>
        <ThreadPrimitive.Root className="vault-chat-thread">
          <ThreadPrimitive.Viewport className="vault-chat-scroll">
            {chat.nextBefore != null ? <button type="button" disabled={chat.loadingOlder}
              onClick={async event => {
                const viewport = event.currentTarget.parentElement;
                const height = viewport?.scrollHeight ?? 0;
                const top = viewport?.scrollTop ?? 0;
                await chat.loadOlder();
                requestAnimationFrame(() => { if (viewport) viewport.scrollTop = top + viewport.scrollHeight - height; });
              }}>{chat.loadingOlder ? "Loading…" : "Load earlier messages"}</button> : null}
            {messages.length === 0 ? <p className="vault-chat-empty">Ask your Vault a question.</p> : null}
            <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage: Message }} />
          </ThreadPrimitive.Viewport>
          <ThreadPrimitive.ScrollToBottom className="browser-voice-pill vault-chat-jump">Latest message</ThreadPrimitive.ScrollToBottom>
        </ThreadPrimitive.Root>
      </AssistantRuntimeProvider>
      </PresentationRefresh.Provider>
      </CardActionsContext.Provider>
      {presentation ? <PresentationNoticeCard state={presentation} onDone={setPresentation} /> : null}
      <div className="vault-chat-status" role="status">{chat.loading ? "Loading chat…" : chat.sending ? "Sending…" : chat.status}</div>
      <LivePreparationPanel value={chat.preparation.value} />
      {chat.error ? <div className="vault-chat-error" role="alert"><p>{chat.error}</p>
        {chat.retryable ? <button type="button" disabled={chat.sending} onClick={() => void chat.send(true)}>Retry same submission</button> : null}
        <button type="button" onClick={chat.refresh}>Reload history</button>
      </div> : null}
      {chat.attachments?.length ? <aside aria-label="Attachments" className="vault-chat-attachments">
        {chat.attachments.map(item => <div key={item.id}>
          {item.preview ? <img src={item.preview} alt={item.name} width={64} height={64} /> : null}
          <span>{item.name} · {item.coverage.replaceAll("_", " ")}</span>
          <button type="button" disabled={chat.sending || chat.retryable} onClick={() => void chat.removeAttachment(item.id)}
            aria-label={`Remove ${item.name}`}>Remove</button>
        </div>)}
      </aside> : null}
      {chat.uploading ? <p role="status">Preparing attachment…</p> : null}
      <form className="vault-chat-composer" onSubmit={event => { event.preventDefault(); void chat.send(); }}>
        <textarea aria-label="Message your Vault" placeholder="Message your Vault…" rows={1} value={chat.draft}
          onCompositionStart={() => chat.preparation.setComposing(true)}
          onCompositionEnd={() => chat.preparation.setComposing(false)}
          onPaste={event => {
            const files = Array.from(event.clipboardData.files);
            if (files.length) { event.preventDefault(); void chat.attachFiles(files); }
          }}
          onChange={event => chat.setDraft(event.target.value)} onKeyDown={event => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault(); void chat.send();
            }
          }} />
        <div className="vault-chat-composer-actions">
          <label className="vault-chat-attach">Attach
            <input type="file" multiple accept=".png,.jpg,.jpeg,.webp,.txt,.md,.csv,.pdf,.docx"
              disabled={chat.uploading || chat.sending || chat.retryable}
              onChange={event => { void chat.attachFiles(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = ""; }} />
          </label>
          <button hidden type="button" className="vault-chat-microphone" aria-label={voiceActive ? "Stop Voice" : "Start Voice"}
            aria-pressed={voiceActive} disabled={voiceBusy} onClick={onToggleVoice}><BrowserVoiceMicrophoneIcon /></button>
          {chat.running ? <button type="button" onClick={() => void chat.stop()}>Stop response</button>
            : <button type="submit" disabled={chat.sending || chat.loading || chat.uploading || chat.retryable || !chat.draft.trim()}>Send</button>}
        </div>
      </form>
      <p className="vault-chat-footnote">Use the Voice page for voice conversations. Chat uses your configured text model.</p>
    </div>
  </section>;
}
