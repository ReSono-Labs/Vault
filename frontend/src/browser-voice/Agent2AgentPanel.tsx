import { useEffect, useRef, useState, type FormEvent } from "react";
import { InboundBearer } from "@/browser-voice/InboundBearer";
import { localApi, type A2AConnection, type A2ANotification } from "@/browser-voice/localApi";
import { BrowserVoiceConnectionsIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";
import { PageHeader, PageSection } from "@/browser-voice/presentation/ManagementLayout";
import { whenVisible } from "@/browser-voice/polling";

export function Agent2AgentPanel() {
  const [connections, setConnections] = useState<A2AConnection[]>([]);
  const [notifications, setNotifications] = useState<A2ANotification[]>([]);
  const [optionOn, setOptionOn] = useState(false);
  const [listen, setListen] = useState<{ cardUrl: string; rpcUrl: string; tokenHint: string } | null>(null);
  const [companion, setCompanion] = useState<{ status: string; displayName?: string } | null>(null);
  const [companionCode, setCompanionCode] = useState("");
  const [companionPending, setCompanionPending] = useState<{ pairingId: string; displayName: string } | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedActivity, setSelectedActivity] = useState<A2ANotification | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const connectDialogRef = useRef<HTMLDialogElement | null>(null);
  const detailDialogRef = useRef<HTMLDialogElement | null>(null);
  const activityDialogRef = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const dialog = connectDialogRef.current;
    if (!dialog) return;
    if (adding && !dialog.open) typeof dialog.showModal === "function" ? dialog.showModal() : dialog.setAttribute("open", "");
    if (!adding && dialog.open) typeof dialog.close === "function" ? dialog.close() : dialog.removeAttribute("open");
  }, [adding]);
  useEffect(() => {
    const dialog = detailDialogRef.current;
    if (!dialog) return;
    if (selectedAgent && !dialog.open) typeof dialog.showModal === "function" ? dialog.showModal() : dialog.setAttribute("open", "");
    if (!selectedAgent && dialog.open) typeof dialog.close === "function" ? dialog.close() : dialog.removeAttribute("open");
  }, [selectedAgent]);
  useEffect(() => {
    const dialog = activityDialogRef.current;
    if (!dialog) return;
    if (selectedActivity && !dialog.open) typeof dialog.showModal === "function" ? dialog.showModal() : dialog.setAttribute("open", "");
    if (!selectedActivity && dialog.open) typeof dialog.close === "function" ? dialog.close() : dialog.removeAttribute("open");
  }, [selectedActivity]);

  async function refresh() {
    try {
      const [connected, activity, plugins, companionState] = await Promise.all([
        localApi.a2aConnections(), localApi.a2aNotifications(), localApi.builtinPlugins(), localApi.linkCompanion(),
      ]);
      const enabled = Boolean(plugins.items?.find((item) => item.key === "agent2agent")?.enabled);
      setConnections(Array.isArray(connected?.items) ? connected.items : []);
      setNotifications(Array.isArray(activity?.items) ? activity.items : []);
      setOptionOn(enabled);
      setCompanion(companionState);
      if (enabled) {
        const inbound = await localApi.a2aListen();
        setListen(inbound);
      } else {
        setListen(null);
      }
      setError(null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Agent2Agent could not be loaded."); }
  }
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(whenVisible(() => void refresh()), 5000);
    return () => window.clearInterval(timer);
  }, []);
  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget; const data = new FormData(form);
    try {
      await localApi.connectA2A({ displayName: String(data.get("displayName") || "").trim(), cardUrl: String(data.get("cardUrl") || "").trim(), token: String(data.get("token") || "") });
      form.reset(); setAdding(false); await refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "External agent could not be connected."); }
  }
  async function remove(connectionId: string) {
    try { await localApi.removeA2A(connectionId); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "External agent could not be removed."); }
  }
  const agents = connections.map((connection) => ({ key: `a2a-${connection.connectionId}`, connection }));
  const selected = agents.find((item) => item.key === selectedAgent);
  const selectedCard = selected?.connection?.agentCard;
  return <section aria-labelledby="agent2agent-title" className="browser-voice-connections browser-voice-a2a vault-page">
    <PageHeader description="Agents that Voice and the Background Agent can work with, using the A2A standard." title="External agents" titleId="agent2agent-title" />
    <PageSection actions={<button className="browser-voice-submit" disabled={!optionOn} onClick={() => setAdding(true)} type="button">Connect agent</button>} description={optionOn ? "Select an agent to view its Agent Card, access, skills, and connection details." : "Turn on Agent2Agent under Library (Built into Vault) before connecting an agent."} title="Connected agents" titleId="a2a-connected">
      {agents.map((item) => <button className="browser-voice-connection-row browser-voice-a2a-standard-row" key={item.key} onClick={() => setSelectedAgent(item.key)} type="button"><span className="browser-voice-connection-mark"><BrowserVoiceConnectionsIcon /></span><span><strong>{item.connection.displayName}</strong><small>A2A connected · Voice and Background Agent available</small></span><span className="browser-voice-state is-ready">Connected</span></button>)}
      {!agents.length ? <p className="browser-voice-management-empty">No external agents are connected.</p> : null}
    </PageSection>
    <AgentActivity items={notifications} onOpen={setSelectedActivity} />
    <PageSection description="Pair this computer's Link Companion, and share this Vault's Agent Card with other agents." title="Setup" titleId="a2a-setup">
      <div className="vault-subsection"><h4>Link Companion</h4><p>{companion?.status === "paired" ? `Paired with ${companion.displayName || "this computer's Link connector"}. Disconnect in Link to revoke platform access.` : `${companion?.status === "needs_pairing" ? "Link Companion needs to be paired again; its access was revoked. " : ""}Confirm this Vault with the host connector. Do not type ports. Run sudo resono-link-connector companion setup vault, then enter the pairing code here.`}</p>
      {companion?.status === "paired" ? <div className="browser-voice-modal-actions"><button className="browser-voice-account-danger" onClick={() => { void (async () => { try { await localApi.unpairLinkCompanion(); setCompanionCode(""); setCompanionPending(null); await refresh(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Link Companion could not be disconnected."); } })(); }} type="button">Disconnect Link Companion</button></div> : <form onSubmit={(event) => { event.preventDefault(); void (async () => { try { const pending = await localApi.linkCompanionPairing(companionCode.trim()); setCompanionPending(pending); setError(null); } catch (caught) { setError(caught instanceof Error ? caught.message : "That pairing code is not waiting."); } })(); }}><label><span className="browser-voice-eyebrow-label">Pairing code</span><input value={companionCode} onChange={(event) => setCompanionCode(event.target.value)} placeholder="ABCD-EF01" required /></label><div className="browser-voice-modal-actions"><button className="browser-voice-submit" type="submit">Look up request</button>{companionPending ? <button className="browser-voice-submit" onClick={(event) => { event.preventDefault(); void (async () => { try { await localApi.approveLinkCompanionPairing(companionPending.pairingId); setCompanionCode(""); setCompanionPending(null); await refresh(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Link Companion could not be confirmed."); } })(); }} type="button">Confirm {companionPending.displayName}</button> : null}</div></form>}
      </div>
      {optionOn && listen ? <div className="vault-subsection"><h4>Inbound Agent Card</h4><p>Peers send work to the Background Agent with this Card URL and bearer. Keep the token distinct from outbound connection tokens.</p><dl className="browser-voice-a2a-facts"><div className="is-wide"><dt>Agent Card</dt><dd>{listen.cardUrl}</dd></div><div className="is-wide"><dt>Inbound bearer</dt><dd><InboundBearer hint={listen.tokenHint} onChanged={(tokenHint) => setListen((current) => current ? { ...current, tokenHint } : current)} /></dd></div></dl></div> : null}
    </PageSection>
    <dialog aria-labelledby="a2a-connect-title" className="browser-voice-modal" onCancel={() => setAdding(false)} onClose={() => setAdding(false)} ref={connectDialogRef}><form onSubmit={(event) => void connect(event)}><div className="browser-voice-modal-head"><div><span className="browser-voice-eyebrow-label">Agent connection</span><h2 id="a2a-connect-title">Connect external agent</h2></div><button aria-label="Close agent connection" className="browser-voice-modal-close" onClick={() => setAdding(false)} type="button">×</button></div><div className="browser-voice-modal-fields"><label><span>Name</span><input name="displayName" placeholder="Hermes" required /></label><label><span>Agent Card URL</span><input name="cardUrl" placeholder="https://agent.example/.well-known/agent-card.json" required type="url" /></label><label className="browser-voice-modal-wide"><span>Bearer token (if required)</span><input autoComplete="off" name="token" type="password" /></label></div><p className="browser-voice-form-note">Vault validates the Agent Card and encrypts the credential locally.</p><div className="browser-voice-modal-actions"><button className="browser-voice-pill" onClick={() => setAdding(false)} type="button">Cancel</button><button className="browser-voice-submit" type="submit">Connect agent</button></div></form></dialog>
    <dialog aria-labelledby="a2a-detail-title" className="browser-voice-modal" onCancel={() => setSelectedAgent(null)} onClose={() => setSelectedAgent(null)} ref={detailDialogRef}>{selected ? <div className="browser-voice-a2a-dialog"><div className="browser-voice-modal-head"><div><span className="browser-voice-eyebrow-label">A2A Agent Card</span><h2 id="a2a-detail-title">{selected.connection.displayName}</h2></div><button aria-label="Close agent details" className="browser-voice-modal-close" onClick={() => setSelectedAgent(null)} type="button">×</button></div><p>{selectedCard?.description || "Connected external agent."}</p><dl className="browser-voice-a2a-facts"><div><dt>A2A</dt><dd>Connected</dd></div><div><dt>Voice</dt><dd>Available</dd></div><div><dt>Background Agent</dt><dd>Available</dd></div><div><dt>Protocol</dt><dd>{`${selectedCard?.supportedInterfaces?.[0]?.protocolBinding || "JSONRPC"} ${selectedCard?.supportedInterfaces?.[0]?.protocolVersion || "1.0"}`}</dd></div>{selectedCard?.version ? <div><dt>Version</dt><dd>{selectedCard.version}</dd></div> : null}<div className="is-wide"><dt>Agent Card</dt><dd>{selected.connection.cardUrl}</dd></div></dl>{selectedCard?.skills?.length ? <div className="browser-voice-a2a-skills"><h5>Skills</h5><div>{selectedCard.skills.map((skill, index) => <span key={skill.id || `${skill.name}-${index}`}>{skill.name || skill.id}</span>)}</div></div> : null}<div className="browser-voice-modal-actions"><button className="browser-voice-account-danger" onClick={() => { setSelectedAgent(null); void remove(selected.connection.connectionId); }} type="button">Remove connection</button><button className="browser-voice-pill" onClick={() => setSelectedAgent(null)} type="button">Close</button></div></div> : null}</dialog>
    <dialog aria-labelledby="a2a-activity-title" className="browser-voice-modal" onCancel={() => setSelectedActivity(null)} onClose={() => setSelectedActivity(null)} ref={activityDialogRef}>{selectedActivity ? <div className="browser-voice-a2a-dialog"><div className="browser-voice-modal-head"><div><span className="browser-voice-eyebrow-label">Completed agent work</span><h2 id="a2a-activity-title">{selectedActivity.agentName}</h2></div><button aria-label="Close activity details" className="browser-voice-modal-close" onClick={() => setSelectedActivity(null)} type="button">×</button></div><dl className="browser-voice-a2a-facts"><div><dt>Requested by</dt><dd>{selectedActivity.ownerKind === "voice" ? "Voice" : "Background Agent"}</dd></div><div><dt>Completed</dt><dd>{selectedActivity.completedAt ? new Date(selectedActivity.completedAt).toLocaleString() : "Completed"}</dd></div></dl><div className="browser-voice-a2a-review"><h5>Summary</h5><p>{selectedActivity.summary || "Completed without a summary."}</p></div><div className="browser-voice-modal-actions"><button className="browser-voice-pill" onClick={() => setSelectedActivity(null)} type="button">Close</button></div></div> : null}</dialog>
    {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
  </section>;
}

