import { useEffect, useState } from "react";

import type { HostedLimits, HostedLimitsView } from "@/browser-voice/api/extensions";
import { localApi } from "@/browser-voice/localApi";
import { PageSection } from "@/browser-voice/presentation/ManagementLayout";

const gigabytes = (bytes: number) => `${(bytes / 1024 ** 3).toFixed(bytes < 10 * 1024 ** 3 ? 1 : 0)} GB`;
const SOURCE: Record<string, string> = {
  cgroup: "the limit set for Vault (container or service)",
  system: "this computer",
  affinity: "the CPUs Vault may use",
};

/** Device owner: how much of this computer each hosted package may use. Shares of what Vault
 *  itself may use, so the defaults fit any hardware, in Docker or a native install. */
export function HostedLimitsSection() {
  const [view, setView] = useState<HostedLimitsView | null>(null);
  const [draft, setDraft] = useState<HostedLimits | null>(null);
  const [ports, setPorts] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  function show(next: HostedLimitsView) {
    setView(next);
    setDraft(next.limits);
    setPorts(next.limits.extraPorts.join(", "));
  }
  useEffect(() => { void localApi.hostedLimits().then(show).catch(() => setError("Limits could not be loaded.")); }, []);
  if (!view || !draft) return error ? <p className="browser-voice-management-error" role="alert">{error}</p> : null;

  const memory = Math.max(128 * 1024 ** 2, Math.floor(view.host.memoryBytes * draft.memoryPercent / 100));
  const cpus = Math.max(1, Math.min(Math.floor(view.host.cpus), Math.floor(view.host.cpus * draft.cpuPercent / 100) || 1));

  async function save(restart: boolean) {
    if (!draft) return;
    setWorking(true); setError(null); setMessage(null);
    try {
      const extraPorts = ports.split(/[\s,]+/).filter(Boolean).map(Number);
      show(await localApi.saveHostedLimits({ ...draft, extraPorts }, restart));
      setMessage(restart ? "Saved. Hosted packages are restarting with the new limits." : "Saved. Each package uses the new limits from its next start.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Limits could not be saved.");
    } finally {
      setWorking(false);
    }
  }

  const number = (key: "memoryPercent" | "cpuPercent" | "maxProcesses") =>
    (event: React.ChangeEvent<HTMLInputElement>) => setDraft({ ...draft, [key]: Number(event.currentTarget.value) });
  return (
    <PageSection title="Hosted packages" titleId="settings-hosted-limits"
      description="How much of this computer each package that runs its own program may use. A package that goes over its memory or process limit is stopped and says why.">
      <p className="vault-section-note">
        Vault may use {gigabytes(view.host.memoryBytes)} of memory ({SOURCE[view.host.memorySource] ?? view.host.memorySource})
        {" "}and {view.host.cpus % 1 ? view.host.cpus.toFixed(1) : view.host.cpus} CPUs ({SOURCE[view.host.cpuSource] ?? view.host.cpuSource}).
      </p>
      <form className="browser-voice-form" onSubmit={(event) => { event.preventDefault(); void save(false); }}>
        <label><span>Memory per package: {draft.memoryPercent}% (about {gigabytes(memory)})</span>
          <input disabled={working} max={90} min={5} onChange={number("memoryPercent")} step={5} type="range" value={draft.memoryPercent} /></label>
        <label><span>CPU per package: {draft.cpuPercent}% ({cpus} of {Math.floor(view.host.cpus) || 1} CPUs, lower priority than Vault)</span>
          <input disabled={working} max={100} min={10} onChange={number("cpuPercent")} step={10} type="range" value={draft.cpuPercent} /></label>
        <label><span>Processes per package</span>
          <input disabled={working} max={4096} min={4} onChange={number("maxProcesses")} type="number" value={draft.maxProcesses} /></label>
        <label><span>Network</span>
          <select disabled={working} onChange={(event) => setDraft({ ...draft, network: event.currentTarget.value as HostedLimits["network"] })} value={draft.network}>
            <option value="standard">Standard: web ports, its own workspace&apos;s packages, and the ports below</option>
            <option value="open">Open: any port (less safe)</option>
          </select></label>
        {draft.network === "standard" ? <label><span>Extra ports (for example 587 for sending mail, 993 for reading it)</span>
          <input disabled={working} onChange={(event) => setPorts(event.currentTarget.value)} placeholder="587, 993" value={ports} /></label> : null}
        <div className="browser-voice-capability-actions">
          <button className="browser-voice-submit" disabled={working} type="submit">Save</button>
          <button className="browser-voice-pill" disabled={working} onClick={() => void save(true)} type="button">Save and restart packages</button>
        </div>
      </form>
      {message ? <p className="browser-voice-management-message" role="status">{message}</p> : null}
      {error ? <p className="browser-voice-management-error" role="alert">{error}</p> : null}
    </PageSection>
  );
}
