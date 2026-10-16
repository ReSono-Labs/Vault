import { createContext, useContext, useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";
import type { CardItem, CardLayout, ChatCardPart, VaultCard } from "@/browser-voice/conversation/api";
import "./genui.css";

/**
 * Vault's registered card components. Cards are server-validated data rendered as React text
 * (never HTML); the only interaction is sending a new user message. All colour, radius and
 * surface decisions come from theme tokens in genui.css, so switching themes is a single
 * `data-genui-theme` attribute on any ancestor.
 */
export type CardActions = { choose?: (text: string) => void; busy?: boolean };
export const CardActionsContext = createContext<CardActions>({});

const SOURCE_LABELS: Record<string, string> = { web_search: "Web", memory_lookup: "Memory", contacts_search: "Contacts" };
function sourceLabel(name: string) {
  if (SOURCE_LABELS[name]) return SOURCE_LABELS[name];
  const head = name.split(/[_.]/)[0];
  return head ? head.charAt(0).toUpperCase() + head.slice(1) : name;
}
/** Stable per-text variation for generated media art (no images are fetched). */
function seed(text = "") {
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) hash = (hash * 31 + text.charCodeAt(index)) | 0;
  return Math.abs(hash);
}
const art = (text?: string) => ({ "--g-seed": `${seed(text) % 360}deg`, "--g-seed-x": `${20 + (seed(text) % 60)}%` }) as CSSProperties;

const prefersMotion = () => typeof window !== "undefined" && typeof window.matchMedia === "function"
  && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Counts a displayed number up from zero once, keeping its prefix, suffix and decimals ("$12.4k", "165.65"). */
function CountUp({ value }: { value?: string | number }) {
  const text = value === undefined ? "" : String(value);
  const match = /^([^\d-]*)(-?[\d,]*\.?\d+)(.*)$/.exec(text);
  const [shown, setShown] = useState(match && prefersMotion() ? 0 : null as number | null);
  useEffect(() => {
    if (!match || !prefersMotion()) return;
    const target = Number(match[2].replace(/,/g, ""));
    let frame = 0; const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 900);
      setShown(target * (1 - Math.pow(1 - t, 3)));
      if (t < 1) frame = requestAnimationFrame(tick); else setShown(null);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [text]);
  if (!match || shown === null) return <>{text}</>;
  const decimals = (match[2].split(".")[1] ?? "").length;
  const grouped = match[2].includes(",");
  const body = shown.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: grouped });
  return <span aria-label={text}>{match[1]}{body}{match[3]}</span>;
}

const STATE_LABEL: Record<NonNullable<CardItem["state"]>, string> = { done: "Done", needs_you: "Needs you", optional: "Optional", pending: "Pending" };
const TREND_ICON: Record<NonNullable<CardItem["trend"]>, string> = { up: "▲", down: "▼", flat: "■" };

