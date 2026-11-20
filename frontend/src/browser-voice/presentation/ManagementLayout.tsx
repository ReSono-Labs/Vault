import { useRef, type KeyboardEvent, type ReactNode } from "react";

/**
 * Shared layout for management pages: one page header, a tab strip that becomes a labeled
 * selector on narrow screens, and sections that keep each heading with the controls it describes.
 * Spacing lives in styles/browser-voice-layout.css; colours come from the existing classes.
 */

export function PageHeader({ eyebrow, title, titleId, description, actions }: {
  eyebrow?: string; title: ReactNode; titleId: string; description?: ReactNode; actions?: ReactNode;
}) {
  return <header className="browser-voice-management-heading vault-page-header">
    <div>
      {eyebrow ? <span className="browser-voice-eyebrow-label">{eyebrow}</span> : null}
      <h2 id={titleId}>{title}</h2>
      {description ? <p>{description}</p> : null}
    </div>
    {actions ? <div className="vault-page-header-actions">{actions}</div> : null}
  </header>;
}

export type TabItem<T extends string> = { id: T; label: string };

const tabId = (prefix: string, id: string) => `${prefix}-${id}-tab`;
const panelId = (prefix: string, id: string) => `${prefix}-${id}-panel`;

/** Tabs with arrow/Home/End keys; below 560px the same choice is a labeled select. */
export function Tabs<T extends string>({ label, idPrefix, tabs, value, onChange }: {
  label: string; idPrefix: string; tabs: TabItem<T>[]; value: T; onChange: (value: T) => void;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = tabs.length - 1;
    const next = event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0 : event.key === "End" ? last : null;
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next].id);
    refs.current[tabs[next].id]?.focus();
  }
  return <div className="vault-tabs">
    <div aria-label={label} className="browser-voice-connection-tabs vault-tabs-strip" role="tablist">
      {tabs.map((tab, index) => {
        const selected = tab.id === value;
        return <button aria-controls={panelId(idPrefix, tab.id)} aria-selected={selected}
          className={selected ? "is-active" : ""} id={tabId(idPrefix, tab.id)} key={tab.id}
          onClick={() => onChange(tab.id)} onKeyDown={event => onKeyDown(event, index)}
          ref={element => { refs.current[tab.id] = element; }} role="tab" tabIndex={selected ? 0 : -1} type="button">
          {tab.label}
        </button>;
      })}
    </div>
    <label className="browser-voice-account-field vault-tabs-select">
      <span>{label}</span>
      <select onChange={event => onChange(event.target.value as T)} value={value}>
        {tabs.map(tab => <option key={tab.id} value={tab.id}>{tab.label}</option>)}
      </select>
    </label>
  </div>;
}

export function TabPanel({ idPrefix, id, className, children }: {
  idPrefix: string; id: string; className?: string; children: ReactNode;
}) {
  return <section aria-labelledby={tabId(idPrefix, id)} className={`vault-tab-panel${className ? ` ${className}` : ""}`}
    id={panelId(idPrefix, id)} role="tabpanel">
    {children}
  </section>;
}

/** One heading, its description and its controls, grouped so spacing is set between sections. */
export function PageSection({ title, titleId, description, actions, children, className }: {
  title: ReactNode; titleId?: string; description?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string;
}) {
  return <section aria-labelledby={titleId} className={`vault-section${className ? ` ${className}` : ""}`}>
    <div className="browser-voice-section-head vault-section-head">
      <div>
        <h3 id={titleId}>{title}</h3>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="vault-section-actions">{actions}</div> : null}
    </div>
    {children}
  </section>;
}
