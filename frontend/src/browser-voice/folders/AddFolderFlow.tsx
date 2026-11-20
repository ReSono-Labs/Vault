import { useState } from "react";
import { localApi, type FolderPermission, type UserFolder } from "@/browser-voice/localApi";
import { FolderDialog, HiddenFilesOption, PermissionToggle, errorText } from "@/browser-voice/folders/FolderDialog";
import { FolderPicker, type PickedFolder } from "@/browser-voice/folders/FolderPicker";

type Choice = PickedFolder & { create: string | null };

function defaultName(choice: Choice): string {
  if (choice.create) return choice.create;
  const last = choice.label.split(" / ").at(-1) ?? "";
  return last.replace(/[^A-Za-z0-9 ._-]+/g, "-").replace(/^[-. ]+|[-. ]+$/g, "").slice(0, 64) || "Folder";
}

/**
 * Add folder: pick (or make) a folder inside what the admin shared, confirm its name and
 * what agents can do, then Add.
 */
export function AddFolderFlow({
  onAdded,
  onClose,
  anywhere = false,
}: {
  onAdded: (folder: UserFolder) => void;
  onClose: () => void;
  /** Master account: browse everything Vault can see instead of the folders shared with you. */
  anywhere?: boolean;
}) {
  const [choice, setChoice] = useState<Choice | null>(null);
  const [name, setName] = useState("");
  const [permission, setPermission] = useState<FolderPermission>("read");
  const [includeHidden, setIncludeHidden] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function confirm(next: Choice) {
    setChoice(next);
    setName(defaultName(next));
    setPermission(next.canWrite && next.create ? "write" : "read");
    setIncludeHidden(false);
    setError(null);
  }

  if (!choice) {
    return (
      <FolderPicker
        allowCreate
        onChoose={(picked) => confirm({ ...picked, create: null })}
        onClose={onClose}
        onCreate={(request) => confirm({ ...request, create: request.name })}
        source={anywhere ? "admin" : "user"}
        title="Add a folder"
      />
    );
  }

  async function add() {
    if (!choice) return;
    setWorking(true);
    setError(null);
    try {
      const value = {
        path: choice.path,
        name: name.trim(),
        permission,
        ...(choice.create ? { create: true, newFolderName: choice.create } : {}),
        ...(includeHidden ? { includeHidden: true } : {}),
      };
      const folder = anywhere
        ? await localApi.adminAddFolder({ locationId: choice.scopeId, ...value })
        : await localApi.addFolder({ grantId: choice.scopeId, ...value });
      onAdded(folder);
    } catch (caught) {
      setError(errorText(caught, "The folder could not be added."));
    } finally {
      setWorking(false);
    }
  }

  return (
    <FolderDialog eyebrow="Folders" onClose={onClose} title="Add a folder" titleId="add-folder-title">
      <form
        className="browser-voice-folder-confirm-form"
        onSubmit={(event) => {
          event.preventDefault();
          void add();
        }}
      >
        <p className="browser-voice-share-folder-path">
          <strong>{choice.create ? `New folder in ${choice.label}` : choice.label}</strong>
        </p>
        <label className="browser-voice-modal-wide">
          <span>Name</span>
          <input maxLength={64} onChange={(event) => setName(event.target.value)} required value={name} />
        </label>
        <PermissionToggle canEdit={choice.canWrite} onChange={setPermission} value={permission} />
        {anywhere || choice.create ? <HiddenFilesOption checked={includeHidden} onChange={setIncludeHidden} /> : null}
        {error ? <p className="browser-voice-modal-error" role="alert">{error}</p> : null}
        <div className="browser-voice-modal-actions">
          <button className="browser-voice-pill" disabled={working} onClick={() => setChoice(null)} type="button">
            Back
          </button>
          <button className="browser-voice-submit" disabled={working || !name.trim()} type="submit">
            {working ? "Adding…" : "Add"}
          </button>
        </div>
      </form>
    </FolderDialog>
  );
}