function Icon({ name }: { name: "check" | "dot" | "clock" | "pin" | "star" | "arrow" }) {
  const paths = {
    check: <path d="m5 12.5 4.2 4.2L19 7" />, dot: <circle cx="12" cy="12" r="3.5" />,
    clock: <><circle cx="12" cy="12" r="8" /><path d="M12 7.5V12l3 2" /></>,
    pin: <path d="M12 21s-6-5.6-6-11a6 6 0 0 1 12 0c0 5.4-6 11-6 11Z M12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" />,
    star: <path d="m12 4 2.4 5 5.4.6-4 3.7 1.1 5.3L12 16l-4.9 2.6 1.1-5.3-4-3.7 5.4-.6Z" />,
    arrow: <path d="M7 17 17 7M9 7h8v8" />,
  };
  return <svg className="g-icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}

// ── layouts ────────────────────────────────────────────────────────

function Timeline({ card }: { card: VaultCard }) {
  return <ol className="g-timeline">{card.items?.map((item, index) =>
    <li key={index} className={item.state ? `is-${item.state}` : ""}>
      <time>{item.time}</time>
      <span className="g-tile" aria-hidden="true"><Icon name={item.state === "done" ? "check" : item.state === "needs_you" ? "dot" : "clock"} /></span>
      <span className="g-grow"><b>{item.title}</b>{item.detail ? <small>{item.detail}</small> : null}</span>
      {item.state ? <em className="g-pill">{STATE_LABEL[item.state]}</em> : null}
    </li>)}</ol>;
}

function Options({ card }: { card: VaultCard }) {
  const { choose, busy } = useContext(CardActionsContext);
  return <div className="g-rail" role="group" aria-label={card.title ?? "Options"}>
    {card.items?.map((item, index) =>
      <button key={index} type="button" className="g-mini" disabled={!choose || busy} onClick={() => choose?.(item.title ?? "")}>
        <span className="g-media" style={art(item.title)} aria-hidden="true"><span className="g-badge">{index + 1}</span></span>
        <span className="g-mini-body"><b>{item.title}</b>{item.detail ? <small>{item.detail}</small> : null}</span>
      </button>)}
  </div>;
}

function Checklist({ card }: { card: VaultCard }) {
  const done = card.items?.filter(item => item.done).length ?? 0;
  return <>
    <ul className="g-checklist">{card.items?.map((item, index) =>
      <li key={index} className={item.done ? "is-done" : ""}>
        <span className="g-check" aria-hidden="true">{item.done ? <Icon name="check" /> : null}</span>
        <span>{item.text}</span><span className="g-sr">{item.done ? " (done)" : " (open)"}</span>
      </li>)}</ul>
    <div className="g-progress" aria-hidden="true"><i style={{ width: `${(done / Math.max(card.items?.length ?? 1, 1)) * 100}%` }} /></div>
  </>;
}

function Comparison({ card }: { card: VaultCard }) {
  return <div className="g-compare" style={{ "--g-cols": card.columns?.length ?? 2 } as CSSProperties}>
    <div className="g-compare-head" role="row"><span />{card.columns?.map((column, index) =>
      <span key={index} className="g-compare-name" role="columnheader"><i style={art(column)} aria-hidden="true" />{column}</span>)}</div>
    <table className="g-sr-table"><thead><tr><td />{card.columns?.map((c, i) => <th key={i} scope="col">{c}</th>)}</tr></thead>
      <tbody>{card.rows?.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) =>
        cellIndex === 0 ? <th key={cellIndex} scope="row">{cell}</th> : <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table>
    {card.rows?.map((row, index) => <div key={index} className="g-compare-row" aria-hidden="true">
      <span className="g-compare-attr">{row[0]}</span>{row.slice(1).map((cell, cellIndex) => <span key={cellIndex}>{cell}</span>)}
    </div>)}
  </div>;
}

function Table({ card }: { card: VaultCard }) {
  return <div className="g-table-wrap"><table className="g-table">
    <thead><tr>{card.columns?.map((column, index) => <th key={index} scope="col">{column}</th>)}</tr></thead>
    <tbody>{card.rows?.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody>
  </table></div>;
}

function Metrics({ card }: { card: VaultCard }) {
  const [hero, ...rest] = card.items ?? [];
  if (!hero) return null;
  const metric = (item: CardItem, big: boolean, index: number) => <div key={index} className={big ? "g-metric is-hero" : "g-metric"}>
    <dt>{item.label}</dt>
    <dd><strong>{big ? <CountUp value={item.value} /> : item.value}</strong>{item.trend ? <span className={`g-trend is-${item.trend}`} aria-label={item.trend}>{TREND_ICON[item.trend]}</span> : null}
      {item.detail ? <small>{item.detail}</small> : null}</dd>
  </div>;
  return <dl className="g-metrics">{metric(hero, true, 0)}{rest.map((item, index) => metric(item, false, index + 1))}</dl>;
}

function Chart({ card }: { card: VaultCard }) {
  const items = card.items ?? [];
  const amounts = items.map(item => item.amount ?? 0);
  const max = Math.max(...amounts), min = Math.min(...amounts, card.chartKind === "bar" ? 0 : Infinity);
  const span = max - min || 1;
  const width = 300, height = 120;
  const y = (amount: number) => height - 10 - ((amount - min) / span) * (height - 26);
  const step = items.length > 1 ? (width - 8) / (items.length - 1) : width;
  const bar = width / Math.max(items.length, 1);
  const last = items[items.length - 1];
  const first = items[0];
  const change = first && last && first.amount ? ((last.amount! - first.amount) / Math.abs(first.amount)) * 100 : null;
  return <figure className="g-chart">
    <div className="g-chart-head"><strong><CountUp value={last?.amount?.toLocaleString()} /></strong>
      {change !== null ? <span className={change >= 0 ? "is-up" : "is-down"}>{change >= 0 ? "▲" : "▼"} {Math.abs(change).toFixed(1)}%</span> : null}</div>
    <span className="g-ghost" aria-hidden="true">{card.title}</span>
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={card.fallbackText}>
      <g className="g-chart-grid">{[0.25, 0.5, 0.75].map(r => <line key={r} x1="0" x2={width} y1={height * r} y2={height * r} />)}</g>
      {card.chartKind === "bar"
        ? items.map((item, index) => <rect key={index} x={index * bar + bar * 0.2} width={bar * 0.6}
            y={y(Math.max(item.amount ?? 0, 0))} height={Math.max(2, Math.abs(y(item.amount ?? 0) - y(0)))} rx={4} />)
        : <>
          <polyline className="g-chart-area" points={`0,${height} ${items.map((item, index) => `${index * step},${y(item.amount ?? 0)}`).join(" ")} ${width},${height}`} />
          <polyline className="g-chart-line" pathLength={1} points={items.map((item, index) => `${index * step},${y(item.amount ?? 0)}`).join(" ")} />
          {last ? <circle className="g-chart-dot" cx={(items.length - 1) * step} cy={y(last.amount ?? 0)} r={4} /> : null}
        </>}
    </svg>
    <figcaption>{first ? <><span>{first.label}</span><span>{last?.label}</span></> : null}</figcaption>
  </figure>;
}

function Summary({ card }: { card: VaultCard }) {
  return <>{card.body ? <p className="g-lead">{card.body}</p> : null}
    <ul className="g-points">{card.items?.map((item, index) => <li key={index}>{item.text}</li>)}</ul></>;
}

/** Only https links reach the DOM; they open in a new tab without referrer or opener. */
function safeUrl(url?: string) {
  if (!url) return undefined;
  try { const parsed = new URL(url); return parsed.protocol === "https:" && !parsed.username ? parsed.href : undefined; }
  catch { return undefined; }
}
function Headlines({ card }: { card: VaultCard }) {
  const [lead, ...rest] = card.items ?? [];
  if (!lead) return null;
  const link = (item: CardItem) => {
    const href = safeUrl(item.url);
    return href ? <a href={href} target="_blank" rel="noopener noreferrer nofollow">{item.title}</a> : item.title;
  };
  const meta = (item: CardItem) => [item.source, item.time].filter(Boolean).join(" · ");
  return <div className="g-news">
    <article className="g-news-lead">
      <div className="g-media is-photo" style={art(lead.title)} aria-hidden="true"><span>{lead.source}</span></div>
      <div className="g-news-body"><span className="g-meta">{meta(lead)}</span><b>{link(lead)}</b>{lead.detail ? <small>{lead.detail}</small> : null}</div>
    </article>
    {rest.length ? <ol className="g-news-list">{rest.map((item, index) =>
      <li key={index}><span className="g-meta">{meta(item)}</span><b>{link(item)}</b>{safeUrl(item.url) ? <Icon name="arrow" /> : null}</li>)}</ol> : null}
  </div>;
}

function Places({ card }: { card: VaultCard }) {
  const { choose, busy } = useContext(CardActionsContext);
  return <ul className="g-rail g-places">{card.items?.map((item, index) =>
    <li key={index} className="g-mini">
      <span className="g-media" style={art(item.title)} aria-hidden="true"><span className="g-badge"><Icon name="pin" /></span></span>
      <span className="g-mini-body"><b>{item.title}</b>
        <small>{[item.rating ? `★ ${item.rating}` : "", item.distance].filter(Boolean).join(" · ")}</small>
        {item.status ? <em className="g-pill">{item.status}</em> : null}
        {item.detail ? <small>{item.detail}</small> : null}
        {choose ? <button type="button" className="g-action" disabled={busy} onClick={() => choose(item.title ?? "")}
          aria-label={`Choose ${item.title}`}>Choose</button> : null}</span>
    </li>)}</ul>;
}

function WeatherGlyph({ condition }: { condition?: CardItem["condition"] }) {
  return <span className={`g-sky is-${condition ?? "cloud"}`} aria-hidden="true"><i /><i /></span>;
}
function Weather({ card }: { card: VaultCard }) {
  const [now, ...rest] = card.items ?? [];
  if (!now) return null;
  return <div className="g-weather">
    <div className="g-weather-now"><WeatherGlyph condition={now.condition} />
      <strong>{now.value}</strong><span>{now.detail ?? now.label}</span>
      {now.condition ? <span className="g-sr">{now.condition}</span> : null}</div>
    {rest.length ? <ol className="g-forecast">{rest.map((item, index) =>
      <li key={index}><small>{item.label}</small><WeatherGlyph condition={item.condition} /><b>{item.value}</b>
        {item.condition ? <span className="g-sr">{item.condition}</span> : null}</li>)}</ol> : null}
  </div>;
}

function Steps({ card }: { card: VaultCard }) {
  return <ol className="g-steps">{card.items?.map((item, index) =>
    <li key={index}><span className="g-step-no" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
      <span><b>{item.title}</b>{item.detail ? <small>{item.detail}</small> : null}</span></li>)}</ol>;
}

function Cards({ card }: { card: VaultCard }) {
  return <div className="g-bento">{card.items?.map((item, index) =>
    <article key={index} className={index === 0 ? "is-feature" : ""} style={art(item.title)}>
      {item.label ? <span className="g-meta">{item.label}</span> : null}
      <b>{item.title}</b>{item.detail ? <small>{item.detail}</small> : null}</article>)}</div>;
}

const REGISTRY: Record<CardLayout, (props: { card: VaultCard }) => ReactNode> = {
  timeline: Timeline, options: Options, checklist: Checklist, comparison: Comparison, table: Table, metrics: Metrics,
  chart: Chart, summary: Summary, headlines: Headlines, places: Places, weather: Weather, steps: Steps, cards: Cards,
};

/** Gentle 3D tilt and a light that follows the pointer (mouse/pen only, never with reduced motion). */
function useTilt() {
  const ref = useRef<HTMLElement>(null);
  const frame = useRef(0);
  const enabled = typeof window !== "undefined" && typeof window.matchMedia === "function"
    && window.matchMedia("(hover: hover)").matches && prefersMotion();
  const move = (event: PointerEvent<HTMLElement>) => {
    if (!enabled || event.pointerType === "touch") return;
    const node = ref.current; if (!node) return;
    const box = node.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width, y = (event.clientY - box.top) / box.height;
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      node.style.setProperty("--g-rx", `${(0.5 - y) * 5}deg`); node.style.setProperty("--g-ry", `${(x - 0.5) * 7}deg`);
      node.style.setProperty("--g-mx", `${x * 100}%`); node.style.setProperty("--g-my", `${y * 100}%`);
      node.classList.add("is-lit");
    });
  };
  const leave = () => {
    const node = ref.current; if (!node) return;
    cancelAnimationFrame(frame.current);
    node.style.setProperty("--g-rx", "0deg"); node.style.setProperty("--g-ry", "0deg"); node.classList.remove("is-lit");
  };
  return { ref, onPointerMove: move, onPointerLeave: leave };
}

