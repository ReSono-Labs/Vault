import { useEffect, useState } from "react";
import { localApi, type FolderAccess, type FolderPermission } from "@/browser-voice/localApi";
import { FolderDialog, HiddenFilesOption, PermissionToggle, errorText } from "@/browser-voice/folders/FolderDialog";
import { FolderList } from "@/browser-voice/folders/FolderList";
import { FolderPicker, type PickedFolder } from "@/browser-voice/folders/FolderPicker";

/** Admin: which folders on this computer one person may use. They add folders from inside these. */
export function AdminFolderAccess({ userId, displayName }: { userId: string; displayName: string }) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [items, setItems] = useState<FolderAccess[]>([]);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<PickedFolder | null>(null);
  const [permission, setPermission] = useState<FolderPermission>("read");
  const [includeHidden, setIncludeHidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setItems((await localApi.folderAccess(userId)).items);
  }

  useEffect(() => {
    setMessage(null);
    setError(null);
    localApi
      .folderLocations()
      .then((value) => {
        setAvailable(value.available);
        return value.available ? refresh() : undefined;
      })
      .catch((caught) => setError(errorText(caught, "Folder access could not be loaded.")));
  }, [userId]);

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

  if (available === false) return null;

  return (
    <section className="browser-voice-folder-access" aria-label={`Folders for ${displayName}`}>
      <div className="browser-voice-section-head">
        <div>
          <h4>Folders</h4>
          <p>Folders {displayName} can use. They can add folders from inside these, but nothing above them.</p>
        </div>
        <button className="browser-voice-submit" disabled={busy} onClick={() => setPicking(true)} type="button">
          Give access
        </button>
      </div>
      {items.length ? (
        <FolderList
          busy={busy}
          onPermission={(row, next) =>
            void run(
              () => localApi.setFolderAccessPermission(row.id, next),
              next === "write" ? `${displayName} can now view and edit ${row.name}.` : `${displayName} can now only view ${row.name}.`,
              "Access could not be changed.",
            )
          }
          onHidden={(row, next) =>
            void run(
              () => localApi.setFolderAccessHidden(row.id, next),
              next ? `Hidden files are now shown in ${row.name} for ${displayName}.` : `Hidden files are now hidden in ${row.name} for ${displayName}.`,
              "Access could not be changed.",
            )
          }
          onRemove={(row) =>
            void run(
              () => localApi.removeFolderAccess(row.id),
              `${displayName} no longer has access to ${row.name}. The files are still on the computer.`,
              "Access could not be removed.",
            )
          }
          removeQuestion={(row) =>
            `Remove ${row.name} for ${displayName}? Their agents lose access to it and to any folders they added inside it. The files stay on the computer.`
          }
          rows={items.map((item) => ({
            id: item.grantId,
            name: item.label,
            detail: item.folderCount === 1 ? "1 folder added" : `${item.folderCount} folders added`,
            permission: item.maxPermission,
            maxPermission: "write",
            status: item.status,
            statusMessage: item.statusMessage,
            includeHidden: item.includeHidden,
          }))}
        />
      ) : (
        <p className="browser-voice-management-empty">{displayName} doesn't have access to any folders yet.</p>
      )}
      {message ? <p className="browser-voice-management-message" role="status">{message}</p> : null}
      {error ? <div className="browser-voice-management-error" role="alert">{error}</div> : null}
      {picking ? (
        <FolderPicker
          onChoose={(value) => {
            setPicking(false);
            setPicked(value);
            setPermission("read");
            setIncludeHidden(false);
          }}
          onClose={() => setPicking(false)}
          source="admin"
          title={`Give ${displayName} access to a folder`}
        />
      ) : null}
      {picked ? (
        <FolderDialog
          eyebrow="Folders"
          onClose={() => setPicked(null)}
          title={`Give ${displayName} access`}
          titleId="give-folder-access-title"
        >
          <p className="browser-voice-share-folder-path">
            <strong>{picked.label}</strong>
          </p>
          <PermissionToggle label={`What can ${displayName}'s agents do?`} onChange={setPermission} value={permission} />
          <HiddenFilesOption checked={includeHidden} onChange={setIncludeHidden} />
          <div className="browser-voice-modal-actions">
            <button className="browser-voice-pill" onClick={() => setPicked(null)} type="button">
              Cancel
            </button>
            <button
              className="browser-voice-submit"
              disabled={busy}
              onClick={() => {
                const target = picked;
                setPicked(null);
                void run(
                  () =>
                    localApi.giveFolderAccess(userId, {
                      locationId: target.scopeId,
                      path: target.path,
                      maxPermission: permission,
                      includeHidden,
                    }),
                  `${displayName} can now use ${target.label}.`,
                  "Access could not be given.",
                );
              }}
              type="button"
            >
              Give access
            </button>
          </div>
        </FolderDialog>
      ) : null}
    </section>
  );
}
