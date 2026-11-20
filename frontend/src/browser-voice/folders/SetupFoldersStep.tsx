import { useEffect, useState } from "react";
import { localApi, type FolderPermission } from "@/browser-voice/localApi";
import { PermissionToggle, errorText } from "@/browser-voice/folders/FolderDialog";
import { FolderPicker, type PickedFolder } from "@/browser-voice/folders/FolderPicker";

type Pick = PickedFolder & { permission: FolderPermission };

/** First-run step for the master account: a ReSono Vault folder in Documents, plus any other folders. */
export function SetupFoldersStep({ onDone }: { onDone: () => void }) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [vaultFolder, setVaultFolder] = useState(true);
  const [picks, setPicks] = useState<Pick[]>([]);
  const [picking, setPicking] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    localApi
      .folderLocations()
      .then((value) => setAvailable(value.available && value.locations.some((item) => item.status === "ok")))
      .catch(() => setAvailable(false));
  }, []);

  async function finish() {
    setWorking(true);
    setError(null);
    try {
      if (vaultFolder) await localApi.setupVaultFolder();
      for (const pick of picks) {
        await localApi.setupAddFolder({ locationId: pick.scopeId, path: pick.path, permission: pick.permission });
      }
      onDone();
    } catch (caught) {
      setError(errorText(caught, "Folders could not be set up. You can add them later in Settings."));
    } finally {
      setWorking(false);
    }
  }

  if (available === null) return <p className="browser-voice-form-note">Checking folders on this computer…</p>;

  if (!available) {
    return (
      <div className="browser-voice-onboarding-choice">
        <p>Folders aren't set up on this computer, so your agents will use Vault's own storage. You can continue.</p>
        <div className="browser-voice-onboarding-actions">
          <button className="browser-voice-submit" onClick={onDone} type="button">
            Continue
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="browser-voice-onboarding-choice browser-voice-setup-folders">
      <p>Choose folders on this computer that your agents can use. You can change this any time in Settings.</p>
      <label className="browser-voice-setup-folder-option">
        <input checked={vaultFolder} onChange={(event) => setVaultFolder(event.target.checked)} type="checkbox" />
        <span>
          <strong>Create my ReSono Vault folder in Documents</strong>
          <small>A folder your agents can read and write.</small>
        </span>
      </label>
      {picks.map((pick, index) => (
        <div className="browser-voice-setup-folder-pick" key={`${pick.scopeId}:${pick.path}`}>
          <strong>{pick.label}</strong>
          <PermissionToggle
            onChange={(permission) =>
              setPicks((current) => current.map((item, position) => (position === index ? { ...item, permission } : item)))
            }
            value={pick.permission}
          />
          <button
            className="browser-voice-pill browser-voice-pill-muted"
            onClick={() => setPicks((current) => current.filter((_item, position) => position !== index))}
            type="button"
          >
            Remove
          </button>
        </div>
      ))}
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
      <div className="browser-voice-onboarding-actions">
        <button className="browser-voice-pill" disabled={working} onClick={() => setPicking(true)} type="button">
          Add other folders
        </button>
        <button className="browser-voice-pill browser-voice-pill-muted" disabled={working} onClick={onDone} type="button">
          Skip for now
        </button>
        <button className="browser-voice-submit" disabled={working} onClick={() => void finish()} type="button">
          {working ? "Setting up…" : "Continue"}
        </button>
      </div>
      {picking ? (
        <FolderPicker
          onChoose={(picked) => {
            setPicking(false);
            setPicks((current) =>
              current.some((item) => item.scopeId === picked.scopeId && item.path === picked.path)
                ? current
                : [...current, { ...picked, permission: "read" }],
            );
          }}
          onClose={() => setPicking(false)}
          source="admin"
          title="Add a folder for your agents"
        />
      ) : null}
    </div>
  );
}
