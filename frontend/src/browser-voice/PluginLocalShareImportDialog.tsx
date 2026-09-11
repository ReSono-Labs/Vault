import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  completePluginImportWithoutLocalShare,
  completePluginImportWithLocalShare,
  type PendingPluginImport,
} from "@/browser-voice/pluginPackageFlow";
import {
  pickPluginLocalShareFolder,
  pluginLocalShareSupported,
  type PluginLocalSharePick,
} from "@/browser-voice/pluginLocalShareImport";

export function PluginLocalShareImportDialog({
  pending,
  onClose,
  onComplete,
}: {
  pending: PendingPluginImport;
  onClose: () => void;
  onComplete: (result: { identity: string; message: string }) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const [pickedFolder, setPickedFolder] = useState<PluginLocalSharePick | null>(null);
  const [permission, setPermission] = useState<"read" | "write">(
    pending.share.permission === "write" ? "write" : "read",
  );
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    return () => {
      if (dialog.open) {
        dialog.close();
      }
    };
  }, []);

  function closeDialog() {
    const dialog = dialogRef.current;
    if (dialog?.open) {
      dialog.close();
      return;
    }
    onClose();
  }

  async function chooseFolder() {
    if (!pluginLocalShareSupported()) {
      setError("Your browser cannot link folders. Use Chrome or Edge on this computer.");
      return;
    }
    setError(null);
    try {
      const picked = await pickPluginLocalShareFolder();
      setPickedFolder(picked);
    } catch (caught) {
      if (caught instanceof Error && caught.name === "AbortError") {
        return;
      }
      setError(caught instanceof Error ? caught.message : "Folder picker failed.");
    }
  }

  async function finishImport() {
    if (!pickedFolder) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      const result = await completePluginImportWithLocalShare(pending, pickedFolder, permission);
      closeDialog();
      onComplete(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Plugin import failed.");
    } finally {
      setWorking(false);
    }
  }

  async function importWithoutFolder() {
    setWorking(true);
    setError(null);
    try {
      const result = await completePluginImportWithoutLocalShare(pending);
      closeDialog();
      onComplete(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Plugin import failed.");
    } finally {
      setWorking(false);
    }
  }

  return createPortal(
    <dialog
      aria-labelledby="plugin-local-share-title"
      className="browser-voice-modal browser-voice-share-modal"
      onCancel={(event) => {
        event.preventDefault();
        closeDialog();
      }}
      onClose={onClose}
      ref={dialogRef}
    >
      <div className="browser-voice-share-dialog-body">
        <div className="browser-voice-modal-head">
          <div>
            <span className="browser-voice-eyebrow-label">Plugin import</span>
            <h2 id="plugin-local-share-title">Link a folder from this computer</h2>
            <p className="browser-voice-share-folder-path">
              <strong>{pending.preview.identity}</strong>
              <small>{pending.share.label}</small>
              <small>
                Vault path: <code>local/{pending.share.mountName}</code>
              </small>
            </p>
          </div>
          <button
            aria-label="Close folder link dialog"
            className="browser-voice-modal-close"
            onClick={closeDialog}
            type="button"
          >
            ×
          </button>
        </div>

        {!pickedFolder ? (
          <p className="browser-voice-form-note">
            Choose a folder on this computer. Vault will not copy files into Docker.
          </p>
        ) : (
          <>
            <p className="browser-voice-share-message" role="status">
              Selected folder: <strong>{pickedFolder.label}</strong>
            </p>
            <div className="browser-voice-share-access">
              <span>Folder access</span>
              <div className="browser-voice-share-access-options" role="group" aria-label="Folder access">
                <button
                  className={permission === "read" ? "is-active" : ""}
                  disabled={working}
                  onClick={() => setPermission("read")}
                  type="button"
                >
                  Read only
                </button>
                <button
                  className={permission === "write" ? "is-active" : ""}
                  disabled={working}
                  onClick={() => setPermission("write")}
                  type="button"
                >
                  Read &amp; write
                </button>
              </div>
            </div>
          </>
        )}

        {error ? <p className="browser-voice-modal-error" role="alert">{error}</p> : null}

        <div className="browser-voice-modal-actions">
          {!pickedFolder ? (
            <>
              {!pending.share.required ? (
                <button
                  className="browser-voice-pill browser-voice-pill-muted"
                  disabled={working}
                  onClick={() => void importWithoutFolder()}
                  type="button"
                >
                  Import without folder
                </button>
              ) : null}
              <button className="browser-voice-pill" disabled={working} onClick={closeDialog} type="button">
                Cancel
              </button>
              <button
                className="browser-voice-submit"
                disabled={working}
                onClick={() => void chooseFolder()}
                type="button"
              >
                Choose folder…
              </button>
            </>
          ) : (
            <>
              <button
                className="browser-voice-pill browser-voice-pill-muted"
                disabled={working}
                onClick={() => setPickedFolder(null)}
                type="button"
              >
                Choose a different folder
              </button>
              <button className="browser-voice-pill" disabled={working} onClick={closeDialog} type="button">
                Cancel
              </button>
              <button
                className="browser-voice-submit"
                disabled={working}
                onClick={() => void finishImport()}
                type="button"
              >
                {working ? "Importing…" : "Finish import"}
              </button>
            </>
          )}
        </div>
      </div>
    </dialog>,
    document.body,
  );
}
