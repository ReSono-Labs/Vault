import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { genuiApi, type Alternatives, type PresentationState } from "@/browser-voice/conversation/api";
import { LAYOUT_LABELS, type CardLayout } from "./layouts";
import { VaultCardView } from "./VaultCard";

const label = (layout: string) => layout === "text" ? "Text" : LAYOUT_LABELS[layout as CardLayout] ?? layout;

/** 👍/👎 under a finished answer. 👎 opens "How can I do better?". */
export function AnswerFeedback({ conversationId, turnId, onPresentationChanged }: {
  conversationId: string; turnId: string; onPresentationChanged?: () => void;
}) {
  const [verdict, setVerdict] = useState<"up" | "down" | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function vote(next: "up" | "down") {
    const value = verdict === next ? null : next;
    setError(null);
    try { setVerdict((await genuiApi.feedback(conversationId, turnId, value)).verdict); }
    catch { setError("Feedback could not be saved."); return; }
    setOpen(value === "down");
  }
  return <div className="vault-feedback">
    <div className="vault-feedback-bar" role="group" aria-label="Rate this answer">
      <button type="button" aria-pressed={verdict === "up"} aria-label="Good answer" onClick={() => void vote("up")}>👍</button>
      <button type="button" aria-pressed={verdict === "down"} aria-label="Could be better" onClick={() => void vote("down")}>👎</button>
      {!open ? <button type="button" className="vault-feedback-better" onClick={() => setOpen(true)}>How can I do better?</button> : null}
      {error ? <small role="alert">{error}</small> : null}
    </div>
    {open ? <BetterCarousel conversationId={conversationId} turnId={turnId} onClose={() => setOpen(false)}
      onChosen={() => { setVerdict("down"); onPresentationChanged?.(); }} /> : null}
  </div>;
}

/** The same answer shown in other layouts; swipe (touch) or ←/→, then "Use this one". */
export function BetterCarousel({ conversationId, turnId, onClose, onChosen }: {
  conversationId: string; turnId: string; onClose: () => void; onChosen: (layout: string) => void;
}) {
  const [data, setData] = useState<Alternatives | null>(null);
  const [index, setIndex] = useState(0);
  const [state, setState] = useState<"loading" | "ready" | "saving" | "saved" | "error">("loading");
  const touch = useRef<number | null>(null);
  useEffect(() => {
    let current = true;
    // Previews are cached on the server as soon as they finish, so a dropped slow request is retried.
    const load = (attempt: number): Promise<void> => genuiApi.alternatives(conversationId, turnId)
      .then(value => { if (current) { setData(value); setState("ready"); } })
      .catch(() => attempt < 3 && current ? new Promise<void>(resolve => setTimeout(resolve, 4000)).then(() => load(attempt + 1))
        : void (current && setState("error")));
    void load(0);
    return () => { current = false; };
  }, [conversationId, turnId]);
  const options = data?.previews ?? [];
  const count = options.length;
  const go = (step: number) => count && setIndex(value => (value + step + count) % count);
  const onKey = (event: KeyboardEvent) => {
    if (event.key === "ArrowRight") { event.preventDefault(); go(1); }
    if (event.key === "ArrowLeft") { event.preventDefault(); go(-1); }
  };
  async function choose() {
    const option = options[index];
    if (!option) return;
    setState("saving");
    try { await genuiApi.choose(conversationId, turnId, option.layout); setState("saved"); onChosen(option.layout); }
    catch { setState("error"); }
  }
  return <section className="vault-better" aria-label="How can I do better?" aria-roledescription="carousel">
    <header><h3>How can I do better?</h3><button type="button" aria-label="Close" onClick={onClose}>✕</button></header>
    {state === "loading" ? <p role="status" className="vault-better-status">Trying other formats… this can take up to half a minute.</p> : null}
    {state === "error" ? <p role="alert" className="vault-better-status">Other formats are unavailable right now.</p> : null}
    {data && !count ? <p className="vault-better-status">This answer already uses the best fit I can find.</p> : null}
    {data && count ? <>
      <p className="vault-better-lead">Same answer, other formats. Pick the one that works best for you.</p>
      <div className="vault-better-stage" tabIndex={0} onKeyDown={onKey} aria-live="polite"
        onTouchStart={event => { touch.current = event.touches[0].clientX; }}
        onTouchEnd={event => {
          if (touch.current === null) return;
          const delta = event.changedTouches[0].clientX - touch.current;
          touch.current = null;
          if (Math.abs(delta) > 40) go(delta < 0 ? 1 : -1);
        }}>
        <div className="vault-better-slide" role="group" aria-roledescription="slide"
          aria-label={`${index + 1} of ${count}: ${label(options[index].layout)}`} key={index}>
          <span className="vault-better-tag">{label(options[index].layout)}</span>
          {options[index].card
            ? <VaultCardView part={{ cardId: `preview-${index}`, card: options[index].card!, sources: [] }} />
            : <p className="vault-better-text">{data.current.text}</p>}
        </div>
      </div>
      <div className="vault-better-controls">
        <button type="button" aria-label="Previous format" onClick={() => go(-1)} disabled={count < 2}>←</button>
        <span className="vault-better-dots" aria-hidden="true">{options.map((_, dot) =>
          <i key={dot} className={dot === index ? "is-active" : ""} />)}</span>
        <button type="button" aria-label="Next format" onClick={() => go(1)} disabled={count < 2}>→</button>
      </div>
      <label className="vault-better-check">
        <input type="checkbox" checked={state === "saved"} disabled={state === "saving" || state === "saved"}
          onChange={() => void choose()} />
        <span>{state === "saved" ? `Got it — ${label(options[index].layout)} it is.` : `Use ${label(options[index].layout)} for answers like this`}</span>
      </label>
    </> : null}
  </section>;
}

