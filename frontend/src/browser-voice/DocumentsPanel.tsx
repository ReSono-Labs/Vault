import { Fragment, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { localApi, type HelpMessage } from "@/browser-voice/localApi";

type GuideSection = { id: string; title: string; label: string; summary: string; content: string };
type DocumentDefinition = { id: string; title: string; summary: string; href: string };

const documents: DocumentDefinition[] = [
  { id: "platform", title: "Vault User Guide", summary: "Set up, use, and manage Vault.", href: "/platform-guide.md" },
  { id: "windows", title: "Install Vault on Windows", summary: "Run Vault with Docker Desktop and WSL 2.", href: "/windows-installation.md" },
  { id: "link", title: "ReSono Labs Link", summary: "Add a Custom HTTP/WebSocket Link service for Vault remote access.", href: "/resono-labs-link.md" },
  { id: "bridge", title: "Local Connection Bridge", summary: "Connect trusted local applications that need HTTP or WebSockets.", href: "/local-connection-bridge.md" },
  { id: "agent-memory", title: "Hermes & OpenClaw Memory", summary: "Connect agents to shared Vault memory and session recall.", href: "/hermes-openclaw-memory.md" },
  { id: "plugin-kit", title: "Vault Plugin Kit", summary: "Build Agent Plugins, including package-data migration, Workspace file import, and local folder linking.", href: "/vault-plugin-kit.md" },
  { id: "mcp-kit", title: "Vault MCP Package Kit", summary: "Ship hosted MCP packages with migration ingestion, companion plugins, and supervised sidecars.", href: "/vault-mcp-package-kit.md" },
];

const sectionHelp: Record<string, [string, string]> = {
  "Platform index": ["All help topics", "Choose what you want to set up, change, or learn about."],
  "1. What Vault is": ["About Vault", "Learn what Vault does and which parts are built in."],
  "2. Requirements": ["Before you install", "Check what your computer needs to run Vault."],
  "3. Install Vault": ["Install Vault", "Set up Vault on this computer or your local network."],
  "4. First-time setup": ["Set up Vault", "Create the main account and finish the first setup."],
  "5. Sign in, sign out, and change a password": ["Sign in and passwords", "Sign in, sign out, or change your password."],
  "6. Accounts and workspaces": ["People and accounts", "Add people, use Workspace files, and understand what is private or shared."],
  "7. AI providers": ["Choose an AI provider", "Connect OpenAI, Gemini, or xAI and choose the models Vault uses."],
  "8. Voice": ["Use Voice", "Start a voice conversation and control what Voice can access."],
  "9. Background Agent": ["Use the Background Agent", "Give Vault work that can continue without an open voice session."],
  "10. Mail": ["Connect Mail", "Add or remove an email account and understand available mail actions."],
  "11. Calendar": ["Connect a calendar", "Add or remove a calendar connection."],
  "12. Contacts": ["Use Contacts", "Find and work with contacts from Vault."],
  "13. Memory": ["Manage Memory", "See how Vault remembers information and connects memory to other agents."],
  "14. Agent2Agent": ["Connect another agent", "Connect Hermes, OpenClaw, or another compatible agent."],
  "15. Library: Plugins, Skills, MCP, and Tools": ["Add capabilities", "Install plugins and MCP packages, including package data, Workspace files, and linked folders."],
  "16. Connections safe mode": ["Pause outside connections", "Temporarily stop third-party capabilities without deleting them."],
  "17. Package operation": ["Manage or remove Vault", "Update, back up, restore, uninstall, or reset Vault."],
  "18. Security and privacy boundaries": ["Privacy and security", "Understand where information is stored and what is kept separate."],
  "19. Common issues": ["Fix a common problem", "Find simple steps for Plugin, MCP, sign-in, capability, and update problems."],
  "20. Current supported limitations": ["What Vault cannot do yet", "Review features that are not currently available."],
  "21. Grounding references": ["Technical references", "See the source files used to verify this guide."],
};

export function DocumentsPanel() {
  const [sources, setSources] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState(documents[0].id);
  const selectedDocument = documents.find((document) => document.id === selectedDocumentId) ?? documents[0];
  const source = sources[selectedDocument.id] ?? "";
  const sections = useMemo(() => parseSections(source), [source]);
  const [selectedId, setSelectedId] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const selected = sections.find((section) => section.id === selectedId) ?? sections[0];
  const selectedIndex = selected ? sections.findIndex((section) => section.id === selected.id) : -1;

  function openSection(section: GuideSection | undefined) {
    if (!section) return;
    setSelectedId(section.id);
    requestAnimationFrame(() => {
      document.querySelector(".browser-voice-documents-selector")?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    });
  }

  useEffect(() => {
    Promise.all(documents.map(async (document) => {
      const response = await fetch(document.href, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`${document.title} could not be loaded.`);
      return [document.id, await response.text()] as const;
    }))
      .then((entries) => setSources(Object.fromEntries(entries)))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Vault documents could not be loaded."));
  }, []);

  return <section aria-labelledby="documents-title" className="browser-voice-documents">
    <header className="browser-voice-management-heading">
      <div><span className="browser-voice-eyebrow-label">Help</span><h2 id="documents-title">Documents</h2><p>Choose a guide for clear, user-friendly instructions.</p></div>
      <div className="browser-voice-inline-actions"><button className="browser-voice-submit" onClick={() => setHelpOpen(true)} type="button">Ask Vault Help</button><a className="browser-voice-pill" download href={selectedDocument.href}>Download document</a></div>
    </header>
    {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
    {!error && !source ? <p className="browser-voice-management-empty">Loading documents…</p> : null}
    {selected ? <div className="browser-voice-documents-layout">
      <div className="browser-voice-document-catalog" aria-label="Available documents">
        {documents.map((document) => <button className={document.id === selectedDocument.id ? "is-active" : ""} key={document.id} onClick={() => { setSelectedDocumentId(document.id); setSelectedId(""); }} type="button"><strong>{document.title}</strong><span>{document.summary}</span></button>)}
      </div>
      <label className="browser-voice-documents-selector">
        <span className="browser-voice-eyebrow-label">Document section</span>
        <select aria-label="Document section" onChange={(event) => setSelectedId(event.target.value)} value={selected.id}>
          {sections.map((section) => <option key={section.id} value={section.id}>{section.label}</option>)}
        </select>
      </label>
      {selected.id === "guide-0" && selectedDocument.id === "platform" ? <div className="browser-voice-document-topics">
        <h2>What do you want to do?</h2>
        <p>Choose a topic for clear instructions.</p>
        <div>{sections.slice(1).map((section) => <button key={section.id} onClick={() => openSection(section)} type="button"><strong>{section.label}</strong><span>{section.summary}</span></button>)}</div>
        <DocumentNavigation currentIndex={selectedIndex} onOpen={openSection} sections={sections} />
      </div> : <article className="browser-voice-document-body" key={selected.id}>
        <h2>{selectedDocument.id === "platform" ? selected.label : selected.title}</h2>
        {renderMarkdown(selected.content)}
        <DocumentNavigation currentIndex={selectedIndex} onOpen={openSection} sections={sections} />
      </article>}
    </div> : null}
    {helpOpen ? <HelpAssistantPanel onClose={() => setHelpOpen(false)} /> : null}
  </section>;
}

function DocumentNavigation({
  currentIndex, onOpen, sections,
}: {
  currentIndex: number;
  onOpen: (section: GuideSection | undefined) => void;
  sections: GuideSection[];
}) {
  const previous = currentIndex > 0 ? sections[currentIndex - 1] : undefined;
  const next = currentIndex >= 0 && currentIndex < sections.length - 1 ? sections[currentIndex + 1] : undefined;
  return <nav aria-label="Document pages" className="browser-voice-document-navigation">
    <button aria-label={`Back: ${previous?.label ?? "First page"}`} disabled={!previous} onClick={() => onOpen(previous)} type="button">
      <span aria-hidden="true">←</span><span><small>Back</small><strong>{previous?.label ?? "First page"}</strong></span>
    </button>
    <button aria-label={`Next: ${next?.label ?? "Last page"}`} disabled={!next} onClick={() => onOpen(next)} type="button">
      <span><small>Next</small><strong>{next?.label ?? "Last page"}</strong></span><span aria-hidden="true">→</span>
    </button>
  </nav>;
}

const helpSuggestions = [
  "How do I connect an AI provider?",
  "Why was my Plugin or MCP blocked?",
  "Help me fix a common problem.",
];

function HelpAssistantPanel({ onClose }: { onClose: () => void }) {
  const [messages, setMessages] = useState<HelpMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [searchWeb, setSearchWeb] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sources, setSources] = useState<Array<{ label: string; kind: string; url?: string }>>([]);
  const showSuggestions = !messages.length && !working && !draft.trim();

  async function submitQuestion(question: string) {
    const trimmed = question.trim();
    if (!trimmed || working) return;
    const history = messages.slice(-8);
    setMessages((current) => [...current, { role: "user", content: trimmed }]);
    setDraft("");
    setError(null);
    setWorking(true);
    setSources([]);
    try {
      const result = await localApi.askHelp(trimmed, history, searchWeb);
      setMessages((current) => [...current, { role: "assistant", content: result.answer }]);
      setSources(result.sources);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Vault Help could not answer right now.");
    } finally { setWorking(false); }
  }

  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitQuestion(draft);
  }

  return createPortal(<div className="browser-voice-help-backdrop" role="presentation">
    <section aria-label="Vault Help" aria-modal="true" className="browser-voice-help-panel" role="dialog">
      <header><h2>Vault Help</h2><button aria-label="Close Vault Help" className="browser-voice-pill" onClick={onClose} type="button">Close</button></header>
      <div aria-live="polite" className="browser-voice-help-messages">
        {!messages.length ? <p className="browser-voice-management-empty">Ask how to use Vault, solve a problem, or create a Plugin or MCP connection. Vault Help checks the complete document index first.</p> : null}
        {showSuggestions ? <div className="browser-voice-help-suggestions">{helpSuggestions.map((question) => <button key={question} onClick={() => void submitQuestion(question)} type="button">{question}</button>)}</div> : null}
        {messages.map((message, index) => <article className={`is-${message.role}`} key={`${message.role}-${index}`}><strong>{message.role === "user" ? "You" : "Vault Help"}</strong><div>{message.role === "assistant" ? renderMarkdown(message.content) : <p>{message.content}</p>}</div></article>)}
        {working ? <p className="browser-voice-management-empty">Checking Vault documents…</p> : null}
        {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
        {sources.length ? <details className="browser-voice-help-sources"><summary>Sources checked</summary><ul>{sources.map((source, index) => <li key={`${source.label}-${index}`}>{source.url ? <a href={source.url} rel="noreferrer" target="_blank">{source.label}</a> : source.label}<small>{source.kind === "guide" ? "Vault document" : source.kind === "web" ? "Web result" : source.kind === "learned" ? "Learned notes" : "Read-only source"}</small></li>)}</ul></details> : null}
      </div>
      <form className="browser-voice-help-form" onSubmit={ask}>
        <textarea aria-label="Ask Vault Help" maxLength={4000} onChange={(event) => setDraft(event.target.value)} placeholder="What do you need help with?" rows={2} value={draft} />
        <div><label><input checked={searchWeb} onChange={(event) => setSearchWeb(event.target.checked)} type="checkbox" /> Search online</label><span><button className="browser-voice-submit" disabled={working || !draft.trim()} type="submit">{working ? "Checking…" : "Ask"}</button></span></div>
      </form>
    </section>
  </div>, document.body);
}

function parseSections(source: string): GuideSection[] {
  const normalized = source.replaceAll("\r\n", "\n");
  const matches = [...normalized.matchAll(/^##\s+(.+)$/gm)];
  return matches.map((match, index) => {
    const title = match[1].trim();
    const start = (match.index ?? 0) + match[0].length;
    const end = matches[index + 1]?.index ?? normalized.length;
    const help = sectionHelp[title] ?? [title.replace(/^\d+\.\s*/, ""), "Open this section."];
    return { id: `guide-${index}`, title, label: help[0], summary: help[1], content: normalized.slice(start, end).trim() };
  });
}

function renderMarkdown(source: string): ReactNode[] {
  const lines = source.split("\n");
  const output: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    if (line.startsWith("```")) {
      const code: string[] = []; index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) code.push(lines[index++]);
      index += 1; output.push(<pre key={`code-${index}`}><code>{code.join("\n")}</code></pre>); continue;
    }
    const heading = /^(#{3,4})\s+(.+)$/.exec(line);
    if (heading) {
      output.push(heading[1].length === 3 ? <h3 key={`h-${index}`}>{heading[2]}</h3> : <h4 key={`h-${index}`}>{heading[2]}</h4>);
      index += 1; continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (index < lines.length && lines[index].startsWith("|")) rows.push(lines[index++].split("|").slice(1, -1).map((cell) => cell.trim()));
      const dataRows = rows.filter((row) => !row.every((cell) => /^:?-{3,}:?$/.test(cell)));
      const [header, ...body] = dataRows;
      output.push(<div className="browser-voice-document-table-wrap" key={`table-${index}`}><table><thead><tr>{header.map((cell, cellIndex) => <th key={cellIndex}>{inline(cell)}</th>)}</tr></thead><tbody>{body.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{inline(cell)}</td>)}</tr>)}</tbody></table></div>); continue;
    }
    if (/^- /.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^- /.test(lines[index])) items.push(lines[index++].slice(2));
      output.push(<ul key={`list-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{inline(item)}</li>)}</ul>); continue;
    }
    if (/^\d+\. /.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\. /.test(lines[index])) items.push(lines[index++].replace(/^\d+\. /, ""));
      output.push(<ol key={`list-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{inline(item)}</li>)}</ol>); continue;
    }
    const paragraph: string[] = [line.trim()]; index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,4})\s|^```|^\||^- |^\d+\. /.test(lines[index])) paragraph.push(lines[index++].trim());
    output.push(<p key={`p-${index}`}>{inline(paragraph.join(" "))}</p>);
  }
  return output;
}

function inline(value: string): ReactNode {
  const parts = value.split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g);
  return parts.map((part, index) => {
    if (part.startsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) return <a href={link[2]} key={index}>{link[1]}</a>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}
