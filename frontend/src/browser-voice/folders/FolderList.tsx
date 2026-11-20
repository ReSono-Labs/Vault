import { useState } from "react";
import { BrowserVoiceWorkspaceIcon } from "@/browser-voice/presentation/BrowserVoiceIcons";
import type { FolderPermission, FolderStatus } from "@/browser-voice/localApi";

export type FolderRow = {
  id: string;
  name: string;
  detail: string;
  permission: FolderPermission;
  /** Highest permission allowed; "read" disables the edit option. */
  maxPermission: FolderPermission;
  status: FolderStatus;
  statusMessage: string | null;
  /** Hidden files switch; leave undefined to not show it. */
  includeHidden?: boolean;
  /** Why the switch can't be used here, if it can't. */
  hiddenLockedReason?: string | null;
};

/** A list of folders with a Can view / Can view and edit switch and a Remove button on each row. */
export function FolderList({
  rows,
  busy,
  onPermission,
  onRemove,
  removeQuestion,
  onHidden,
}: {
  rows: FolderRow[];
  busy: boolean;
  onPermission: (row: FolderRow, permission: FolderPermission) => void;
  onRemove: (row: FolderRow) => void;
  removeQuestion: (row: FolderRow) => string;
  onHidden?: (row: FolderRow, includeHidden: boolean) => void;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);
  return (
    <div className="browser-voice-agent-list browser-voice-folder-rows">
      {rows.map((row) => {
        const editable = row.permission === "write";
        return (
          <article className={`browser-voice-agent-row is-${row.status === "ok" ? "on" : "off"}`} key={row.id}>
            <span className="browser-voice-agent-row-main">
              <span className="browser-voice-agent-mark">
                <BrowserVoiceWorkspaceIcon />
              </span>
              <span>
                <strong>{row.name}</strong>
                <small>{row.detail}</small>
                {row.status !== "ok" ? (
                  <small className="browser-voice-folder-warning" role="status">
                    ⚠ {row.statusMessage}
                  </small>
                ) : null}
              </span>
            </span>
            {confirming === row.id ? (
              <span className="browser-voice-folder-confirm" role="group" aria-label={`Remove ${row.name}`}>
                <small>{removeQuestion(row)}</small>
                <button className="browser-voice-pill" disabled={busy} onClick={() => setConfirming(null)} type="button">
                  Cancel
                </button>
                <button
                  className="browser-voice-account-danger"
                  disabled={busy}
                  onClick={() => {
                    setConfirming(null);
                    onRemove(row);
                  }}
                  type="button"
                >
                  Confirm
                </button>
              </span>
            ) : (
              <span className="browser-voice-folder-row-actions">
                {onHidden && row.includeHidden !== undefined ? (
                  <button
                    aria-label={`${row.name}: hidden files ${row.includeHidden ? "shown" : "hidden"}. Change.`}
                    aria-pressed={row.includeHidden}
                    className="browser-voice-pill"
                    disabled={busy || Boolean(row.hiddenLockedReason)}
                    onClick={() => onHidden(row, !row.includeHidden)}
                    title={row.hiddenLockedReason ?? undefined}
                    type="button"
                  >
                    {row.includeHidden ? "Hidden files shown" : "Hidden files hidden"}
                  </button>
                ) : null}
                <button
                  aria-label={`${row.name}: ${editable ? "Can view and edit" : "Can view"}. Change.`}
                  aria-pressed={editable}
                  className="browser-voice-pill"
                  disabled={busy || (!editable && row.maxPermission !== "write")}
                  onClick={() => onPermission(row, editable ? "read" : "write")}
                  title={!editable && row.maxPermission !== "write" ? "This folder is view-only." : undefined}
                  type="button"
                >
                  {editable ? "Can view and edit" : "Can view"}
                </button>
                <button
                  className="browser-voice-pill browser-voice-pill-muted"
                  disabled={busy}
                  onClick={() => setConfirming(row.id)}
                  type="button"
                >
                  Remove
                </button>
              </span>
            )}
          </article>
        );
      })}
    </div>
  );
}
