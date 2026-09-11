import { useEffect, useState, type FormEvent } from "react";
import { localApi, type ExternalMemoryIntegration, type ExternalMemoryPairing } from "@/browser-voice/localApi";
import { BrowserVoiceConnectionCategoryIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";

export function MemoryPanel() {
  const [integrations, setIntegrations] = useState<ExternalMemoryIntegration[]>([]);
  const [newCredential, setNewCredential] = useState<string | null>(null);
  const [pairing, setPairing] = useState<ExternalMemoryPairing | null>(null);
  const [pairingComplete, setPairingComplete] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    localApi.externalMemoryIntegrations().then((result) => setIntegrations(result.items))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Vault Memory connections could not be loaded."));
  }, []);
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("memoryPairing");
    if (!code) return;
    localApi.externalMemoryPairing(code).then(setPairing)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Pairing request could not be loaded."));
  }, []);

  async function createIntegration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setNewCredential(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const integration = await localApi.createExternalMemoryIntegration({
        displayName: String(data.get("displayName") || "").trim(),
        adapterKind: String(data.get("adapterKind") || "").trim(),
        grants: ["search", "propose", "correct", "forget"],
      });
      setIntegrations((current) => [...current, integration]);
      setNewCredential(integration.credential); setShowCreate(false); form.reset();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Vault Memory access could not be created."); }
  }
  async function revokeIntegration(integrationId: string) {
    try {
      await localApi.revokeExternalMemoryIntegration(integrationId);
      setIntegrations((current) => current.map((item) => item.integrationId === integrationId ? { ...item, status: "revoked" } : item));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Vault Memory access could not be revoked."); }
  }
  async function approvePairing() {
    if (!pairing) return;
    try {
      const integration = await localApi.approveExternalMemoryPairing(pairing.pairingId);
      setIntegrations((current) => [...current, integration]);
      setPairing(null); setPairingComplete(true);
      window.history.replaceState({}, "", window.location.pathname);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Pairing request could not be approved."); }
  }
  async function removeIntegration(integrationId: string) {
    try {
      await localApi.removeExternalMemoryIntegration(integrationId);
      setIntegrations((current) => current.filter((item) => item.integrationId !== integrationId));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Revoked connection could not be removed."); }
  }

  return (
    <section className="browser-voice-connections" aria-labelledby="memory-title">
      <header className="browser-voice-management-heading"><div><span className="browser-voice-eyebrow-label">Memory</span><h2 id="memory-title">Vault Memory</h2><p>Shared memory connections for Hermes, OpenClaw, and compatible agent plugins.</p></div></header>
      <section className="browser-voice-management-section">
        <div className="browser-voice-section-head"><div><span className="browser-voice-eyebrow-label">Agent memory</span><h3>Vault Memory access</h3><p>Connected agents can recall and propose memory without becoming Vault agents.</p></div>{!pairing && !pairingComplete ? <button className="browser-voice-submit" onClick={() => setShowCreate((value) => !value)} type="button">{showCreate ? "Cancel" : "Add agent memory"}</button> : null}</div>
        {pairing ? <div className="browser-voice-connection-credential" role="status"><strong>Connect {pairing.displayName}?</strong><span>{pairing.adapterKind} requests {pairing.grants.join(", ")} access for this account and workspace.</span><button onClick={() => void approvePairing()} type="button">Connect</button></div> : null}
        {pairingComplete ? <div className="browser-voice-connection-credential" role="status"><strong>Pairing complete</strong><span>The plugin received approval. Return to the terminal to finish setup.</span></div> : null}
        {integrations.map((item) => <article className="browser-voice-connection-row" key={item.integrationId}>
          <span className="browser-voice-connection-mark"><BrowserVoiceConnectionCategoryIcon category="provider" /></span>
          <span><strong>{item.displayName}</strong><small>{item.adapterKind} · {item.status} · {item.grants.join(", ")}</small></span>
          {item.status === "active" ? <button className="browser-voice-pill browser-voice-pill-muted" onClick={() => void revokeIntegration(item.integrationId)} type="button">Revoke</button> : <button className="browser-voice-pill browser-voice-pill-muted" onClick={() => void removeIntegration(item.integrationId)} type="button">Remove</button>}
        </article>)}
        {!integrations.length ? <p className="browser-voice-management-empty">No Vault Memory connections.</p> : null}
        {newCredential ? <div className="browser-voice-connection-credential" role="status"><strong>Copy this credential now</strong><code>{newCredential}</code><span>Vault will not show it again.</span></div> : null}
        {showCreate && !pairing && !pairingComplete ? <form className="browser-voice-connection-form" onSubmit={(event) => void createIntegration(event)}>
          <div className="browser-voice-connection-form-grid"><label><span>Connection name</span><input maxLength={128} name="displayName" placeholder="Hermes" required /></label><label><span>Adapter</span><input maxLength={64} name="adapterKind" placeholder="hermes" required /></label></div>
          <p className="browser-voice-connection-security-note">Access is restricted to this account and workspace. Enabled operations are automatically accepted until you revoke access.</p>
          <button type="submit">Create agent access</button>
        </form> : null}
      </section>
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
    </section>
  );
}