/** Shown once after the tuner changes presentation: what changed, an example, Keep or Undo. */
export function PresentationNoticeCard({ state, onDone }: { state: PresentationState; onDone: (next: PresentationState) => void }) {
  const notice = state.notice;
  const [busy, setBusy] = useState(false);
  if (!state.noticePending || !notice) return null;
  async function act(kind: "keep" | "undo") {
    setBusy(true);
    try { onDone(await (kind === "keep" ? genuiApi.keep(notice!.version) : genuiApi.undo(notice!.version))); }
    finally { setBusy(false); }
  }
  return <section className="vault-notice" aria-label="Presentation update">
    <span className="vault-notice-eyebrow">Learned from your feedback · {notice.events} answers</span>
    <p>{notice.summary}</p>
    {notice.example ? <VaultCardView part={{ cardId: "notice-example", card: notice.example, sources: [] }} /> : null}
    <div className="vault-notice-actions">
      <button type="button" className="is-primary" disabled={busy} onClick={() => void act("keep")}>Keep</button>
      <button type="button" disabled={busy} onClick={() => void act("undo")}>Undo</button>
    </div>
  </section>;
}

/** Beta export: preview first, request text opt-in, download only on an explicit click. */
export function FeedbackExport() {
  const [includeText, setIncludeText] = useState(false);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function load(withText: boolean) {
    setError(null);
    try { setPreview(await genuiApi.exportFeedback(withText)); } catch { setError("Export is unavailable."); }
  }
  useEffect(() => { void load(includeText); }, [includeText]);
  const json = preview ? JSON.stringify(preview, null, 2) : "";
  const items = Array.isArray(preview?.items) ? (preview!.items as unknown[]).length : 0;
  function download() {
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `vault-presentation-feedback-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click(); URL.revokeObjectURL(url);
  }
  return <section className="vault-export" aria-label="Share presentation feedback">
    <h3>Share presentation feedback</h3>
    <p>Nothing leaves this device unless you download this file and send it. It contains the formats Vault predicted,
      showed and you chose{includeText ? ", plus the text of your requests" : ""}.</p>
    <label><input type="checkbox" checked={includeText} onChange={event => setIncludeText(event.target.checked)} />
      Include my request text</label>
    {error ? <p role="alert">{error}</p> : null}
    {preview ? <>
      <pre className="vault-export-preview" tabIndex={0} aria-label="Export preview">{json}</pre>
      <button type="button" onClick={download} disabled={!items}>Download {items} item{items === 1 ? "" : "s"}</button>
    </> : null}
  </section>;
}
