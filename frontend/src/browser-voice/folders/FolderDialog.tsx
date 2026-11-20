import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Modal shell shared by the folder dialogs (same look as the share and import dialogs). */
export function FolderDialog({
  eyebrow,
  title,
  titleId,
  onClose,
  children,
}: {
  eyebrow: string;
  title: string;
  titleId: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    return () => {
      if (dialog.open) dialog.close();
    };
  }, []);

  return createPortal(
    <dialog
      aria-labelledby={titleId}
      className="browser-voice-modal browser-voice-share-modal browser-voice-folder-dialog"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      ref={dialogRef}
    >
      <div className="browser-voice-share-dialog-body">
        <div className="browser-voice-modal-head">
          <div>
            <span className="browser-voice-eyebrow-label">{eyebrow}</span>
            <h2 id={titleId}>{title}</h2>
          </div>
          <button aria-label="Close" className="browser-voice-modal-close" onClick={onClose} type="button">
            ×
          </button>
        </div>
        {children}
      </div>
    </dialog>,
    document.body,
  );
}

/** "Can view" / "Can view and edit" toggle. */
export function PermissionToggle({
  value,
  onChange,
  canEdit = true,
  disabled = false,
  label = "What can agents do?",
}: {
  value: "read" | "write";
  onChange: (value: "read" | "write") => void;
  canEdit?: boolean;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <div className="browser-voice-share-access">
      <span>{label}</span>
      <div className="browser-voice-share-access-options" role="group" aria-label={label}>
        <button
          aria-pressed={value === "read"}
          className={value === "read" ? "is-active" : ""}
          disabled={disabled}
          onClick={() => onChange("read")}
          type="button"
        >
          Can view
        </button>
        <button
          aria-pressed={value === "write"}
          className={value === "write" ? "is-active" : ""}
          disabled={disabled || !canEdit}
          onClick={() => onChange("write")}
          title={canEdit ? undefined : "This folder is view-only."}
          type="button"
        >
          Can view and edit
        </button>
      </div>
    </div>
  );
}

/** "Show hidden files" checkbox; covers the folder and everything inside it. */
export function HiddenFilesOption({
  checked,
  onChange,
  disabled = false,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="browser-voice-setup-folder-option">
      <input checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} type="checkbox" />
      <span>
        <strong>Show hidden files</strong>
        <small>
          Files and folders whose names start with a dot, like .gitignore. Applies to this folder and everything
          inside it.
        </small>
      </span>
    </label>
  );
}

export function errorText(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}
