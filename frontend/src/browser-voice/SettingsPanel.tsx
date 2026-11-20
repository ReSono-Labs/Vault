import { setTheme, storedTheme, type VaultTheme } from "@/browser-voice/theme";
import { useEffect, useState } from "react";
import { localApi } from "@/browser-voice/localApi";
import { PageHeader, PageSection, TabPanel, Tabs, type TabItem } from "@/browser-voice/presentation/ManagementLayout";
import { SettingsCommandsSection } from "@/browser-voice/commands/SettingsCommandsSection";
import { SettingsFoldersSection } from "@/browser-voice/folders/SettingsFoldersSection";
import { BackgroundSettings } from "@/browser-voice/background/BackgroundSettings";
import { BrowserVoiceMicrophoneIcon, ChatIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";
import { livePanelShown, setLivePanelShown, type LiveSurface } from "@/browser-voice/conversation/livePanel";

type SettingsTab = "display" | "folders" | "commands" | "assistant";

export function SettingsPanel({ isAdmin = false, onOpenBackgroundWork }: { isAdmin?: boolean; onOpenBackgroundWork?: () => void }) {
  const [tab, setTab] = useState<SettingsTab>("display");
  // Folders and Commands only get a tab where this Vault offers them.
  const [foldersAvailable, setFoldersAvailable] = useState(false);
  const [commandsAvailable, setCommandsAvailable] = useState(false);
  useEffect(() => {
    let current = true;
    localApi.folders().then(value => { if (current) setFoldersAvailable(value.available); }).catch(() => undefined);
    localApi.commandSettings().then(() => { if (current) setCommandsAvailable(true); }).catch(() => undefined);
    return () => { current = false; };
  }, []);
  const tabs: TabItem<SettingsTab>[] = [
    { id: "display", label: "Display" },
    ...(foldersAvailable ? [{ id: "folders" as const, label: "Folders" }] : []),
    ...(commandsAvailable ? [{ id: "commands" as const, label: "Commands" }] : []),
    { id: "assistant", label: "Background assistant" },
  ];
  const selected = tabs.some(item => item.id === tab) ? tab : "display";
  return (
    <section className="browser-voice-agents vault-page is-readable" aria-labelledby="browser-voice-settings-title">
      <PageHeader eyebrow="Vault" title="Settings" titleId="browser-voice-settings-title"
        description="Manage optional features for this Vault and this browser." />
      <Tabs idPrefix="settings" label="Settings sections" onChange={setTab} tabs={tabs} value={selected} />

      {selected === "display" ? <TabPanel id="display" idPrefix="settings">
        <PageSection title="Appearance" titleId="settings-appearance" description="Choose how Vault looks in this browser.">
          <AppearancePicker />
        </PageSection>
        <PageSection title="Live window" titleId="settings-live-window"
          description="Show the live memory and tool preparation while you speak or type. Hiding it only hides the window; live preparation keeps working.">
          <p className="vault-section-note">Applies to this browser.</p>
          <LiveWindowSwitches />
        </PageSection>
      </TabPanel> : null}

      {selected === "folders" ? <TabPanel id="folders" idPrefix="settings"><SettingsFoldersSection /></TabPanel> : null}

      {selected === "commands" ? <TabPanel id="commands" idPrefix="settings"><SettingsCommandsSection isAdmin={isAdmin} /></TabPanel> : null}

      {selected === "assistant" ? <TabPanel id="assistant" idPrefix="settings">
        <BackgroundSettings />
        {onOpenBackgroundWork ? <p className="vault-section-note vault-settings-link">
          Active and past runs, with Stop for anything still working, are in{" "}
          <button className="vault-link-button" onClick={onOpenBackgroundWork} type="button">Background work</button>.
        </p> : null}
      </TabPanel> : null}
    </section>
  );
}

function AppearancePicker() {
  const [theme, setCurrent] = useState<VaultTheme>(storedTheme);
  const options: { key: VaultTheme; name: string; detail: string }[] = [
    { key: "midnight", name: "Midnight", detail: "Dark navy with cyan light." },
    { key: "aurora", name: "Aurora", detail: "Light glass with pink and lilac." },
  ];
  return <div className="browser-voice-theme-picker" role="radiogroup" aria-label="Appearance">
    {options.map(option => <button key={option.key} type="button" role="radio" aria-checked={theme === option.key}
      className="browser-voice-theme-option" onClick={() => { setTheme(option.key); setCurrent(option.key); }}>
      <span className={`browser-voice-theme-swatch is-${option.key}`} aria-hidden="true"><i /><i /><i /></span>
      <strong>{option.name}</strong><small>{option.detail}</small>
    </button>)}
  </div>;
}

function LiveWindowSwitches() {
  const [shown, setShown] = useState({ chat: livePanelShown("chat"), voice: livePanelShown("voice") });
  const rows: { surface: LiveSurface; name: string; detail: string }[] = [
    { surface: "voice", name: "Voice", detail: "Live window on the Voice screen." },
    { surface: "chat", name: "Chat", detail: "Live window under the Chat conversation." },
  ];
  return <div className="browser-voice-agent-list browser-voice-live-window-settings">
    {rows.map(row => {
      const on = shown[row.surface];
      return <article key={row.surface} className={`browser-voice-agent-row is-${on ? "on" : "off"}`}>
        <span className="browser-voice-agent-row-main">
          <span className="browser-voice-agent-mark">{row.surface === "voice" ? <BrowserVoiceMicrophoneIcon /> : <ChatIcon />}</span>
          <span><strong>{row.name}</strong><small>{row.detail}</small><small>{on ? "Shown" : "Hidden"}</small></span>
        </span>
        <button aria-label={`${on ? "Hide" : "Show"} the ${row.name} live window`} aria-pressed={on}
          className="browser-voice-agent-switch" onClick={() => { setLivePanelShown(row.surface, !on); setShown(current => ({ ...current, [row.surface]: !on })); }}
          role="switch" type="button"><span /></button>
      </article>;
    })}
  </div>;
}
