import { useEffect, useState, type FormEvent } from "react";
import { localApi } from "@/browser-voice/localApi";

export function OnboardingAiConfiguration({ onDone }: { onDone: () => void }) {
  const [configuring, setConfiguring] = useState(false);
  const [providers, setProviders] = useState<Array<{ providerKey: string; displayName?: string; modelKey: string; backgroundModelKey: string; voice: string; voices?: string[]; voiceModels?: string[]; textModels?: string[] }>>([]);
  const [providerKey, setProviderKey] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [modelKey, setModelKey] = useState("gpt-realtime-2.1");
  const [backgroundModelKey, setBackgroundModelKey] = useState("gpt-5.6-sol");
  const [voice, setVoice] = useState("alloy");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!configuring) return;
    void localApi.providers().then((catalog) => setProviders(catalog.items)).catch(() => undefined);
  }, [configuring]);

  function chooseProvider(nextKey: string) {
    setProviderKey(nextKey);
    const next = providers.find((item) => item.providerKey === nextKey);
    if (!next) return;
    setModelKey(next.modelKey); setBackgroundModelKey(next.backgroundModelKey); setVoice(next.voice);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await localApi.setVoiceProvider(providerKey, {
        apiKey,
        modelKey,
        backgroundModelKey,
        voice,
      });
      setApiKey("");
      setSaved(true);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "AI provider could not be saved.",
      );
    }
  }

  return (
    <div className="browser-voice-onboarding-choice">
      {!configuring ? <><p>Would you like to connect an AI provider now? The encrypted key will be shared for use by all active Vault users, while only the master can change it.</p><div className="browser-voice-choice-actions"><button className="browser-voice-submit" onClick={() => setConfiguring(true)} type="button">Connect and share provider</button><button className="browser-voice-pill browser-voice-pill-muted" onClick={onDone} type="button">Not now</button></div></> : null}
      {configuring ? <form
        className="browser-voice-form browser-voice-onboarding-later-form"
        onSubmit={(event) => void save(event)}
      >
        <label>
          <span>AI provider</span>
          <select aria-label="AI provider" onChange={(event) => chooseProvider(event.target.value)} value={providerKey}>
            {(providers.length ? providers : [{ providerKey: "openai", displayName: "OpenAI", modelKey, backgroundModelKey, voice }]).map((item) => <option key={item.providerKey} value={item.providerKey}>{item.displayName ?? item.providerKey}</option>)}
          </select>
        </label>
        <label>
          <span>{providers.find((item) => item.providerKey === providerKey)?.displayName ?? "OpenAI"} API key</span>
          <input
            autoComplete="off"
            onChange={(event) => setApiKey(event.target.value)}
            required
            type="password"
            value={apiKey}
          />
        </label>
        <label>
          <span>Realtime model</span>
          {providers.find((item) => item.providerKey === providerKey)?.voiceModels?.length ? <select onChange={(event) => setModelKey(event.target.value)} value={modelKey}>{providers.find((item) => item.providerKey === providerKey)?.voiceModels?.map((item) => <option key={item} value={item}>{item}</option>)}</select> : <input
            onChange={(event) => setModelKey(event.target.value)}
            required
            value={modelKey}
          />}
        </label>
        <label>
          <span>Background model</span>
          {providers.find((item) => item.providerKey === providerKey)?.textModels?.length ? <select onChange={(event) => setBackgroundModelKey(event.target.value)} value={backgroundModelKey}>{providers.find((item) => item.providerKey === providerKey)?.textModels?.map((item) => <option key={item} value={item}>{item}</option>)}</select> : <input
            onChange={(event) => setBackgroundModelKey(event.target.value)}
            required
            value={backgroundModelKey}
          />}
        </label>
        <label>
          <span>Voice</span>
          {providers.find((item) => item.providerKey === providerKey)?.voices?.length ? <select onChange={(event) => setVoice(event.target.value)} value={voice}>{providers.find((item) => item.providerKey === providerKey)?.voices?.map((item) => <option key={item} value={item}>{item}</option>)}</select> : <input
            onChange={(event) => setVoice(event.target.value)}
            required
            value={voice}
          />}
        </label>
        <p className="browser-voice-form-note">This provider runs Voice and background AI work. Embeddings remain separately controlled.</p>
        {saved ? <div className="browser-voice-management-message" role="status">AI configuration saved locally.</div> : null}
        {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
        <div className="browser-voice-onboarding-actions">
          {!saved ? <button className="browser-voice-submit" type="submit">Save AI configuration</button> : null}
          <button className={saved ? "browser-voice-submit" : "browser-voice-pill browser-voice-pill-muted"} onClick={onDone} type="button">{saved ? "Enter Vault" : "Skip for now"}</button>
        </div>
      </form> : null}
    </div>
  );
}
