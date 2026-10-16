import { createContext, useContext, type ReactNode } from "react";
import type { CardItem, CardLayout, ChatCardPart, VaultCard } from "@/browser-voice/conversation/api";
import "./genui.css";

/**
 * Vault's registered card components. Cards are server-validated data; everything is rendered
 * as React text (never HTML), and the only interaction is sending a new user message.
 */
export type CardActions = { choose?: (text: string) => void; busy?: boolean };
export const CardActionsContext = createContext<CardActions>({});

const SOURCE_LABELS: Record<string, string> = {
  web_search: "Web", memory_lookup: "Memory", contacts_search: "Contacts",
};
function sourceLabel(name: string) {
  if (SOURCE_LABELS[name]) return SOURCE_LABELS[name];
  const head = name.split(/[_.]/)[0];
  return head ? head.charAt(0).toUpperCase() + head.slice(1) : name;
}

const STATE_LABEL: Record<NonNullable<CardItem["state"]>, string> = {
  done: "Done", needs_you: "Needs you", optional: "Optional", pending: "Pending",
};
const TREND: Record<NonNullable<CardItem["trend"]>, string> = { up: "▲", down: "▼", flat: "■" };

function Timeline({ card }: { card: VaultCard }) {
  return <ol className="vault-card-timeline">{card.items?.map((item, index) =>
    <li key={index}>
      <time>{item.time}</time>
      <span><b>{item.title}</b>{item.detail ? <small>{item.detail}</small> : null}</span>
      {item.state ? <em className={`is-${item.state}`}>{STATE_LABEL[item.state]}</em> : null}
    </li>)}</ol>;
}

function Options({ card }: { card: VaultCard }) {
  const { choose, busy } = useContext(CardActionsContext);
  return <div className="vault-card-options" role="group" aria-label={card.title ?? "Options"}>
    {card.items?.map((item, index) =>
      <button key={index} type="button" disabled={!choose || busy} onClick={() => choose?.(item.title ?? "")}>
        <span className="vault-card-option-mark" aria-hidden="true">{index + 1}</span>
        <b>{item.title}</b>{item.detail ? <small>{item.detail}</small> : null}
      </button>)}
  </div>;
}

function Checklist({ card }: { card: VaultCard }) {
  return <ul className="vault-card-checklist">{card.items?.map((item, index) =>
    <li key={index} className={item.done ? "is-done" : ""}>
      <span aria-hidden="true" /><span>{item.text}</span>
      <span className="vault-visually-hidden">{item.done ? " (done)" : " (open)"}</span>
    </li>)}</ul>;
}

function Grid({ card, comparison }: { card: VaultCard; comparison: boolean }) {
  return <div className="vault-card-table-wrap"><table className={`vault-card-table${comparison ? " is-comparison" : ""}`}>
    <thead><tr>{comparison ? <td /> : null}{card.columns?.map((column, index) => <th key={index} scope="col">{column}</th>)}</tr></thead>
    <tbody>{card.rows?.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) =>
      comparison && cellIndex === 0 ? <th key={cellIndex} scope="row">{cell}</th> : <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody>
  </table></div>;
}

function Metrics({ card }: { card: VaultCard }) {
  return <dl className="vault-card-metrics">{card.items?.map((item, index) =>
    <div key={index}><dt>{item.label}</dt>
      <dd><strong>{item.value}</strong>{item.trend ? <span className={`is-${item.trend}`} aria-label={item.trend}>{TREND[item.trend]}</span> : null}
        {item.detail ? <small>{item.detail}</small> : null}</dd></div>)}</dl>;
}

function Chart({ card }: { card: VaultCard }) {
  const items = card.items ?? [];
  const amounts = items.map(item => item.amount ?? 0);
  const max = Math.max(...amounts), min = Math.min(0, ...amounts);
  const span = max - min || 1;
  const width = 300, height = 110;
  const y = (amount: number) => height - 8 - ((amount - min) / span) * (height - 20);
  const step = items.length > 1 ? width / (items.length - 1) : width;
  const bar = width / Math.max(items.length, 1);
  return <figure className="vault-card-chart">
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={card.fallbackText}>
      {card.chartKind === "bar"
        ? items.map((item, index) => <rect key={index} x={index * bar + bar * 0.18} width={bar * 0.64}
            y={y(Math.max(item.amount ?? 0, 0))} height={Math.abs(y(item.amount ?? 0) - y(0))} rx={4} />)
        : <polyline fill="none" strokeWidth={2.4} strokeLinejoin="round" strokeLinecap="round"
            points={items.map((item, index) => `${index * step},${y(item.amount ?? 0)}`).join(" ")} />}
    </svg>
    <figcaption>{items.length ? <><span>{items[0].label}</span><span>{items[items.length - 1].label}</span></> : null}</figcaption>
  </figure>;
}

function Summary({ card }: { card: VaultCard }) {
  return <>{card.body ? <p className="vault-card-body">{card.body}</p> : null}
    <ul className="vault-card-points">{card.items?.map((item, index) => <li key={index}>{item.text}</li>)}</ul></>;
}

/** Only https links reach the DOM; they open in a new tab without referrer or opener. */
function safeUrl(url?: string) {
  if (!url) return undefined;
  try { const parsed = new URL(url); return parsed.protocol === "https:" && !parsed.username ? parsed.href : undefined; }
  catch { return undefined; }
}

