import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { localApi, type ManagedLocalUser } from "@/browser-voice/localApi";

function itemTitle(folderPath: string, shareKind: "file" | "folder"): string {
  if (!folderPath) {
    return "Workspace root";
  }
  const segments = folderPath.split("/").filter(Boolean);
  return segments.at(-1) ?? folderPath;
}

export function WorkspaceShareDialog({
  folderPath,
  shareKind = "folder",
  onClose,
}: {
  folderPath: string;
  shareKind?: "file" | "folder";
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const [users, setUsers] = useState<ManagedLocalUser[]>([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [permission, setPermission] = useState<"read" | "write">("read");
  const [existing, setExisting] = useState<Array<{ shareId: string; label: string; permission: string }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const isFolderShare = shareKind === "folder";

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

  useEffect(() => {
    void (async () => {
      try {
        const [userList, shares] = await Promise.all([
          localApi.localUsers(),
          localApi.listWorkspaceShares(folderPath),
        ]);
        setUsers(userList.items.filter((item) => !item.isDeviceOwner));
        setExisting(
          shares.items.map((item) => ({
            shareId: item.shareId,
            label: item.granteeDisplayName || item.granteeUsername,
            permission: item.permission,
          })),
        );
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Sharing could not be loaded.");
      }
    })();
  }, [folderPath]);

  function closeDialog() {
    const dialog = dialogRef.current;
    if (dialog?.open) {
      dialog.close();
      return;
    }
    onClose();
  }

  async function shareWithUser() {
    if (!selectedUserId) {
      return;
    }
    setWorking(true);
    setError(null);
    setMessage(null);
    try {
      await localApi.saveWorkspaceShare(folderPath, selectedUserId, permission);
      const shares = await localApi.listWorkspaceShares(folderPath);
      setExisting(
        shares.items.map((item) => ({
          shareId: item.shareId,
          label: item.granteeDisplayName || item.granteeUsername,
          permission: item.permission,
        })),
      );
      setMessage(isFolderShare ? "Folder shared." : "File shared.");
      setSelectedUserId("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "This item could not be shared.");
    } finally {
      setWorking(false);
    }
  }

  async function revoke(shareId: string) {
    setWorking(true);
    setError(null);
    setMessage(null);
    try {
      await localApi.revokeWorkspaceShare(shareId);
      setExisting((current) => current.filter((item) => item.shareId !== shareId));
      setMessage("Access removed.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Access could not be removed.");
    } finally {
      setWorking(false);
    }
  }

  return createPortal(
    <dialog
      aria-labelledby="workspace-share-title"
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
            <span className="browser-voice-eyebrow-label">Workspace</span>
            <h2 id="workspace-share-title">{isFolderShare ? "Share folder" : "Share file"}</h2>
            <p className="browser-voice-share-folder-path">
              <strong>{itemTitle(folderPath, shareKind)}</strong>
              {folderPath ? <small>{folderPath}</small> : null}
            </p>
          </div>
          <button aria-label="Close share dialog" className="browser-voice-modal-close" onClick={closeDialog} type="button">
            ×
          </button>
        </div>

        {isFolderShare ? (
          <p className="browser-voice-share-warning" role="note">
            Everything in this folder and its subfolders will be visible to people you share with.
          </p>
        ) : null}

        <div className="browser-voice-modal-fields">
          <label className="browser-voice-modal-wide">
            <span>Vault user</span>
            <select onChange={(event) => setSelectedUserId(event.target.value)} value={selectedUserId}>
              <option value="">Choose a user</option>
              {users.map((user) => (
                <option key={user.userId} value={user.userId}>
                  {user.displayName} ({user.username})
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="browser-voice-share-access">
          <span>Access</span>
          <div className="browser-voice-share-access-options" role="group" aria-label="Access level">
            <button
              className={permission === "read" ? "is-active" : ""}
              onClick={() => setPermission("read")}
              type="button"
            >
              Read
            </button>
            <button
              className={permission === "write" ? "is-active" : ""}
              onClick={() => setPermission("write")}
              type="button"
            >
              Read &amp; write
            </button>
          </div>
        </div>

        {error ? <p className="browser-voice-modal-error" role="alert">{error}</p> : null}
        {message ? <p className="browser-voice-share-message" role="status">{message}</p> : null}

        <div className="browser-voice-modal-actions">
          <button className="browser-voice-pill" onClick={closeDialog} type="button">
            Cancel
          </button>
          <button className="browser-voice-submit" disabled={working || !selectedUserId} onClick={() => void shareWithUser()} type="button">
            Share
          </button>
        </div>

        {existing.length ? (
          <section aria-label="People with access" className="browser-voice-share-existing">
            <h3>People with access</h3>
            <ul>
              {existing.map((item) => (
                <li className="browser-voice-share-member" key={item.shareId}>
                  <span>
                    <strong>{item.label}</strong>
                    <small>{item.permission === "write" ? "Read & write" : "Read"}</small>
                  </span>
                  <button
                    className="browser-voice-pill browser-voice-pill-muted"
                    disabled={working}
                    onClick={() => void revoke(item.shareId)}
                    type="button"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </dialog>,
    document.body,
  );
}