export function VaultCardView({ part }: { part: ChatCardPart }) {
  const tilt = useTilt();
  const Body = REGISTRY[part.card.layout];
  if (!Body) return <p className="vault-card-fallback">{part.card.fallbackText}</p>;
  const sources = part.sources.map(sourceLabel).filter((label, index, all) => all.indexOf(label) === index);
  return <section ref={tilt.ref} onPointerMove={tilt.onPointerMove} onPointerLeave={tilt.onPointerLeave}
    className={`vault-card is-${part.card.layout}`} aria-label={part.card.title ?? part.card.fallbackText}>
    {part.card.title || sources.length ? <header className="g-head">
      {part.card.title ? <h3>{part.card.title}</h3> : <span />}
      {sources.length ? <span className="g-source">{sources.join(" · ")}</span> : null}
    </header> : null}
    <Body card={part.card} />
  </section>;
}

const SKELETON_ROWS: Partial<Record<CardLayout, number>> = { options: 1, chart: 1, metrics: 1, places: 1, weather: 1 };
export function VaultCardSkeleton({ layout }: { layout: CardLayout }) {
  const rows = SKELETON_ROWS[layout] ?? 3;
  return <div className={`vault-card is-skeleton is-${layout}`} role="status" aria-label="Preparing a card">
    <i style={{ width: "38%" }} />{Array.from({ length: rows }, (_, index) => <i key={index} className="is-row" />)}
  </div>;
}

/** assistant-ui data-part adapters. */
export function VaultCardPart({ data }: { data: unknown }) {
  return <VaultCardView part={data as ChatCardPart} />;
}
export function VaultCardSkeletonPart({ data }: { data: unknown }) {
  return <VaultCardSkeleton layout={(data as { layout: CardLayout }).layout} />;
}
