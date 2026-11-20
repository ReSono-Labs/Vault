import { useEffect, useState } from "react";
import { localApi, type FolderList as FolderListResponse } from "@/browser-voice/localApi";
import { AddFolderFlow } from "@/browser-voice/folders/AddFolderFlow";
import { errorText } from "@/browser-voice/folders/FolderDialog";
import { FolderList, type FolderRow } from "@/browser-voice/folders/FolderList";

/** Settings > Folders: the folders this person's agents can use. */
export function SettingsFoldersSection() {
  const [state, setState] = useState<FolderListResponse | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setState(await localApi.folders());
  }

  useEffect(() => {
    refresh().catch((caught) => setError(errorText(caught, "Folders could not be loaded.")));
  }, []);

  async function run(action: () => Promise<unknown>, done: string, failed: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(done);
      await refresh();
    } catch (caught) {
      setError(errorText(caught, failed));
    } finally {
      setBusy(false);
    }
  }

  if (state && !state.available) return null;

  const rows: FolderRow[] = (state?.folders ?? []).map((folder) => ({
    id: folder.folderId,
    name: folder.name,
    detail: folder.location,
    permission: folder.permission,
    maxPermission: folder.maxPermission,
    status: folder.status,
    statusMessage: folder.statusMessage,
    includeHidden: folder.includeHidden,
    hiddenLockedReason: folder.hiddenFromAccess
      ? "The master account shows hidden files for everything in this folder's access."
      : folder.canChangeHidden
        ? null
        : "Only the master account can change this for a folder you didn't make in Vault.",
  }));

  return (
    <>
      <div className="browser-voice-section-head browser-voice-settings-linked-head">
        <div>
          <h3>Folders</h3>
          <p>Folders on this computer that your agents can use. They appear in Files under local/.</p>
        </div>
        <button
          className="browser-voice-submit"
          disabled={busy || !state?.hasAccess}
          onClick={() => setAdding(true)}
          type="button"
        >
          Add folder
        </button>
      </div>
      {state && !state.hasAccess ? (
        <p className="browser-voice-management-empty">
          Your admin hasn't shared any folders with you yet. Ask them to give you access in People and access.
        </p>
      ) : null}
      {state?.hasAccess && rows.length === 0 ? (
        <p className="browser-voice-management-empty">No folders yet. Click Add folder to choose one.</p>
      ) : null}
      {rows.length ? (
        <FolderList
          busy={busy}
          onPermission={(row, permission) =>
            void run(
              () => localApi.setFolderPermission(row.id, permission),
              permission === "write" ? `Agents can now view and edit ${row.name}.` : `Agents can now only view ${row.name}.`,
              "The folder could not be changed.",
            )
          }
          onHidden={(row, includeHidden) =>
            void run(
              () => localApi.setFolderHidden(row.id, includeHidden),
              includeHidden ? `Hidden files are now shown in ${row.name}.` : `Hidden files are now hidden in ${row.name}.`,
              "The folder could not be changed.",
            )
          }
          onRemove={(row) =>
            void run(
              () => localApi.removeFolder(row.id),
              `${row.name} was removed. The files are still on your computer.`,
              "The folder could not be removed.",
            )
          }
          removeQuestion={(row) =>
            `Remove ${row.name}? Your agents won't be able to use it anymore. The files stay on your computer.`
          }
          rows={rows}
        />
      ) : null}
      {message ? <p className="browser-voice-management-message" role="status">{message}</p> : null}
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
      {adding ? (
        <AddFolderFlow
          anywhere={Boolean(state?.canAddAnywhere)}
          onAdded={(folder) => {
            setAdding(false);
            setMessage(`${folder.name} was added. Your agents can use it at ${folder.path}.`);
            void refresh();
          }}
          onClose={() => setAdding(false)}
        />
      ) : null}
    </>
  );
}