function Headlines({ card }: { card: VaultCard }) {
  return <ol className="vault-card-headlines">{card.items?.map((item, index) => {
    const href = safeUrl(item.url);
    const title = href ? <a href={href} target="_blank" rel="noopener noreferrer nofollow">{item.title}</a> : item.title;
    return <li key={index}>
      <span className="vault-card-headline-meta">{[item.source, item.time].filter(Boolean).join(" · ")}</span>
      <b>{title}</b>{item.detail ? <small>{item.detail}</small> : null}
    </li>;
  })}</ol>;
}

function Places({ card }: { card: VaultCard }) {
  const { choose, busy } = useContext(CardActionsContext);
  return <ul className="vault-card-places">{card.items?.map((item, index) =>
    <li key={index}>
      <span className="vault-card-place-pin" aria-hidden="true">{index + 1}</span>
      <span className="vault-card-place-body"><b>{item.title}</b>
        <small>{[item.rating ? `★ ${item.rating}` : "", item.distance, item.status].filter(Boolean).join(" · ")}</small>
        {item.detail ? <small>{item.detail}</small> : null}</span>
      {choose ? <button type="button" disabled={busy} onClick={() => choose(item.title ?? "")}
        aria-label={`Choose ${item.title}`}>Choose</button> : null}
    </li>)}</ul>;
}

const WEATHER_ICON: Record<NonNullable<CardItem["condition"]>, string> = {
  sun: "☀️", partly: "⛅", cloud: "☁️", rain: "🌧️", snow: "🌨️", storm: "⛈️", fog: "🌫️", wind: "💨", night: "🌙",
};
function Weather({ card }: { card: VaultCard }) {
  const [now, ...rest] = card.items ?? [];
  if (!now) return null;
  return <div className="vault-card-weather">
    <div className="vault-card-weather-now">
      <span className="vault-card-weather-icon" aria-hidden="true">{now.condition ? WEATHER_ICON[now.condition] : ""}</span>
      <strong>{now.value}</strong>
      <span>{now.detail ?? now.label}</span>
    </div>
    {rest.length ? <ol className="vault-card-weather-forecast">{rest.map((item, index) =>
      <li key={index}><small>{item.label}</small>
        <span aria-hidden="true">{item.condition ? WEATHER_ICON[item.condition] : ""}</span>
        <b>{item.value}</b>{item.condition ? <span className="vault-visually-hidden">{item.condition}</span> : null}</li>)}</ol> : null}
  </div>;
}

function Steps({ card }: { card: VaultCard }) {
  return <ol className="vault-card-steps">{card.items?.map((item, index) =>
    <li key={index}><span aria-hidden="true">{index + 1}</span><span><b>{item.title}</b>{item.detail ? <small>{item.detail}</small> : null}</span></li>)}</ol>;
}

function Cards({ card }: { card: VaultCard }) {
  return <div className="vault-card-grid">{card.items?.map((item, index) =>
    <article key={index}>{item.label ? <span className="vault-card-grid-label">{item.label}</span> : null}
      <b>{item.title}</b>{item.detail ? <small>{item.detail}</small> : null}</article>)}</div>;
}

const REGISTRY: Record<CardLayout, (props: { card: VaultCard }) => ReactNode> = {
  headlines: Headlines, places: Places, weather: Weather, steps: Steps, cards: Cards,
  timeline: Timeline, options: Options, checklist: Checklist, metrics: Metrics, chart: Chart, summary: Summary,
  table: ({ card }) => <Grid card={card} comparison={false} />,
  comparison: ({ card }) => <Grid card={card} comparison />,
};

export function VaultCardView({ part }: { part: ChatCardPart }) {
  const Body = REGISTRY[part.card.layout];
  if (!Body) return <p className="vault-card-fallback">{part.card.fallbackText}</p>;
  return <section className={`vault-card is-${part.card.layout}`} aria-label={part.card.title ?? part.card.fallbackText}>
    {part.card.title || part.sources.length ? <header>
      {part.card.title ? <h3>{part.card.title}</h3> : <span />}
      {part.sources.length ? <span className="vault-card-sources">{part.sources.map(sourceLabel)
        .filter((label, index, all) => all.indexOf(label) === index).join(" · ")}</span> : null}
    </header> : null}
    <Body card={part.card} />
  </section>;
}

const SKELETON_ROWS: Partial<Record<CardLayout, number>> = { options: 1, chart: 1, metrics: 1 };
export function VaultCardSkeleton({ layout }: { layout: CardLayout }) {
  const rows = SKELETON_ROWS[layout] ?? 3;
  return <div className={`vault-card is-skeleton is-${layout}`} role="status" aria-label="Preparing a card">
    <i style={{ width: "38%" }} />{Array.from({ length: rows }, (_, index) => <i key={index} className="is-row" />)}
  </div>;
}

/** assistant-ui data-part adapter: ``data-vault-card`` parts render through the registry. */
export function VaultCardPart({ data }: { data: unknown }) {
  const part = data as ChatCardPart;
  return <VaultCardView part={part} />;
}
export function VaultCardSkeletonPart({ data }: { data: unknown }) {
  return <VaultCardSkeleton layout={(data as { layout: CardLayout }).layout} />;
}
