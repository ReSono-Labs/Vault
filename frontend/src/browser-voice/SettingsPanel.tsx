import { setTheme, storedTheme, type VaultTheme } from "@/browser-voice/theme";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  computerFoldersSupported,
  pickComputerFolder,
  removeComputerFolderHandle,
} from "@/browser-voice/computerFolders";
import { localApi, type HostFilesystemMount, type HostFilesystemSettings, type LocalUser } from "@/browser-voice/localApi";
import { BrowserVoiceWorkspaceIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";

type PendingPick = {
  mountId: string;
  suggestedName: string;
  label: string;
};

export function SettingsPanel({ user }: { user: LocalUser }) {
  const [settings, setSettings] = useState<HostFilesystemSettings | null>(null);
  const [mounts, setMounts] = useState<HostFilesystemMount[]>([]);
  const [pendingPick, setPendingPick] = useState<PendingPick | null>(null);
  const [addingFolder, setAddingFolder] = useState(false);
  const [mountName, setMountName] = useState("");
  const [permission, setPermission] = useState<"read" | "write">("read");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [passwordPromptOpen, setPasswordPromptOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const passwordDialogRef = useRef<HTMLDialogElement | null>(null);

  async function refresh() {
    const [nextSettings, nextMounts] = await Promise.all([
      localApi.hostFilesystemSettings(),
      localApi.hostFilesystemMounts(),
    ]);
    setSettings(nextSettings);
    setMounts(nextMounts.items);
  }

  useEffect(() => {
    void refresh().catch((caught) => {
      setError(caught instanceof Error ? caught.message : "Settings could not be loaded.");
    });
  }, []);

  useEffect(() => {
    const dialog = passwordDialogRef.current;
    if (!dialog) {
      return;
    }
    if (passwordPromptOpen && !dialog.open) {
      dialog.showModal();
    }
    if (!passwordPromptOpen && dialog.open) {
      dialog.close();
    }
  }, [passwordPromptOpen]);

  async function saveEnabled(enabled: boolean, password?: string) {
    setWorking(true);
    setError(null);
    try {
      const next = await localApi.saveHostFilesystemSettings({
        enabled,
        currentPassword: password,
      });
      setSettings(next);
      setMessage(enabled ? "Computer folders are on." : "Computer folders are off.");
      if (!enabled) {
        setPendingPick(null);
        setAddingFolder(false);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Computer folders could not be updated.");
      throw caught;
    } finally {
      setWorking(false);
    }
  }

  function requestEnable() {
    if (settings?.enabled) {
      void saveEnabled(false);
      return;
    }
    if (user.passwordMode === "master_managed") {
      setError("Computer folders require a user-managed password on this account.");
      return;
    }
    setCurrentPassword("");
    setPasswordPromptOpen(true);
  }

  async function confirmEnable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorking(true);
    setError(null);
    try {
      await saveEnabled(true, currentPassword);
      setPasswordPromptOpen(false);
      setCurrentPassword("");
    } catch {
      // Error already shown.
    } finally {
      setWorking(false);
    }
  }

  async function pickFolder() {
    setWorking(true);
    setError(null);
    try {
      const picked = await pickComputerFolder(permission);
      setPendingPick(picked);
      setMountName(picked.suggestedName);
    } catch (caught) {
      if (caught instanceof Error && caught.name === "AbortError") {
        return;
      }
      setError(caught instanceof Error ? caught.message : "Folder picker failed.");
    } finally {
      setWorking(false);
    }
  }

  function startAddingFolder() {
    setError(null);
    setAddingFolder(true);
    setPendingPick(null);
    setMountName("");
    setPermission("read");
  }

  function cancelAddingFolder() {
    setAddingFolder(false);
    setPendingPick(null);
    setMountName("");
  }

  async function registerFolder() {
    if (!pendingPick || !mountName.trim()) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      await localApi.registerHostFilesystemMount({
        mountId: pendingPick.mountId,
        mountName: mountName.trim(),
        permission,
        source: "browser",
      });
      setPendingPick(null);
      setMountName("");
      setAddingFolder(false);
      setMessage("Linked folder added.");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Linked folder could not be saved.");
    } finally {
      setWorking(false);
    }
  }

  async function revokeMount(mount: HostFilesystemMount) {
    setWorking(true);
    setError(null);
    try {
      await localApi.revokeHostFilesystemMount(mount.mountId);
      await removeComputerFolderHandle(mount.mountId);
      setMessage("Linked folder removed.");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Linked folder could not be removed.");
    } finally {
      setWorking(false);
    }
  }

  const enabled = settings?.enabled ?? false;

  return (
    <section className="browser-voice-agents" aria-labelledby="browser-voice-settings-title">
      <header className="browser-voice-management-heading">
        <div>
          <span className="browser-voice-eyebrow-label">Vault</span>
          <h2 id="browser-voice-settings-title">Settings</h2>
          <p>Manage optional features for this Vault and this browser.</p>
        </div>
      </header>

      <div className="browser-voice-section-head">
        <div>
          <h3>Appearance</h3>
          <p>Choose how Vault looks in this browser.</p>
        </div>
      </div>
      <AppearancePicker />

      <div className="browser-voice-section-head">
        <div>
          <h3>Computer folders</h3>
          <p>
            Link folders from this computer as <code>local/...</code>. Files in this browser can
            open them. Voice can browse and read them while this Vault tab is open.
          </p>
        </div>
      </div>

      <div className="browser-voice-agent-list">
        <article className={`browser-voice-agent-row is-${enabled ? "on" : "off"}`}>
          <span className="browser-voice-agent-row-main">
            <span className="browser-voice-agent-mark">
              <BrowserVoiceWorkspaceIcon />
            </span>
            <span>
              <strong>Computer folders</strong>
              <small>Files and Voice (this tab) can browse linked folders under local/.</small>
              <small>{enabled ? "On" : "Off"} · This browser</small>
            </span>
          </span>
          <button
            aria-label={`Turn computer folders ${enabled ? "off" : "on"}`}
            aria-pressed={enabled}
            className="browser-voice-agent-switch"
            disabled={working}
            onClick={() => requestEnable()}
            role="switch"
            type="button"
          >
            <span />
          </button>
        </article>
      </div>

      {enabled ? (
        <section className="browser-voice-management-section">
          {!computerFoldersSupported() ? (
            <p className="browser-voice-management-empty">
              Folder linking needs a browser with folder picker support, such as Chrome or Edge.
            </p>
          ) : (
            <>
              <div className="browser-voice-section-head browser-voice-settings-linked-head">
                <h4>Linked folders</h4>
                <button
                  className="browser-voice-submit"
                  disabled={working || addingFolder}
                  onClick={() => startAddingFolder()}
                  type="button"
                >
                  Add folder
                </button>
              </div>

              {mounts.length ? (
                <div className="browser-voice-agent-list browser-voice-settings-folder-list">
                  {mounts.map((mount) => (
                    <article className="browser-voice-agent-row is-on" key={mount.mountId}>
                      <span className="browser-voice-agent-row-main">
                        <span className="browser-voice-agent-mark">
                          <BrowserVoiceWorkspaceIcon />
                        </span>
                        <span>
                          <strong>{mount.mountName}</strong>
                          <small>
                            {mount.mountPath} · {mount.permission === "write" ? "Read & write" : "Read only"}
                          </small>
                        </span>
                      </span>
                      <button
                        className="browser-voice-pill browser-voice-pill-muted"
                        disabled={working}
                        onClick={() => void revokeMount(mount)}
                        type="button"
                      >
                        Remove
                      </button>
                    </article>
                  ))}
                </div>
              ) : null}

              {addingFolder ? (
                <div className="browser-voice-settings-add-folder">
                  <div className="browser-voice-share-access">
                    <span>Access for new folder</span>
                    <div className="browser-voice-share-access-options" role="group" aria-label="Folder access">
                      <button
                        aria-pressed={permission === "read"}
                        className={permission === "read" ? "is-active" : ""}
                        disabled={working || Boolean(pendingPick)}
                        onClick={() => setPermission("read")}
                        type="button"
                      >
                        Read only
                      </button>
                      <button
                        aria-pressed={permission === "write"}
                        className={permission === "write" ? "is-active" : ""}
                        disabled={working || Boolean(pendingPick)}
                        onClick={() => setPermission("write")}
                        type="button"
                      >
                        Read &amp; write
                      </button>
                    </div>
                  </div>

                  {pendingPick ? (
                    <form
                      className="browser-voice-connection-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void registerFolder();
                      }}
                    >
                      <p>
                        <strong>{pendingPick.label}</strong>
                      </p>
                      <div className="browser-voice-connection-form-grid">
                        <label>
                          <span>Name in Vault</span>
                          <input onChange={(event) => setMountName(event.target.value)} value={mountName} />
                        </label>
                      </div>
                      <div className="browser-voice-modal-actions">
                        <button
                          className="browser-voice-pill browser-voice-pill-muted"
                          disabled={working}
                          onClick={() => cancelAddingFolder()}
                          type="button"
                        >
                          Cancel
                        </button>
                        <button disabled={working || !mountName.trim()} type="submit">
                          Save linked folder
                        </button>
                      </div>
                    </form>
                  ) : (
                    <div className="browser-voice-settings-add-folder-actions">
                      <button
                        className="browser-voice-pill browser-voice-pill-muted"
                        disabled={working}
                        onClick={() => cancelAddingFolder()}
                        type="button"
                      >
                        Cancel
                      </button>
                      <button
                        className="browser-voice-submit"
                        disabled={working}
                        onClick={() => void pickFolder()}
                        type="button"
                      >
                        Choose folder
                      </button>
                    </div>
                  )}
                </div>
              ) : null}

              {!mounts.length && !addingFolder ? (
                <p className="browser-voice-management-empty">Add a folder to see it under local/ in your workspace.</p>
              ) : null}
            </>
          )}
        </section>
      ) : null}

      {message ? <p className="browser-voice-management-message" role="status">{message}</p> : null}
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}

      <dialog
        aria-labelledby="computer-folders-password-title"
        className="browser-voice-modal"
        onCancel={() => setPasswordPromptOpen(false)}
        onClose={() => setPasswordPromptOpen(false)}
        ref={passwordDialogRef}
      >
        <form onSubmit={(event) => void confirmEnable(event)}>
          <div className="browser-voice-modal-head">
            <div>
              <span className="browser-voice-eyebrow-label">Computer folders</span>
              <h2 id="computer-folders-password-title">Confirm your password</h2>
            </div>
            <button
              aria-label="Close password dialog"
              className="browser-voice-modal-close"
              onClick={() => setPasswordPromptOpen(false)}
              type="button"
            >
              ×
            </button>
          </div>
          <p className="browser-voice-form-note">
            Vault needs your current password before this browser can access folders on your computer.
          </p>
          <div className="browser-voice-modal-fields">
            <label className="browser-voice-modal-wide">
              <span>Current password</span>
              <input
                autoComplete="current-password"
                autoFocus
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
                type="password"
                value={currentPassword}
              />
            </label>
          </div>
          <div className="browser-voice-modal-actions">
            <button className="browser-voice-pill" onClick={() => setPasswordPromptOpen(false)} type="button">
              Cancel
            </button>
            <button className="browser-voice-submit" disabled={working} type="submit">
              {working ? "Turning on…" : "Turn on"}
            </button>
          </div>
        </form>
      </dialog>
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
