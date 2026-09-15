import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { localApi, type CalendarAccount, type LocalExtension, type MailAccount, type VoiceProviderStatus } from "@/browser-voice/localApi";
import { McpPackageSetup } from "@/browser-voice/McpPackageSetup";
import { importMcpPackageFile, mcpPackageRemoveMessage } from "@/browser-voice/mcpPackageFlow";
import { BrowserVoiceConnectionCategoryIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";

type ConnectionTab = "provider" | "calendar" | "mail" | "extensions";

const CONNECTION_TABS: Array<{ id: ConnectionTab; label: string }> = [
  { id: "provider", label: "AI & Voice" },
  { id: "calendar", label: "Calendar" },
  { id: "mail", label: "Mail" },
  { id: "extensions", label: "Extensions" },
];

function setDialogOpen(dialog: HTMLDialogElement, open: boolean) {
  if (open && !dialog.open) {
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }
  if (!open && dialog.open) {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }
}

export function ConnectionsPanel() {
  const [activeTab, setActiveTab] = useState<ConnectionTab>("provider");
  const [items, setItems] = useState<LocalExtension[]>([]);
  const [safeMode, setSafeMode] = useState(true);
  const [provider, setProvider] = useState<VoiceProviderStatus | null>(null);
  const [providers, setProviders] = useState<VoiceProviderStatus[]>([]);
  const [providerKey, setProviderKey] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [modelKey, setModelKey] = useState("gpt-realtime");
  const [voice, setVoice] = useState("alloy");
  const [backgroundModelKey, setBackgroundModelKey] = useState("gpt-5.6-sol");
  const [mailAccounts, setMailAccounts] = useState<MailAccount[]>([]);
  const [calendarAccounts, setCalendarAccounts] = useState<CalendarAccount[]>([]);
  const [showMailForm, setShowMailForm] = useState(false);
  const [showCalendarForm, setShowCalendarForm] = useState(false);
  const [calendarProviderType, setCalendarProviderType] = useState<"ics" | "caldav">("ics");
  const [mailError, setMailError] = useState<string | null>(null);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [oauthMessage, setOauthMessage] = useState<string | null>(null);
  const [openMcp, setOpenMcp] = useState<LocalExtension | null>(null);
  const [mcpMessage, setMcpMessage] = useState<string | null>(null);
  const [mcpWorking, setMcpWorking] = useState(false);
  const mailDialogRef = useRef<HTMLDialogElement | null>(null);
  const calendarDialogRef = useRef<HTMLDialogElement | null>(null);
  const mcpImportInputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const dialog = mailDialogRef.current;
    if (!dialog) return;
    setDialogOpen(dialog, showMailForm);
  }, [showMailForm]);
  useEffect(() => {
    const dialog = calendarDialogRef.current;
    if (!dialog) return;
    setDialogOpen(dialog, showCalendarForm);
  }, [showCalendarForm]);
  useEffect(() => {
    const providerCatalog = localApi.providers().catch(async () => {
      const fallback = await localApi.voiceProvider("openai");
      return { selectedProviderKey: "openai", items: [{ ...fallback, displayName: "OpenAI", connectionMode: "webrtc" as const, protocol: "openai-realtime", selected: true }] };
    });
    providerCatalog
      .then((catalog) => {
        const currentProvider = catalog.items.find((item) => item.providerKey === catalog.selectedProviderKey) ?? catalog.items[0];
        setProviders(catalog.items);
        setProviderKey(currentProvider.providerKey);
        setProvider(currentProvider);
        setModelKey(currentProvider.modelKey);
        setVoice(currentProvider.voice);
        setBackgroundModelKey(currentProvider.backgroundModelKey);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "AI provider settings could not be loaded."));
    localApi.extensions().then((result) => setItems(result.items.filter((item) => item.kind === "mcp"))).catch(() => undefined);
    localApi.extensionRuntime().then((runtime) => setSafeMode(runtime.safeMode)).catch(() => undefined);
    localApi.mailAccounts().then((mail) => setMailAccounts(mail.items)).catch(() => undefined);
    localApi.calendarAccounts().then((calendars) => setCalendarAccounts(calendars.items)).catch(() => undefined);
  }, []);
  async function toggleSafeMode() {
    try { const next = !safeMode; await localApi.safeMode(next); setSafeMode(next); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Safe mode could not be changed."); }
  }
  async function saveProvider(event: FormEvent) {
    event.preventDefault();
    try {
      const payload: {
        modelKey: string;
        backgroundModelKey: string;
        voice: string;
        apiKey?: string;
      } = {
        modelKey,
        backgroundModelKey,
        voice: providerKey === "gemini" ? "Kore" : providerKey === "xai" ? "eve" : "marin",
      };
      if (apiKey.trim()) payload.apiKey = apiKey.trim();
      const current = await localApi.setVoiceProvider(providerKey, payload);
      setProvider({ ...current, displayName: provider?.displayName, configured: true, selected: true });
      setProviders((items) => items.map((item) => item.providerKey === providerKey ? { ...item, ...current, configured: true, selected: true } : { ...item, selected: false }));
      setApiKey("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Voice provider could not be saved."); }
  }
  function chooseProvider(nextKey: string) {
    const next = providers.find((item) => item.providerKey === nextKey);
    if (!next) return;
    setProviderKey(nextKey); setProvider(next);
    setModelKey(next.modelKey); setBackgroundModelKey(next.backgroundModelKey); setVoice(next.voice);
  }
  async function useProvider() {
    try {
      await localApi.selectProvider(providerKey);
      setProviders((items) => items.map((item) => ({ ...item, selected: item.providerKey === providerKey })));
      setProvider((current) => current ? { ...current, selected: true } : current);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "AI provider could not be selected."); }
  }
  async function connectOAuth() {
    setError(null); setOauthMessage(null);
    try {
      if (provider?.oauthConnected && provider.authMethod === "api_key") {
        const method = providerKey === "openai" ? "chatgpt_oauth" : "gemini_oauth";
        const current = await localApi.selectProviderAuth(providerKey, method);
        setProvider({ ...provider, ...current });
        setProviders((items) => items.map((item) => item.providerKey === providerKey ? { ...item, ...current } : item));
        setOauthMessage(`${providerKey === "openai" ? "ChatGPT" : "Gemini"} OAuth selected.`);
        return;
      }
      if (providerKey === "openai") {
        const started = await localApi.startChatGptOAuth();
        window.open(started.verificationUrl, "_blank", "noopener,noreferrer");
        setOauthMessage(`Enter code ${started.userCode} in the ChatGPT window.`);
        const deadline = started.expiresAt * 1000;
        while (Date.now() < deadline) {
          await new Promise((resolve) => window.setTimeout(resolve, started.pollIntervalSeconds * 1000));
          const result = await localApi.pollChatGptOAuth(started.authSessionId);
          if (result.status === "completed") {
            const current = await localApi.voiceProvider("openai");
            setProvider({ ...provider, ...current, configured: true, selected: true });
            setProviders((items) => items.map((item) => item.providerKey === "openai" ? { ...item, ...current, configured: true, selected: true } : { ...item, selected: false }));
            setOauthMessage("ChatGPT OAuth connected."); return;
          }
        }
        throw new Error("ChatGPT OAuth expired. Try again.");
      }
      if (providerKey === "gemini") {
        const redirectUri = `${window.location.origin}/providers/gemini/oauth/callback`;
        const started = await localApi.startGeminiOAuth(redirectUri);
        window.location.assign(started.authorizationUrl);
      }
    } catch (caught) { setError(caught instanceof Error ? caught.message : "OAuth could not be connected."); }
  }
  async function disconnectOAuth() {
    setError(null); setOauthMessage(null);
    try {
      const current = await localApi.disconnectProviderOAuth(providerKey);
      setProvider({ ...provider, ...current });
      setProviders((items) => items.map((item) => item.providerKey === providerKey ? { ...item, ...current } : item));
      setOauthMessage("OAuth disconnected.");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "OAuth could not be disconnected."); }
  }
  async function connectMail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setMailError(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const value = (name: string) => String(data.get(name) || "").trim();
    try {
      const account = await localApi.connectMail({
        displayName: value("displayName") || undefined,
        credentials: {
          emailAddress: value("emailAddress"),
          imap: { host: value("imapHost"), port: Number(value("imapPort")), username: value("imapUsername"), password: value("imapPassword"), useTls: true },
          smtp: { host: value("smtpHost"), port: Number(value("smtpPort")), username: value("smtpUsername"), password: value("smtpPassword"), useTls: true },
        },
        validateConnection: true,
      });
      setMailAccounts((current) => [...current.filter((item) => item.mailboxAccountId !== account.mailboxAccountId), account].sort((a, b) => a.emailAddress.localeCompare(b.emailAddress)));
      form.reset();
      setShowMailForm(false);
    } catch (caught) { setMailError(caught instanceof Error ? caught.message : "Mail account could not be connected."); }
  }
  async function connectCalendar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setCalendarError(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const value = (name: string) => String(data.get(name) || "").trim();
    const providerType = value("providerType") as "ics" | "caldav";
    try {
      const account = await localApi.connectCalendar({
        providerType, displayName: value("displayName") || undefined,
        credentials: providerType === "ics"
          ? { feedUrl: value("feedUrl") }
          : { calendarUrl: value("calendarUrl") || undefined, username: value("username"), password: value("password") },
        validateConnection: true,
      });
      setCalendarAccounts((current) => [...current, account]); form.reset();
      setCalendarProviderType("ics");
      setShowCalendarForm(false);
    } catch (caught) { setCalendarError(caught instanceof Error ? caught.message : "Calendar could not be connected."); }
  }
  async function removeCalendar(calendarAccountId: string) {
    try { await localApi.removeCalendar(calendarAccountId); setCalendarAccounts((current) => current.filter((item) => item.calendarAccountId !== calendarAccountId)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Calendar could not be removed."); }
  }
  async function refreshExtensions() {
    const extensions = await localApi.extensions();
    setItems(extensions.items.filter((item) => item.kind === "mcp"));
    if (openMcp) {
      const updated = extensions.items.find((item) => item.extensionId === openMcp.extensionId);
      if (updated) setOpenMcp(updated);
    }
  }
  async function importMcpPackage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setMcpWorking(true);
    setMcpMessage(null);
    setError(null);
    try {
      const result = await importMcpPackageFile(file);
      if (result.identity) {
        setMcpMessage(result.message);
        await refreshExtensions();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "MCP package import failed.");
    } finally {
      event.target.value = "";
      setMcpWorking(false);
    }
  }
  async function removeMcp(item: LocalExtension) {
    if (!window.confirm(mcpPackageRemoveMessage(item))) return;
    setMcpWorking(true);
    setError(null);
    try {
      await localApi.extensionState(item.extensionId, "removed");
      if (openMcp?.extensionId === item.extensionId) setOpenMcp(null);
      await refreshExtensions();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "MCP could not be removed.");
    } finally {
      setMcpWorking(false);
    }
  }
  const voiceModelOptions = provider?.voiceModels ?? [];
  const backgroundModelOptions = Array.from(new Set([
    backgroundModelKey,
    ...(providerKey === "openai" ? ["gpt-5.6-sol"]
      : providerKey === "gemini" ? ["gemini-2.5-pro"]
      : providerKey === "xai" ? ["grok-4-0709"] : []),
  ].filter(Boolean)));
  return (
    <section className="browser-voice-connections" aria-labelledby="connections-title">
      <header className="browser-voice-management-heading"><div><span className="browser-voice-eyebrow-label">Connections</span><h2 id="connections-title">Connected services</h2><p>Accounts and providers available to this local Vault.</p></div></header>
      <div aria-label="Connection types" className="browser-voice-connection-tabs" role="tablist">
        {CONNECTION_TABS.map((tab) => <button aria-controls={`connections-${tab.id}-panel`} aria-selected={activeTab === tab.id} className={activeTab === tab.id ? "is-active" : ""} id={`connections-${tab.id}-tab`} key={tab.id} onClick={() => setActiveTab(tab.id)} role="tab" type="button">{tab.label}</button>)}
      </div>
      {activeTab === "provider" ? <section aria-labelledby="connections-provider-tab" className="browser-voice-management-section browser-voice-connection-tab-panel" id="connections-provider-panel" role="tabpanel">
      <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">AI &amp; Voice</span><h3>Provider settings</h3><p>The selected provider runs Voice and all background AI work. Embeddings remain separate.</p></div><span className={`browser-voice-state ${provider?.configured ? "is-ready" : ""}`}>{provider?.selected ? "Selected" : provider?.configured ? "Configured" : "Needs setup"}</span></div>
      <form className="browser-voice-form is-two-column" onSubmit={(event) => void saveProvider(event)}>
        <p className="browser-voice-form-note">{provider?.oauthConnected && provider.authMethod !== "api_key" ? "OAuth is active. Leave the API key blank to save model and voice settings only." : "The API key is encrypted locally and is never returned to the browser."}</p>
        <label><span>AI provider</span><select aria-label="AI provider" onChange={(event) => chooseProvider(event.target.value)} value={providerKey}>{providers.map((item) => <option key={item.providerKey} value={item.providerKey}>{item.displayName ?? item.providerKey}</option>)}</select></label>
        <label><span>{provider?.displayName ?? "Provider"} API key</span><input autoComplete="off" onChange={(event) => setApiKey(event.target.value)} placeholder={provider?.oauthConnected && provider.authMethod !== "api_key" ? "Optional — leave blank to keep OAuth" : undefined} required={!(provider?.oauthConnected && provider.authMethod !== "api_key")} type="password" value={apiKey} /></label>
        <label><span>Voice model</span>{voiceModelOptions.length ? <select onChange={(event) => setModelKey(event.target.value)} value={modelKey}>{voiceModelOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select> : <input onChange={(event) => setModelKey(event.target.value)} required value={modelKey} />}</label>
        <label><span>Background text model</span><select onChange={(event) => setBackgroundModelKey(event.target.value)} value={backgroundModelKey}>{backgroundModelOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        {providerKey === "openai" || providerKey === "gemini" ? <div className="browser-voice-inline-actions">{provider?.oauthConnected ? <button className="browser-voice-pill" onClick={() => void disconnectOAuth()} type="button">Disconnect OAuth</button> : <button className="browser-voice-pill" onClick={() => void connectOAuth()} type="button">{providerKey === "openai" ? "ChatGPT OAuth" : "Gemini OAuth"}</button>}{oauthMessage ? <span className="browser-voice-form-note" role="status">{oauthMessage}</span> : null}</div> : null}
        <div className="browser-voice-inline-actions"><button className="browser-voice-submit" type="submit">Save settings</button>{provider?.configured && !provider.selected ? <button className="browser-voice-pill" onClick={() => void useProvider()} type="button">Use provider</button> : null}</div>
      </form>
      </section> : null}
      {activeTab === "calendar" ? <section aria-labelledby="connections-calendar-tab" className="browser-voice-management-section browser-voice-connection-tab-panel" id="connections-calendar-panel" role="tabpanel">
      <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">Calendar</span><h3>Calendar accounts</h3><p>Connect read-only ICS feeds or CalDAV calendars to this workspace.</p></div><button className="browser-voice-submit" onClick={() => { setCalendarError(null); setShowCalendarForm(true); }} type="button">Add calendar</button></div>
      {calendarAccounts.map((account) => <article className="browser-voice-connection-row" key={account.calendarAccountId}>
        <span className="browser-voice-connection-mark is-calendar"><BrowserVoiceConnectionCategoryIcon category="calendar" /></span>
        <span><strong>{account.displayName}</strong><small>{account.providerType.toUpperCase()} · {account.status}</small></span>
        <button className="browser-voice-pill browser-voice-pill-muted" onClick={() => void removeCalendar(account.calendarAccountId)} type="button">Remove</button>
      </article>)}
      </section> : null}
      {activeTab === "mail" ? <section aria-labelledby="connections-mail-tab" className="browser-voice-management-section browser-voice-connection-tab-panel" id="connections-mail-panel" role="tabpanel">
      <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">Mail</span><h3>Mail accounts</h3><p>Connect multiple IMAP and SMTP accounts to the local Mail client.</p></div><button className="browser-voice-submit" onClick={() => { setMailError(null); setShowMailForm(true); }} type="button">Add mail account</button></div>
      {mailAccounts.map((account) => <article className="browser-voice-connection-row" key={account.mailboxAccountId}>
        <span className="browser-voice-connection-mark"><BrowserVoiceConnectionCategoryIcon category="email" /></span>
        <span><strong>{account.displayName || account.emailAddress}</strong><small>{account.emailAddress} · {account.lifecycleStatus} · {account.syncStatus}</small></span>
      </article>)}
      </section> : null}
      {activeTab === "extensions" ? <section aria-labelledby="connections-extensions-tab" className="browser-voice-management-section browser-voice-connection-tab-panel" id="connections-extensions-panel" role="tabpanel">
      {openMcp ? (
        <McpPackageSetup
          item={openMcp}
          onBack={() => setOpenMcp(null)}
          onChanged={refreshExtensions}
          onRemove={async () => {
            await removeMcp(openMcp);
          }}
        />
      ) : <>
      <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">MCP servers</span><h3>Hosted tool servers</h3><p>{items.length} configured</p></div>
        <input
          accept=".zip,.tar,.tgz,.gz"
          disabled={mcpWorking}
          hidden
          onChange={(event) => void importMcpPackage(event)}
          ref={mcpImportInputRef}
          type="file"
        />
        <button
          className="browser-voice-submit browser-voice-section-action"
          disabled={mcpWorking}
          onClick={() => mcpImportInputRef.current?.click()}
          type="button"
        >
          {mcpWorking ? "Checking…" : "Import package"}
        </button>
      </div>
      {mcpMessage ? <p className="browser-voice-management-message" role="status">{mcpMessage}</p> : null}
      <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">Extensions</span><h3>External connections</h3><p>MCP connections remain blocked until explicitly enabled and granted.</p></div></div>
      <article className="browser-voice-connection-row">
        <span className="browser-voice-connection-mark"><BrowserVoiceConnectionCategoryIcon category="provider" /></span>
        <span><strong>Third-party safe mode</strong><small>{safeMode ? "External capabilities are blocked" : "Explicit grants may run"}</small></span>
        <button aria-pressed={!safeMode} className="browser-voice-agent-switch" onClick={() => void toggleSafeMode()} role="switch" type="button"><span /></button>
      </article>
      {items.map((item) => <article className="browser-voice-connection-row" key={item.extensionId}>
        <span className="browser-voice-connection-mark"><BrowserVoiceConnectionCategoryIcon category="provider" /></span>
        <button className="browser-voice-connection-open" onClick={() => setOpenMcp(item)} type="button">
          <strong>{item.displayName}</strong>
          <small>{item.state === "enabled" ? "On" : "Off"} · Open to configure</small>
        </button>
        <span className="browser-voice-connection-actions">
          <button className="browser-voice-pill browser-voice-pill-muted" disabled={mcpWorking} onClick={() => void removeMcp(item)} type="button">Remove</button>
        </span>
      </article>)}
      {!items.length ? <p className="browser-voice-management-empty">No MCP packages imported.</p> : null}
      </>}
      </section> : null}
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
      <dialog aria-labelledby="calendar-dialog-title" className="browser-voice-modal" onCancel={() => setShowCalendarForm(false)} onClose={() => setShowCalendarForm(false)} ref={calendarDialogRef}>
        <form onSubmit={(event) => void connectCalendar(event)}>
          <div className="browser-voice-modal-head"><div><span className="browser-voice-eyebrow-label">Calendar connection</span><h2 id="calendar-dialog-title">Add calendar</h2></div><button aria-label="Close calendar dialog" className="browser-voice-modal-close" onClick={() => setShowCalendarForm(false)} type="button">×</button></div>
          <div className="browser-voice-modal-fields">
            <label><span>Connection type</span><select name="providerType" onChange={(event) => setCalendarProviderType(event.target.value as "ics" | "caldav")} value={calendarProviderType}><option value="ics">ICS calendar feed</option><option value="caldav">CalDAV account</option></select></label>
            <label><span>Calendar name</span><input maxLength={80} name="displayName" placeholder="Personal calendar" required /></label>
            {calendarProviderType === "ics" ? <label className="browser-voice-modal-wide"><span>ICS feed address</span><input name="feedUrl" placeholder="https://example.com/calendar.ics" required type="url" /></label> : <>
              <label className="browser-voice-modal-wide"><span>CalDAV calendar address</span><input name="calendarUrl" placeholder="https://example.com/caldav/calendars/personal/" type="url" /></label>
              <label><span>Username</span><input autoComplete="username" name="username" required /></label>
              <label><span>Password or app password</span><input autoComplete="current-password" name="password" required type="password" /></label>
            </>}
          </div>
          <p className="browser-voice-form-note">Credentials are encrypted in this Vault and never returned. Read-only calendars cannot be changed.</p>
          {calendarError ? <p className="browser-voice-modal-error" role="alert">{calendarError}</p> : null}
          <div className="browser-voice-modal-actions"><button className="browser-voice-pill" onClick={() => setShowCalendarForm(false)} type="button">Cancel</button><button className="browser-voice-submit" type="submit">Connect calendar</button></div>
        </form>
      </dialog>
      <dialog aria-labelledby="mail-dialog-title" className="browser-voice-modal" onCancel={() => setShowMailForm(false)} onClose={() => setShowMailForm(false)} ref={mailDialogRef}>
        <form onSubmit={(event) => void connectMail(event)}>
          <div className="browser-voice-modal-head"><div><span className="browser-voice-eyebrow-label">Mail account</span><h2 id="mail-dialog-title">Add mail account</h2></div><button aria-label="Close mail dialog" className="browser-voice-modal-close" onClick={() => setShowMailForm(false)} type="button">×</button></div>
          <div className="browser-voice-modal-fields">
            <label><span>Account name</span><input maxLength={80} name="displayName" placeholder="Personal mail" required /></label>
            <label><span>Email address</span><input autoComplete="email" name="emailAddress" required type="email" /></label>
            <label><span>Incoming mail server</span><input name="imapHost" placeholder="imap.example.com" required /></label>
            <label><span>Incoming port</span><input defaultValue="993" max="65535" min="1" name="imapPort" required type="number" /></label>
            <label><span>Incoming username</span><input autoComplete="username" name="imapUsername" required /></label>
            <label><span>Incoming password</span><input autoComplete="current-password" name="imapPassword" required type="password" /></label>
            <label><span>Outgoing mail server</span><input name="smtpHost" placeholder="smtp.example.com" required /></label>
            <label><span>Outgoing port</span><input defaultValue="465" max="65535" min="1" name="smtpPort" required type="number" /></label>
            <label><span>Outgoing username</span><input autoComplete="username" name="smtpUsername" required /></label>
            <label><span>Outgoing password</span><input autoComplete="current-password" name="smtpPassword" required type="password" /></label>
          </div>
          <p className="browser-voice-form-note">Credentials are encrypted in this Vault and never returned.</p>
          {mailError ? <p className="browser-voice-modal-error" role="alert">{mailError}</p> : null}
          <div className="browser-voice-modal-actions"><button className="browser-voice-pill" onClick={() => setShowMailForm(false)} type="button">Cancel</button><button className="browser-voice-submit" type="submit">Save account</button></div>
        </form>
      </dialog>
    </section>
  );
}
