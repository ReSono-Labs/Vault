import { useEffect, useState } from "react";
import { localApi, type CommandSettings } from "@/browser-voice/localApi";
import { BrowserVoiceWorkspaceIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";

/** Settings > Commands: one switch for the whole Vault, controlled by the master account. */
export function SettingsCommandsSection({ isAdmin }: { isAdmin: boolean }) {
  const [settings, setSettings] = useState<CommandSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    localApi.commandSettings().then(setSettings).catch(() => setSettings(null));
  }, []);

  if (!settings) return null;
  const on = settings.enabled;

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      setSettings(await localApi.setCommandsEnabled(!on));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Commands could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="browser-voice-section-head">
        <div>
          <h3>Commands</h3>
          <p>
            Let agents run command-line programs inside your folders: tests, builds, git and data tools. In Chat
            you approve every command first. The Background Agent can only run read-only programs. Voice never
            runs commands.
          </p>
        </div>
      </div>
      <div className="browser-voice-agent-list">
        <article className={`browser-voice-agent-row is-${on ? "on" : "off"}`}>
          <span className="browser-voice-agent-row-main">
            <span className="browser-voice-agent-mark">
              <BrowserVoiceWorkspaceIcon />
            </span>
            <span>
              <strong>Commands</strong>
              <small>
                {!settings.available
                  ? "Not available on this computer."
                  : isAdmin
                    ? "For everyone on this Vault. Commands can use the internet."
                    : "The master account turns this on or off for everyone."}
              </small>
              <small>{on ? "On" : "Off"} · This Vault</small>
            </span>
          </span>
          {isAdmin ? (
            <button
              aria-label={`Turn commands ${on ? "off" : "on"}`}
              aria-pressed={on}
              className="browser-voice-agent-switch"
              disabled={busy || !settings.available}
              onClick={() => void toggle()}
              role="switch"
              type="button"
            >
              <span />
            </button>
          ) : null}
        </article>
      </div>
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
    </>
  );
}
