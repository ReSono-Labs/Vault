import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { localApi, type BuiltinPlugin, type LocalExtension, type LocalTool } from "@/browser-voice/localApi";
import { importMcpPackageFile, mcpPackageRemoveMessage, mcpPackageRowSubtitle } from "@/browser-voice/mcpPackageFlow";
import { importPluginFile, pluginRemoveMessage } from "@/browser-voice/pluginPackageFlow";
import {
  registerPluginImportCompleteHandler,
  setPendingPluginImport,
} from "@/browser-voice/pluginImportUi";
import { McpPackageSetup } from "@/browser-voice/McpPackageSetup";
import { ToolGrantTable } from "@/browser-voice/ToolGrantTable";
import { BrowserVoiceAgentsIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";

export function CapabilitiesPanel() {
  const [items, setItems] = useState<LocalExtension[]>([]);
  const [tools, setTools] = useState<LocalTool[]>([]);
  const [plugins, setPlugins] = useState<BuiltinPlugin[]>([]);
  const [openPlugin, setOpenPlugin] = useState<BuiltinPlugin | null>(null);
  const [openImported, setOpenImported] = useState<LocalExtension | null>(null);
  const [openMcp, setOpenMcp] = useState<LocalExtension | null>(null);
  const [kind, setKind] = useState<"plugin" | "skill" | "mcp" | "tool">("skill");
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const importInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    registerPluginImportCompleteHandler(async (result) => {
      setKind("plugin");
      setOpenMcp(null);
      setMessage(result.message);
      const extensions = await localApi.extensions();
      setItems(extensions.items);
      const imported = extensions.items.find(
        (item) => item.kind === "plugin" && item.identity === result.identity,
      );
      if (imported) setOpenImported(imported);
      await refresh();
    });
    return () => registerPluginImportCompleteHandler(null);
  }, []);

  async function refresh() {
    try {
      const [extensions, builtins, builtinPlugins] = await Promise.all([localApi.extensions(), localApi.tools(), localApi.builtinPlugins()]);
      setItems(extensions.items); setTools(builtins.items); setPlugins(builtinPlugins.items);
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Capabilities could not be loaded."); }
  }

  useEffect(() => { void refresh(); }, []);

  async function importSelectedFile(event: ChangeEvent<HTMLInputElement>) {
    if (kind === "mcp") {
      await importMcpPackage(event);
      return;
    }
    await importFile(event);
  }

  async function importMcpPackage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setWorking(true);
    setError(null);
    setMessage(null);
    try {
      const result = await importMcpPackageFile(file);
      if (result.identity) {
        setMessage(result.message);
        const extensions = await localApi.extensions();
        setItems(extensions.items);
        const imported = extensions.items.find(
          (item) => item.kind === "mcp" && item.identity === result.identity,
        );
        if (imported?.configuration.packageType === "hosted") setOpenMcp(imported);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "MCP package import failed.");
    } finally {
      event.target.value = "";
      setWorking(false);
    }
  }

  function clearPendingPluginImport() {
    setPendingPluginImport(null);
    setMessage(null);
  }

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || kind === "tool" || kind === "mcp") return;
    setWorking(true); setError(null); setMessage(null); clearPendingPluginImport();
    try {
      if (kind === "plugin") {
        const result = await importPluginFile(file);
        if (result.kind === "cancelled") return;
        if (result.kind === "needs_local_share") {
          setPendingPluginImport(result.pending);
          return;
        }
        setKind("plugin");
        setOpenMcp(null);
        setMessage(result.message);
        const extensions = await localApi.extensions();
        setItems(extensions.items);
        const imported = extensions.items.find(
          (item) => item.kind === "plugin" && item.identity === result.identity,
        );
        if (imported) setOpenImported(imported);
        await refresh();
        return;
      }
      const preview = await localApi.preflight(kind, file);
      const previews = "items" in preview ? preview.items : [preview];
      for (const item of previews) {
        const replacement = item.replacement
          ? window.confirm(`${item.identity} is installed. Replace it with this validated version?`)
          : true;
        if (!replacement) continue;
        await localApi.confirmExtension(kind, item.token, item.replacement);
      }
      setMessage(`${kind[0].toUpperCase() + kind.slice(1)} import complete. Capabilities remain off until explicitly enabled and granted.`);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Import failed.");
    } finally {
      event.target.value = ""; setWorking(false);
    }
  }

  async function toggle(item: LocalExtension) {
    setWorking(true); setError(null);
    try {
      await localApi.extensionState(item.extensionId, item.state === "enabled" ? "disabled" : "enabled");
      await refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Capability could not be updated."); }
    finally { setWorking(false); }
  }

  async function remove(item: LocalExtension) {
    const message = item.kind === "mcp"
      ? mcpPackageRemoveMessage(item)
      : item.kind === "plugin"
        ? pluginRemoveMessage(item)
        : `Remove ${item.displayName} from this Vault?`;
    if (!window.confirm(message)) return;
    setWorking(true); setError(null);
    try {
      await localApi.extensionState(item.extensionId, "removed");
      if (openMcp?.extensionId === item.extensionId) setOpenMcp(null);
      if (openImported?.extensionId === item.extensionId) setOpenImported(null);
      await refresh();
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Capability could not be removed."); }
    finally { setWorking(false); }
  }

  async function togglePlugin(item: BuiltinPlugin) {
    setWorking(true); setError(null);
    try { await localApi.updateBuiltinPlugin(item.key, { enabled: !item.enabled }); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Plugin could not be updated."); }
    finally { setWorking(false); }
  }

  async function savePlugin(configuration: Record<string, unknown>) {
    if (!openPlugin) return;
    setWorking(true); setError(null);
    try { const updated = await localApi.updateBuiltinPlugin(openPlugin.key, { configuration }); setOpenPlugin(updated); setMessage(`${updated.name} settings saved.`); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Plugin settings could not be saved."); }
    finally { setWorking(false); }
  }

  const toolGroups = Array.from(
    tools.reduce((groups, tool) => {
      const category = tool.category || "Other";
      groups.set(category, [...(groups.get(category) ?? []), tool]);
      return groups;
    }, new Map<string, LocalTool[]>()),
  ).sort(([left], [right]) => left.localeCompare(right));
  const kindItems = items.filter((item) => item.kind === kind);
  const showEmptyList = kind !== "tool" && kind !== "plugin" && !kindItems.length;

  return (
    <section className="browser-voice-agents" aria-labelledby="browser-voice-capabilities-title">
      <header className="browser-voice-management-heading">
        <div><span className="browser-voice-eyebrow-label">Library</span><h2 id="browser-voice-capabilities-title">Agent capabilities</h2><p>Configure what Voice and the Background Agent can use.</p></div>
      </header>
      {openPlugin ? <BuiltinPluginSetup item={openPlugin} onBack={() => setOpenPlugin(null)} onSave={savePlugin} working={working} /> : openMcp ? (
        <McpPackageSetup
          item={openMcp}
          onBack={() => setOpenMcp(null)}
          onChanged={refresh}
          onRemove={async () => {
            await remove(openMcp);
          }}
        />
      ) : openImported ? <ImportedPluginSetup item={openImported} onBack={() => setOpenImported(null)} onChanged={async () => { await refresh(); }} /> : <><div className="browser-voice-agent-filters" aria-label="Import type">
        {(["skill", "plugin", "mcp", "tool"] as const).map((value) => (
          <button aria-pressed={kind === value} className={kind === value ? "is-active" : ""} key={value} onClick={() => setKind(value)} type="button">
            {value === "mcp" ? "MCP" : `${value[0].toUpperCase()}${value.slice(1)}${value === "tool" ? "s" : ""}`}
          </button>
        ))}
      </div>
      <div className="browser-voice-section-head">
        <div>
          <h3>{kind === "mcp" ? "MCP servers" : `${kind[0].toUpperCase() + kind.slice(1)}s`}</h3>
          <p>
            {kind === "tool"
              ? `${tools.length} available`
              : `${kindItems.length} configured`}
          </p>
        </div>
        {kind !== "tool" ? (
          <>
            <input
              accept=".zip,.tar,.tgz,.gz"
              disabled={working}
              hidden
              onChange={(event) => void importSelectedFile(event)}
              ref={importInputRef}
              type="file"
            />
            <button
              className="browser-voice-submit browser-voice-section-action"
              disabled={working}
              onClick={() => importInputRef.current?.click()}
              type="button"
            >
              {working ? "Checking…" : kind === "mcp" ? "Import package" : `Import ${kind}`}
            </button>
          </>
        ) : null}
      </div>
      {message ? <p className="browser-voice-management-message" role="status">{message}</p> : null}
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
      <div className={`browser-voice-agent-list${showEmptyList ? " is-empty" : ""}`}>
        {kind === "plugin" ? plugins.map((item) => <article className={`browser-voice-agent-row is-${item.enabled ? "on" : "off"}`} key={item.key}>
          <button className="browser-voice-agent-row-main browser-voice-plugin-open" onClick={() => setOpenPlugin(item)} type="button"><span className="browser-voice-agent-mark"><BrowserVoiceAgentsIcon /></span><span><strong>{item.name}</strong><small>{item.description}</small><small>{item.enabled ? "On" : "Off"} · Built into Vault</small></span></button>
          <button aria-label={`Turn ${item.name} ${item.enabled ? "off" : "on"}`} aria-pressed={item.enabled} className="browser-voice-agent-switch" disabled={working} onClick={() => void togglePlugin(item)} role="switch" type="button"><span /></button>
        </article>) : null}
        {kind === "plugin" ? items.filter((item) => item.kind === "plugin").map((item) => <article className={`browser-voice-agent-row is-${item.state === "enabled" ? "on" : "off"}`} key={item.extensionId}>
          <button className="browser-voice-agent-row-main browser-voice-plugin-open" onClick={() => setOpenImported(item)} type="button"><span className="browser-voice-agent-mark"><BrowserVoiceAgentsIcon /></span><span><strong>{item.displayName}</strong><small>{item.description || "Plugin capability"}</small><small>{item.state === "enabled" ? "On" : "Off"} · Added to this Vault</small></span></button>
          <span className="browser-voice-capability-actions"><button aria-label={`Turn ${item.displayName} ${item.state === "enabled" ? "off" : "on"}`} aria-pressed={item.state === "enabled"} className="browser-voice-agent-switch" disabled={working} onClick={() => void toggle(item)} role="switch" type="button"><span /></button><button className="browser-voice-pill browser-voice-pill-muted" disabled={working} onClick={() => void remove(item)} type="button">Remove</button></span>
        </article>) : null}
        {kind === "tool" ? toolGroups.map(([category, categoryTools]) => (
          <details className="browser-voice-tool-category" key={category}>
            <summary><span>{category}</span><small>{categoryTools.length} {categoryTools.length === 1 ? "tool" : "tools"}</small></summary>
            <div>
              {categoryTools.map((item) => (
                <article className="browser-voice-agent-row is-on" key={item.name}>
                  <span className="browser-voice-agent-row-main"><span className="browser-voice-agent-mark"><BrowserVoiceAgentsIcon /></span><span><strong>{item.name}</strong><small>{item.description}</small><small>{item.builtIn ? "Built into this Vault" : "Imported"} · {item.audiences.map((value) => value === "voice" ? "Voice" : "Background").join(" and ")}</small></span></span>
                </article>
              ))}
            </div>
          </details>
        )) : null}
        {kind !== "plugin" && kind !== "tool" ? kindItems.map((item) => (
          <article className={`browser-voice-agent-row is-${item.state === "enabled" ? "on" : "off"}`} key={item.extensionId}>
            {item.kind === "mcp" && item.configuration.packageType === "hosted" ? (
              <button className="browser-voice-agent-row-main browser-voice-plugin-open" onClick={() => setOpenMcp(item)} type="button">
                <span className="browser-voice-agent-mark"><BrowserVoiceAgentsIcon /></span>
                <span>
                  <strong>{item.displayName}</strong>
                  <small>{item.description || "Hosted MCP package"}</small>
                  <small>{mcpPackageRowSubtitle(item)}</small>
                </span>
              </button>
            ) : (
              <span className="browser-voice-agent-row-main">
                <span className="browser-voice-agent-mark"><BrowserVoiceAgentsIcon /></span>
                <span>
                  <strong>{item.displayName}</strong>
                  <small>{item.description || `${item.kind} capability`}</small>
                  {item.kind === "mcp" ? <small>{mcpPackageRowSubtitle(item)}</small> : null}
                </span>
              </span>
            )}
            <span className="browser-voice-capability-actions"><button aria-label={`Turn ${item.displayName} ${item.state === "enabled" ? "off" : "on"}`} aria-pressed={item.state === "enabled"} className="browser-voice-agent-switch" disabled={working} onClick={() => void toggle(item)} role="switch" type="button"><span /></button><button className="browser-voice-pill browser-voice-pill-muted" disabled={working} onClick={() => void remove(item)} type="button">Remove</button></span>
          </article>
        )) : null}
        {showEmptyList ? (
          <p className="browser-voice-management-empty">
            {kind === "mcp" ? "No MCP packages imported." : `No ${kind}s imported.`}
          </p>
        ) : null}
      </div>
      </>}
    </section>
  );
}

type PluginField = { key: string; type: string; label: string; help?: string; placeholder?: string; required?: boolean; default?: unknown; choices?: { value: string; label: string }[] };

function ImportedPluginSetup({ item, onBack, onChanged }: { item: LocalExtension; onBack: () => void; onChanged: () => Promise<void> }) {
  const schema = item.configuration.configurationSchema as { fields?: PluginField[] } | undefined;
  const saved = (item.configuration.settings as Record<string, unknown> | undefined) ?? {};
  const [values, setValues] = useState<Record<string, unknown>>(() => Object.fromEntries((schema?.fields ?? []).map((field) => [field.key, field.type === "secret" ? "" : saved[field.key] ?? field.default ?? (field.type === "checkbox" ? false : field.type === "list" || field.type === "multiple_choice" ? [] : "")])));
  const [connections, setConnections] = useState<LocalExtension[]>([]);
  const [tools, setTools] = useState<Record<string, string[]>>({});
  const [userId, setUserId] = useState("");
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void Promise.all([localApi.pluginConnections(item.extensionId), localApi.me()]).then(([result, me]) => { setConnections(result.items); setUserId(me.user.userId); }).catch((caught) => setError(caught instanceof Error ? caught.message : "Plugin details could not be loaded.")); }, [item.extensionId]);
  const set = (key: string, value: unknown) => setValues((current) => ({ ...current, [key]: value }));
  async function save() { setWorking(true); setError(null); try { await localApi.savePluginSettings(item.extensionId, values); setMessage("Plugin settings saved."); await onChanged(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Settings could not be saved."); } finally { setWorking(false); } }
  async function discover(connection: LocalExtension) { setWorking(true); setError(null); try { const result = await localApi.discoverPluginTools(connection.extensionId); setTools((current) => ({ ...current, [connection.extensionId]: result.items })); setMessage(result.items.length ? "Tools are ready for you to choose." : "This connection did not report any tools."); } catch (caught) { setError(caught instanceof Error ? caught.message : "Vault could not reach this plugin service."); } finally { setWorking(false); } }
  return <section className="browser-voice-plugin-setup">
    <button className="browser-voice-pill" onClick={onBack} type="button">← Plugins</button>
    <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">Added to this Vault</span><h3>{item.displayName}</h3><p>{item.description}</p></div><span className={`browser-voice-state ${item.state === "enabled" ? "is-ready" : ""}`}>{item.state === "enabled" ? "On" : "Off"}</span></div>
    {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}{message ? <p className="browser-voice-management-message" role="status">{message}</p> : null}
    {(schema?.fields?.length ?? 0) > 0 ? <form className="browser-voice-form" onSubmit={(event) => { event.preventDefault(); void save(); }}><h4>Settings</h4>{schema!.fields!.map((field) => <PluginFieldControl field={field} key={field.key} set={set} value={values[field.key]} />)}<button className="browser-voice-submit" disabled={working} type="submit">{working ? "Saving…" : "Save settings"}</button></form> : null}
    {connections.length ? <div className="browser-voice-form"><h4>Tools</h4><p className="browser-voice-form-note">Start the plugin service, then check tools. Mark Voice and Background, choose Read or Read &amp; write, then save.</p>{connections.map((connection) => <div className="browser-voice-plugin-connection" key={connection.extensionId}><div className="browser-voice-section-head"><div><strong>{connection.displayName}</strong><small>{connection.description}</small></div><button className="browser-voice-pill" disabled={working || item.state !== "enabled"} onClick={() => void discover(connection)} type="button">Check tools</button></div><ToolGrantTable extensionId={connection.extensionId} onError={setError} onMessage={setMessage} onWorking={setWorking} tools={tools[connection.extensionId] ?? []} userId={userId} working={working} /></div>)}</div> : <p className="browser-voice-management-empty">This plugin contains instructions only. It does not add a connected tool.</p>}
  </section>;
}

function PluginFieldControl({ field, value, set }: { field: PluginField; value: unknown; set: (key: string, value: unknown) => void }) {
  const selected = Array.isArray(value) ? value : [];
  return <fieldset className="browser-voice-plugin-field"><legend>{field.label}</legend>{field.help ? <small>{field.help}</small> : null}{field.type === "secret" ? <small>Leave this empty later to keep the saved value.</small> : null}
    {field.type === "long_text" || field.type === "list" ? <textarea onChange={(event) => set(field.key, field.type === "list" ? event.target.value.split("\n").map((part) => part.trim()).filter(Boolean) : event.target.value)} placeholder={field.placeholder} value={field.type === "list" ? selected.join("\n") : String(value ?? "")} /> : null}
    {field.type === "choice" ? <select onChange={(event) => set(field.key, event.target.value)} value={String(value ?? "")}>{field.choices?.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select> : null}
    {field.type === "multiple_choice" ? <div>{field.choices?.map((choice) => <label key={choice.value}><input checked={selected.includes(choice.value)} onChange={(event) => set(field.key, event.target.checked ? [...selected, choice.value] : selected.filter((item) => item !== choice.value))} type="checkbox" /> <span>{choice.label}</span></label>)}</div> : null}
    {field.type === "checkbox" ? <label><input checked={Boolean(value)} onChange={(event) => set(field.key, event.target.checked)} type="checkbox" /> <span>On</span></label> : null}
    {!['long_text','list','choice','multiple_choice','checkbox'].includes(field.type) ? <input onChange={(event) => set(field.key, field.type === "number" ? Number(event.target.value) : event.target.value)} placeholder={field.placeholder} required={field.required && field.type !== "secret"} type={field.type === "secret" ? "password" : field.type === "number" ? "number" : field.type === "url" ? "url" : "text"} value={String(value ?? "")} /> : null}
  </fieldset>;
}

function lines(value: unknown) { return Array.isArray(value) ? value.join("\n") : ""; }
function BuiltinPluginSetup({ item, onBack, onSave, working }: { item: BuiltinPlugin; onBack: () => void; onSave: (value: Record<string, unknown>) => Promise<void>; working: boolean }) {
  const [value, setValue] = useState<Record<string, unknown>>(item.configuration);
  const [agentMail, setAgentMail] = useState("");
  const [mailError, setMailError] = useState<string | null>(null);
  useEffect(() => { if (item.key === "agent_mail") void localApi.agentMailAccounts().then((result) => setAgentMail(result.items[0]?.emailAddress || "")).catch(() => undefined); }, [item.key]);
  const set = (key: string, next: unknown) => setValue((current) => ({ ...current, [key]: next }));
  const list = (key: string) => lines(value[key]).split("\n").map((part) => part.trim()).filter(Boolean);
  return <section className="browser-voice-plugin-setup">
    <button className="browser-voice-pill" onClick={onBack} type="button">← Plugins</button>
    <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">Built into Vault</span><h3>{item.name}</h3><p>{item.description}</p></div><span className={`browser-voice-state ${item.enabled ? "is-ready" : ""}`}>{item.enabled ? "On" : "Off"}</span></div>
    <form className="browser-voice-form" onSubmit={(event) => { event.preventDefault(); void onSave(value); }}>
      {item.key === "weather" ? <><label><span>Primary location</span><input onChange={(event) => set("primaryLocation", event.target.value)} placeholder="City, state, or country" value={String(value.primaryLocation || "")} /></label><label><span>Other saved locations</span><small>One location per line, up to 12.</small><textarea onChange={(event) => set("savedLocations", event.target.value.split("\n"))} value={lines(value.savedLocations)} /></label></> : null}
      {item.key === "news" ? <><label><span>Main news topic</span><select onChange={(event) => set("defaultCategory", event.target.value)} value={String(value.defaultCategory || "top")}>{["top","world","business","technology","science","health","sports","entertainment"].map((topic) => <option key={topic} value={topic}>{topic[0].toUpperCase() + topic.slice(1)}</option>)}</select></label><label><span>Headlines at a time</span><input max="10" min="1" onChange={(event) => set("headlineCount", Number(event.target.value))} type="number" value={Number(value.headlineCount || 5)} /></label><p className="browser-voice-form-note">Trusted news feeds are already included. You do not need to add any web addresses.</p></> : null}
      {item.key === "markets" ? <label><span>Stocks to follow</span><small>Enter one ticker per line, such as AAPL or MSFT.</small><textarea onChange={(event) => set("watchlist", event.target.value.split("\n"))} placeholder={"AAPL\nMSFT"} value={lines(value.watchlist)} /></label> : null}
      {item.key === "local_events" ? <><label><span>Home city or area</span><input onChange={(event) => set("homeLocation", event.target.value)} placeholder="Tampa, Florida" value={String(value.homeLocation || "")} /></label><label><span>How far should Vault look?</span><select onChange={(event) => set("radiusMiles", Number(event.target.value))} value={Number(value.radiusMiles || 25)}>{[5,10,25,50,100].map((miles) => <option key={miles} value={miles}>{miles} miles</option>)}</select></label><label><span>What do you enjoy?</span><small>One interest per line, such as live music or family activities.</small><textarea onChange={(event) => set("interests", event.target.value.split("\n"))} value={lines(value.interests)} /></label></> : null}
      {item.key === "agent_mail" ? agentMail ? <p className="browser-voice-form-note">Connected mailbox: {agentMail}</p> : <><p className="browser-voice-form-note">Use a separate email account for messages sent and received by your assistant. Your password is encrypted inside this Vault.</p><label><span>Mailbox name</span><input name="displayName" placeholder="Vault Agent Mail" required /></label><label><span>Email address</span><input name="emailAddress" required type="email" /></label><label><span>Incoming mail server</span><input name="imapHost" placeholder="imap.example.com" required /></label><label><span>Incoming port</span><input defaultValue="993" max="65535" min="1" name="imapPort" required type="number" /></label><label><span>Incoming username</span><input name="imapUsername" required /></label><label><span>Incoming password</span><input name="imapPassword" required type="password" /></label><label><span>Outgoing mail server</span><input name="smtpHost" placeholder="smtp.example.com" required /></label><label><span>Outgoing port</span><input defaultValue="465" max="65535" min="1" name="smtpPort" required type="number" /></label><label><span>Outgoing username</span><input name="smtpUsername" required /></label><label><span>Outgoing password</span><input name="smtpPassword" required type="password" /></label>{mailError ? <p className="browser-voice-management-error" role="alert">{mailError}</p> : null}<button className="browser-voice-submit" disabled={working} onClick={async (event) => { event.preventDefault(); const form = event.currentTarget.form!; const data = new FormData(form); const text = (name: string) => String(data.get(name) || "").trim(); try { const account = await localApi.connectAgentMail({ displayName:text("displayName"), credentials:{emailAddress:text("emailAddress"),imap:{host:text("imapHost"),port:Number(text("imapPort")),username:text("imapUsername"),password:text("imapPassword"),useTls:true},smtp:{host:text("smtpHost"),port:Number(text("smtpPort")),username:text("smtpUsername"),password:text("smtpPassword"),useTls:true}},validateConnection:true}); setAgentMail(account.emailAddress); setMailError(null); } catch (caught) { setMailError(caught instanceof Error ? caught.message : "Mailbox could not be connected."); } }} type="button">Connect mailbox</button></> : null}
      {item.key !== "agent_mail" ? <button className="browser-voice-submit" disabled={working} type="submit">{working ? "Saving…" : "Save settings"}</button> : null}
    </form>
  </section>;
}
