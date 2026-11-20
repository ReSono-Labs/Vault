import { useEffect, useState } from "react";
import { localApi, type UserFolder } from "@/browser-voice/localApi";
import { AddFolderFlow } from "@/browser-voice/folders/AddFolderFlow";
import { FolderDialog, errorText } from "@/browser-voice/folders/FolderDialog";
import {
  completePluginImportWithoutLocalShare,
  completePluginImportWithLocalShare,
  type PendingPluginImport,
} from "@/browser-voice/pluginPackageFlow";

/** Plugin import: choose one of your folders for a plugin that asks for one. */
export function PluginLocalShareImportDialog({
  pending,
  onClose,
  onComplete,
}: {
  pending: PendingPluginImport;
  onClose: () => void;
  onComplete: (result: { identity: string; message: string }) => void;
}) {
  const [folders, setFolders] = useState<UserFolder[] | null>(null);
  const [hasAccess, setHasAccess] = useState(false);
  const [anywhere, setAnywhere] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [addedId, setAddedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const needsEdit = pending.share.permission === "write";

  useEffect(() => {
    localApi
      .folders()
      .then((value) => {
        setFolders(value.folders);
        setHasAccess(value.hasAccess);
        setAnywhere(value.canAddAnywhere);
      })
      .catch((caught) => setError(errorText(caught, "Your folders could not be loaded.")));
  }, []);

  async function finish(withFolder: boolean) {
    setWorking(true);
    setError(null);
    try {
      const result = withFolder && selected
        ? await completePluginImportWithLocalShare(pending, {
            folderId: selected,
            createdDuringImport: selected === addedId,
          })
        : await completePluginImportWithoutLocalShare(pending);
      onComplete(result);
      onClose();
    } catch (caught) {
      setError(errorText(caught, "Plugin import failed."));
      if (addedId) {
        // The server already removed a folder added during a failed import.
        setFolders((current) => current?.filter((folder) => folder.folderId !== addedId) ?? null);
        setSelected(null);
        setAddedId(null);
      }
    } finally {
      setWorking(false);
    }
  }

  if (adding) {
    return (
      <AddFolderFlow
        anywhere={anywhere}
        onAdded={(folder) => {
          setAdding(false);
          setFolders((current) => [...(current ?? []), folder]);
          setSelected(folder.folderId);
          setAddedId(folder.folderId);
        }}
        onClose={() => setAdding(false)}
      />
    );
  }

  const usable = (folders ?? []).filter((folder) => folder.status === "ok");

  return (
    <FolderDialog eyebrow="Plugin import" onClose={onClose} title="Choose a folder for this plugin" titleId="plugin-local-share-title">
      <p className="browser-voice-share-folder-path">
        <strong>{pending.preview.identity}</strong>
        <small>{pending.share.label}</small>
        {needsEdit ? <small>This plugin needs a folder set to “Can view and edit”.</small> : null}
      </p>
      {folders && usable.length === 0 ? (
        <p className="browser-voice-form-note">
          {hasAccess ? "You haven't added any folders yet." : "Your admin hasn't shared any folders with you yet."}
        </p>
      ) : null}
      <div className="browser-voice-agent-list" role="radiogroup" aria-label="Your folders">
        {usable.map((folder) => {
          const blocked = needsEdit && folder.permission !== "write";
          return (
            <button
              aria-checked={selected === folder.folderId}
              className={`browser-voice-agent-row ${selected === folder.folderId ? "is-on" : "is-off"}`}
              disabled={working || blocked}
              key={folder.folderId}
              onClick={() => setSelected(folder.folderId)}
              role="radio"
              title={blocked ? "This folder is set to Can view." : undefined}
              type="button"
            >
              <span>
                <strong>{folder.name}</strong>
                <small>
                  {folder.location} · {folder.permission === "write" ? "Can view and edit" : "Can view"}
                </small>
              </span>
            </button>
          );
        })}
      </div>
      {error ? <p className="browser-voice-modal-error" role="alert">{error}</p> : null}
      <div className="browser-voice-modal-actions">
        {!pending.share.required ? (
          <button
            className="browser-voice-pill browser-voice-pill-muted"
            disabled={working}
            onClick={() => void finish(false)}
            type="button"
          >
            Import without a folder
          </button>
        ) : null}
        <button className="browser-voice-pill" disabled={working} onClick={onClose} type="button">
          Cancel
        </button>
        {hasAccess ? (
          <button className="browser-voice-pill" disabled={working} onClick={() => setAdding(true)} type="button">
            Add folder
          </button>
        ) : null}
        <button
          className="browser-voice-submit"
          disabled={working || !selected}
          onClick={() => void finish(true)}
          type="button"
        >
          {working ? "Importing…" : "Finish import"}
        </button>
      </div>
    </FolderDialog>
  );
}