/** Recent completed A2A requests: one summary line, then one group per agent. */
function AgentActivity({ items, onOpen }: { items: A2ANotification[]; onOpen: (item: A2ANotification) => void }) {
  const latest = items[0];
  const groups = new Map<string, A2ANotification[]>();
  for (const item of items) groups.set(item.agentName, [...(groups.get(item.agentName) ?? []), item]);
  const stamp = (value: string | null) => value ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
  return <details className="vault-section vault-collapsible vault-a2a-activity">
    <summary>
      <span className="vault-collapsible-title">Recent agent work</span>
      <small>{items.length ? `${items.length} completed · latest ${stamp(latest.completedAt || latest.updatedAt)} from ${latest.agentName}` : "No completed agent work yet."}</small>
    </summary>
    {[...groups.entries()].map(([agent, list]) => <details className="vault-a2a-agent-group" key={agent} open={groups.size === 1}>
      <summary><strong>{agent}</strong><small>{list.length} {list.length === 1 ? "request" : "requests"}</small></summary>
      {list.map((item) => <button className="browser-voice-connection-row browser-voice-a2a-activity-row" key={item.taskId} onClick={() => onOpen(item)} type="button">
        <span><strong>{stamp(item.completedAt || item.updatedAt)}</strong><small>{item.summary || "Completed without a summary."}</small></span>
        <span className="browser-voice-state is-ready">Completed</span>
      </button>)}
    </details>)}
  </details>;
}
