import { useEffect, useMemo, useRef, useState } from "react";
import { AssistantRuntimeProvider, MessagePrimitive, ThreadPrimitive, useExternalStoreRuntime,
  type ThreadMessageLike } from "@assistant-ui/react";
import { BrowserVoiceMicrophoneIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";
import { useConversation } from "./useConversation";
import { useChatViewport } from "./useChatViewport";
import { LivePreparationPanel } from "./LivePreparationPanel";
import "./conversation.css";

function Message({ user = false }: { user?: boolean }) {
  return <MessagePrimitive.Root className={`vault-chat-message${user ? " is-user" : ""}`}>
    <span className="vault-chat-message-author">{user ? "You" : "Vault"}</span>
    <MessagePrimitive.Content />
  </MessagePrimitive.Root>;
}
function UserMessage() { return <Message user />; }

export function ChatPanel({ active, voiceActive, voiceBusy, onToggleVoice }: {
  active: boolean; voiceActive: boolean; voiceBusy: boolean; onToggleVoice: () => void;
}) {
  const chat = useConversation(active);
  const viewportRef = useChatViewport(active);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerRef = useRef<HTMLDialogElement>(null);
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
      if (turn.answer) result.push({ id: `${turn.turnId}-answer`, role: "assistant", content: [{ type: "text", text: turn.answer }] });
    }
    if (chat.running && chat.liveText) result.push({ id: `${chat.running}-live`, role: "assistant",
      content: [{ type: "text", text: chat.liveText }] });
    return result;
  }, [chat.turns, chat.running, chat.liveText]);
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
      <h3>Sessions</h3>
        {chat.items.length === 0 ? <p>No saved chats yet.</p> : chat.items.map(item =>
          <button key={item.conversationId} type="button" disabled={chat.sending}
            aria-current={chat.selected === item.conversationId ? "page" : undefined}
            onClick={() => { void chat.select(item.conversationId); setDrawerOpen(false); }}>{item.title || "Untitled chat"}</button>)}

    </aside>
      </div>
    </dialog>
    <div className="vault-chat-main">
      <header className="vault-chat-header"><h1>Chat</h1>
        <button type="button" className="vault-chat-icon-button" aria-label="Open chat options"
          aria-haspopup="dialog" aria-expanded={drawerOpen} aria-controls="vault-chat-options"
          onClick={() => setDrawerOpen(true)}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <rect x="3" y="4" width="18" height="16" rx="3" /><path d="M15 4v16M18 9h.01M18 12h.01M18 15h.01" />
          </svg>
        </button></header>
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
