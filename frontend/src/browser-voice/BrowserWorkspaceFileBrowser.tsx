import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, PointerEvent as ReactPointerEvent } from "react";
import { WorkspaceShareDialog } from "@/browser-voice/WorkspaceShareDialog";
import {
  downloadBrowserLocalFile,
  isBrowserLocalMountPath,
  listBrowserLocalDirectory,
  listBrowserLocalRoot,
  readBrowserLocalFile,
} from "@/browser-voice/computerFoldersWorkspace";
import {
  localApi,
  type HostFilesystemMount,
  type WorkspaceFileDirectoryResponse,
  type WorkspaceFileEntry,
  type WorkspaceFileReadResponse,
} from "@/browser-voice/localApi";

type PreviewState = {
  url: string | null;
  kind: "none" | "image" | "pdf";
  contentType: string | null;
};



const EMPTY_PREVIEW: PreviewState = {
  url: null,
  kind: "none",
  contentType: null,
};

const SWIPE_ACTION_THRESHOLD_PX = 44;

type FileRowPointerGesture = {
  path: string;
  startX: number;
  startY: number;
};

function filenameFromPath(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path || "document.md";
}

function parentFromPath(path: string): string {
  const parts = path.split("/");
  parts.pop();
  return parts.join("/");
}

function upDirectoryTarget(
  directory: string,
  directoryData: WorkspaceFileDirectoryResponse | null,
): string | null {
  if (directoryData && directoryData.parentDirectory !== null) {
    return directoryData.parentDirectory;
  }
  const normalized = directory.trim();
  if (!normalized) {
    return null;
  }
  return parentFromPath(normalized);
}

function WorkspaceUpIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M15 18 9 12l6-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
    </svg>
  );
}

function joinPath(directory: string, name: string): string {
  return directory ? `${directory}/${name}` : name;
}

const SHARED_FILES_ROOT = "shared";
const LOCAL_FILES_ROOT = "local";

function isSharedViewPath(path: string): boolean {
  return path === SHARED_FILES_ROOT || path.startsWith(`${SHARED_FILES_ROOT}/`);
}

function isLocalViewPath(path: string): boolean {
  return path === LOCAL_FILES_ROOT || path.startsWith(`${LOCAL_FILES_ROOT}/`);
}

function isProtectedWorkspacePath(path: string): boolean {
  return isSharedViewPath(path) || isLocalViewPath(path);
}

function canWriteInDirectory(directory: string, data: WorkspaceFileDirectoryResponse | null): boolean {
  if (!isProtectedWorkspacePath(directory)) {
    return true;
  }
  return data?.permission === "write";
}

function normalizeTextFilename(rawName: string): string {
  const name = rawName.trim().replace(/\\/g, "/").split("/").filter(Boolean).join("/");
  if (!name) {
    return "";
  }
  return filenameFromPath(name).includes(".") ? name : `${name}.md`;
}

function formatBytes(sizeBytes: number | null | undefined): string {
  if (sizeBytes === null || sizeBytes === undefined) {
    return "-";
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
}

function typeLabel(entry: WorkspaceFileEntry): string {
  if (entry.kind === "directory") {
    return `${entry.childCount ?? 0} items`;
  }
  if (entry.mimeType?.startsWith("image/")) {
    return "Image";
  }
  if (entry.mimeType === "application/pdf") {
    return "PDF";
  }
  if (entry.editable) {
    return "Editable";
  }
  return "File";
}

function WorkspaceEntryIcon({ kind }: { kind: WorkspaceFileEntry["kind"] }) {
  if (kind === "directory") {
    return (
      <svg aria-hidden="true" className="browser-voice-file-open-icon" fill="none" viewBox="0 0 24 24">
        <path d="M3.5 6.5h6l2 2h9v10.5a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V6.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="browser-voice-file-open-icon" fill="none" viewBox="0 0 24 24">
      <path d="M6 3.5h8l4 4V20H6V3.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="M14 3.5V8h4M9 12h6M9 15.5h6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

function isPreviewableAsset(mimeType: string | null | undefined): boolean {
  return Boolean(mimeType?.startsWith("image/") || mimeType === "application/pdf");
}

function parentDirectoryPath(filePath: string): string {
  const slash = filePath.lastIndexOf("/");
  return slash === -1 ? "" : filePath.slice(0, slash);
}

function shareTargetForEntry(entry: WorkspaceFileEntry, currentDirectory: string): string | null {
  if (isProtectedWorkspacePath(entry.path) || isProtectedWorkspacePath(currentDirectory) || entry.shared || entry.linked) {
    return null;
  }
  return entry.path;
}

function WorkspaceShareIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <circle cx="7" cy="8" r="2.4" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="17" cy="6" r="2.4" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="17" cy="18" r="2.4" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9 9.2 14.8 7.4M9.4 10.8 14.8 16" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  );
}

export function BrowserWorkspaceFileBrowser({ initiallyExpanded = false }: { initiallyExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(initiallyExpanded);
  const [directory, setDirectory] = useState("");
  const [directoryData, setDirectoryData] = useState<WorkspaceFileDirectoryResponse | null>(null);
  const [selectedFileKey, setSelectedFileKey] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<WorkspaceFileReadResponse | null>(null);
  const [editorContent, setEditorContent] = useState("");
  const [renameName, setRenameName] = useState("");
  const [newFolderName, setNewFolderName] = useState("");
  const [newFileName, setNewFileName] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewState>(EMPTY_PREVIEW);
  const [movingEntry, setMovingEntry] = useState<WorkspaceFileEntry | null>(null);
  const [renamingEntryPath, setRenamingEntryPath] = useState<string | null>(null);
  const [moveDirectory, setMoveDirectory] = useState("");
  const [moveDirectoryData, setMoveDirectoryData] = useState<WorkspaceFileDirectoryResponse | null>(null);
  const [revealedEntryPath, setRevealedEntryPath] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [shareDialogTarget, setShareDialogTarget] = useState<{ path: string; kind: "file" | "folder" } | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const newMenuRef = useRef<HTMLDetailsElement | null>(null);
  const moreMenuRef = useRef<HTMLDetailsElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const fileRowPointerGestureRef = useRef<FileRowPointerGesture | null>(null);
  const suppressFileRowClickRef = useRef(false);
  const localMountsRef = useRef<HostFilesystemMount[]>([]);

  async function loadLocalMounts(): Promise<HostFilesystemMount[]> {
    const result = await localApi.hostFilesystemMounts();
    localMountsRef.current = result.items;
    return result.items;
  }

  const entries = directoryData?.entries ?? [];
  const visibleEntries = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!query) return entries;
    return entries.filter((entry) => `${entry.name} ${entry.path} ${typeLabel(entry)}`.toLocaleLowerCase().includes(query));
  }, [entries, searchQuery]);
  const currentDirectoryLabel = directoryData?.currentDirectory || "Workspace root";
  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.path === selectedFileKey) ?? null,
    [entries, selectedFileKey],
  );
  const hasUnsavedChanges = Boolean(selectedFile?.editable && editorContent !== selectedFile.contentMarkdown);
  const sharedPermission = directoryData?.permission ?? null;
  const canWrite = canWriteInDirectory(directory, directoryData);
  const upDirectory = upDirectoryTarget(directory, directoryData);

  useEffect(() => {
    if (!expanded) {
      return;
    }
    void refreshDirectory();
  }, [directory, expanded]);

  useEffect(() => {
    return () => releasePreviewUrl();
  }, []);

  function closeFileMenus() {
    if (newMenuRef.current) {
      newMenuRef.current.open = false;
    }
    if (moreMenuRef.current) {
      moreMenuRef.current.open = false;
    }
  }

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (newMenuRef.current?.contains(target) || moreMenuRef.current?.contains(target)) {
        return;
      }
      closeFileMenus();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  useEffect(() => {
    if (!movingEntry) {
      setMoveDirectoryData(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const data = isBrowserLocalMountPath(moveDirectory)
          ? await listBrowserLocalDirectory(
              moveDirectory,
              localMountsRef.current.length ? localMountsRef.current : await loadLocalMounts(),
            )
          : await localApi.listWorkspaceFiles(moveDirectory);
        if (!cancelled) {
          setMoveDirectoryData(data);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Move folder lookup failed.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [moveDirectory, movingEntry]);

  async function refreshDirectory() {
    setError(null);
    try {
      const normalizedDirectory = directory.trim();
      if (normalizedDirectory === LOCAL_FILES_ROOT) {
        const mounts = localMountsRef.current.length ? localMountsRef.current : await loadLocalMounts();
        setDirectoryData(await listBrowserLocalRoot(mounts));
        return;
      }
      const data = isBrowserLocalMountPath(directory)
        ? await listBrowserLocalDirectory(
            directory,
            localMountsRef.current.length ? localMountsRef.current : await loadLocalMounts(),
          )
        : await localApi.listWorkspaceFiles(directory || null);
      setDirectoryData(data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Workspace files failed to load.");
    }
  }

  function releasePreviewUrl() {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
  }

  function closePreview() {
    setSelectedFileKey(null);
    setSelectedFile(null);
    setEditorContent("");
    releasePreviewUrl();
    setPreview(EMPTY_PREVIEW);
  }

  async function openEntry(entry: WorkspaceFileEntry) {
    setRevealedEntryPath(null);
    setNotice(null);
    setError(null);
    if (entry.kind === "directory") {
      setDirectory(entry.path);
      setSelectedFileKey(null);
      setSelectedFile(null);
      setEditorContent("");
      setRenamingEntryPath(null);
      releasePreviewUrl();
      setPreview(EMPTY_PREVIEW);
      return;
    }
    await openFile(entry.path);
  }

  async function openFile(fileKey: string) {
    setBusy("Opening file");
    setSelectedFileKey(fileKey);
    releasePreviewUrl();
    setPreview(EMPTY_PREVIEW);
    try {
      const mounts = localMountsRef.current.length ? localMountsRef.current : await loadLocalMounts();
      const readBack = isBrowserLocalMountPath(fileKey)
        ? await readBrowserLocalFile(fileKey, mounts)
        : await localApi.readWorkspaceFile(fileKey);
      setSelectedFile(readBack);
      setEditorContent(readBack.contentMarkdown);
      if (isPreviewableAsset(readBack.mimeType)) {
        const { blob, contentType } = isBrowserLocalMountPath(fileKey)
          ? await downloadBrowserLocalFile(fileKey, mounts)
          : await localApi.downloadWorkspaceFile(fileKey);
        const assetUrl = URL.createObjectURL(blob);
        previewUrlRef.current = assetUrl;
        const normalizedType = contentType.split(";", 1)[0].toLowerCase();
        setPreview({
          url: assetUrl,
          kind: normalizedType.startsWith("image/") ? "image" : "pdf",
          contentType: normalizedType,
        });
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "File failed to open.");
    } finally {
      setBusy(null);
    }
  }

  async function createFolder() {
    const folderName = newFolderName.trim();
    if (!folderName) {
      setError("Enter a folder name.");
      return;
    }
    await runMutation("Creating folder", async () => {
      const result = await localApi.createWorkspaceDirectory( joinPath(directory, folderName));
      setNewFolderName("");
      setNotice(result.message);
      closeFileMenus();
    });
  }

  async function createTextFile() {
    const fileName = normalizeTextFilename(newFileName);
    if (!fileName) {
      setError("Enter a file name.");
      return;
    }
    await runMutation("Creating file", async () => {
      const fileKey = joinPath(directory, fileName);
      const result = await localApi.createWorkspaceTextFile( fileKey, "");
      setNewFileName("");
      setNotice(result.message);
      closeFileMenus();
      await openFile(result.path ?? fileKey);
    });
  }

  async function uploadSelectedFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files || files.length === 0) {
      return;
    }
    await runMutation("Uploading files", async () => {
      const result = await localApi.uploadWorkspaceFiles( directory || null, files);
      setNotice(result.message);
      if (result.destinationPath) {
        await openFile(result.destinationPath);
      }
    });
    event.target.value = "";
  }

  async function saveSelectedFile() {
    if (!selectedFileKey || !selectedFile?.editable) {
      return;
    }
    await runMutation("Saving file", async () => {
      const result = await localApi.saveWorkspaceFile( selectedFileKey, editorContent);
      setNotice(result.message);
      await openFile(selectedFileKey);
    });
  }

  function beginRename(entry: WorkspaceFileEntry) {
    setRenameName(entry.name);
    setRenamingEntryPath(entry.path);
    setRevealedEntryPath(null);
  }

  async function renameEntry(entry: WorkspaceFileEntry) {
    if (!renameName.trim()) {
      return;
    }
    const destinationPath = joinPath(parentFromPath(entry.path), renameName.trim());
    if (destinationPath === entry.path) {
      setNotice("That file already has this name.");
      setRenamingEntryPath(null);
      return;
    }
    await runMutation("Renaming file", async () => {
      const result = await localApi.moveWorkspacePath( entry.path, destinationPath);
      const nextPath = result.destinationPath ?? destinationPath;
      if (selectedFileKey === entry.path) {
        setSelectedFileKey(nextPath);
        await openFile(nextPath);
      }
      setRenamingEntryPath(null);
      setNotice(result.message);
    });
  }

  async function deleteEntry(entry: WorkspaceFileEntry) {
    const recursive = entry.kind === "directory";
    const confirmed = window.confirm(
      recursive ? `Delete folder "${entry.path}" and everything inside it?` : `Delete file "${entry.path}"?`,
    );
    if (!confirmed) {
      return;
    }
    setRevealedEntryPath(null);
    await runMutation("Deleting", async () => {
      const result = await localApi.deleteWorkspacePath( entry.path, recursive);
      setNotice(result.message);
      if (selectedFileKey === entry.path || selectedFileKey?.startsWith(`${entry.path}/`)) {
        setSelectedFileKey(null);
        setSelectedFile(null);
        setEditorContent("");
        releasePreviewUrl();
        setPreview(EMPTY_PREVIEW);
      }
    });
  }

  async function downloadFile(fileKey: string) {
    await runMutation("Starting download", async () => {
      const { blob } = await localApi.downloadWorkspaceFile( fileKey);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filenameFromPath(fileKey);
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice("Download started.");
    });
  }

  function beginMove(entry: WorkspaceFileEntry) {
    setRevealedEntryPath(null);
    setMovingEntry(entry);
    setMoveDirectory(parentFromPath(entry.path));
    setNotice(null);
    setError(null);
  }

  function startFileRowPointerGesture(entry: WorkspaceFileEntry, event: ReactPointerEvent<HTMLButtonElement>) {
    fileRowPointerGestureRef.current = {
      path: entry.path,
      startX: event.clientX,
      startY: event.clientY,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function moveFileRowPointerGesture(event: ReactPointerEvent<HTMLButtonElement>) {
    const gesture = fileRowPointerGestureRef.current;
    if (!gesture) {
      return;
    }
    const deltaX = event.clientX - gesture.startX;
    const deltaY = event.clientY - gesture.startY;
    if (Math.abs(deltaX) < SWIPE_ACTION_THRESHOLD_PX || Math.abs(deltaX) <= Math.abs(deltaY)) {
      return;
    }
    suppressFileRowClickRef.current = true;
    setRevealedEntryPath(deltaX < 0 ? gesture.path : null);
  }

  function finishFileRowPointerGesture() {
    fileRowPointerGestureRef.current = null;
    window.setTimeout(() => {
      suppressFileRowClickRef.current = false;
    }, 0);
  }

  function handleFileRowClick(entry: WorkspaceFileEntry) {
    if (suppressFileRowClickRef.current) {
      suppressFileRowClickRef.current = false;
      return;
    }
    if (revealedEntryPath === entry.path) {
      setRevealedEntryPath(null);
      return;
    }
    void openEntry(entry);
  }

  function toggleExpanded() {
    setExpanded((current) => {
      if (current) {
        setMovingEntry(null);
      }
      return !current;
    });
  }

  async function confirmMove() {
    if (!movingEntry) {
      return;
    }
    const destinationPath = joinPath(moveDirectory, movingEntry.name);
    if (destinationPath === movingEntry.path) {
      setNotice("That item is already in the selected folder.");
      setMovingEntry(null);
      return;
    }
    await runMutation("Moving item", async () => {
      const result = await localApi.moveWorkspacePath( movingEntry.path, destinationPath);
      setNotice(result.message);
      if (selectedFileKey === movingEntry.path) {
        const nextPath = result.destinationPath ?? destinationPath;
        setSelectedFileKey(nextPath);
        await openFile(nextPath);
      }
      setMovingEntry(null);
    });
  }

  async function runMutation(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try {
      await action();
      await refreshDirectory();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `${label} failed.`);
    } finally {
      setBusy(null);
    }
  }

  const moveFolders = (moveDirectoryData?.entries ?? []).filter((entry) => {
    if (entry.kind !== "directory") {
      return false;
    }
    if (!movingEntry || movingEntry.kind !== "directory") {
      return true;
    }
    return entry.path !== movingEntry.path && !entry.path.startsWith(`${movingEntry.path}/`);
  });

  return (
    <section className={`browser-voice-handoff-shell browser-voice-files-shell ${expanded ? "is-expanded" : "is-collapsed"}`}>
      <div className="browser-voice-files-head">
        {expanded ? (
          <label className="browser-voice-files-search">
            <span aria-hidden="true">⌕</span>
            <input
              aria-label="Search workspace files"
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search files"
              type="search"
              value={searchQuery}
            />
          </label>
        ) : (
          <div className="browser-voice-handoff-copy">
            <p className="browser-voice-panel-label">Workspace</p>
          </div>
        )}
        <div className="browser-voice-files-actions">
          {expanded ? (
            <>
              {canWrite ? (
                <>
                  <input
                    className="browser-voice-hidden-file-input"
                    multiple
                    onChange={(event) => void uploadSelectedFiles(event)}
                    ref={fileInputRef}
                    type="file"
                  />
                  <button className="browser-voice-chip" disabled={Boolean(busy)} onClick={() => fileInputRef.current?.click()} type="button">
                    Upload
                  </button>
                  <details className="browser-voice-files-new-menu" ref={newMenuRef}>
                    <summary>New folder</summary>
                    <div className="browser-voice-files-new-menu-panel">
                      <div className="browser-voice-files-inline-field">
                        <input
                          className="browser-voice-handoff-input"
                          onChange={(event) => setNewFolderName(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              void createFolder();
                            }
                          }}
                          placeholder="Folder name"
                          value={newFolderName}
                        />
                        <button className="browser-voice-chip" disabled={Boolean(busy) || !newFolderName.trim()} onClick={() => void createFolder()} type="button">Create</button>
                      </div>
                      <p>Or create a text file</p>
                      <div className="browser-voice-files-inline-field">
                        <input
                          className="browser-voice-handoff-input"
                          onChange={(event) => setNewFileName(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              void createTextFile();
                            }
                          }}
                          placeholder="File name"
                          value={newFileName}
                        />
                        <button className="browser-voice-chip" disabled={Boolean(busy) || !newFileName.trim()} onClick={() => void createTextFile()} type="button">Create</button>
                      </div>
                    </div>
                  </details>
                </>
              ) : null}
              <details className="browser-voice-files-more-menu" ref={moreMenuRef}>
                <summary aria-label="More workspace actions">•••</summary>
                <div>
                  <button disabled={Boolean(busy)} onClick={() => {
                    closeFileMenus();
                    void refreshDirectory();
                  }} type="button">Refresh</button>
                  <button aria-expanded={expanded} onClick={() => {
                    closeFileMenus();
                    toggleExpanded();
                  }} type="button">Collapse</button>
                </div>
              </details>
            </>
          ) : (
            <button aria-expanded={expanded} className="browser-voice-chip" onClick={toggleExpanded} type="button">Expand</button>
          )}
        </div>
      </div>

      {expanded ? (
        <>
          <div className="browser-voice-files-sync-state" role="status">
            <span aria-hidden="true" />
            <strong>{directoryData ? "Vault workspace current" : "Loading Vault workspace"}</strong>
            <small>{currentDirectoryLabel}</small>
          </div>

          {busy ? <div className="browser-voice-files-feedback">{busy}...</div> : null}
          {notice ? <div className="browser-voice-files-feedback browser-voice-files-feedback-success">{notice}</div> : null}
          {error ? <div className="browser-voice-files-feedback browser-voice-files-feedback-error">{error}</div> : null}

          <div className="browser-voice-files-layout">
            <div className="browser-voice-files-list" aria-label="Workspace files">
              <div className="browser-voice-files-directory">
                <strong>{currentDirectoryLabel}</strong>
                <small>Swipe left for actions</small>
              </div>
              {visibleEntries.length ? (
                visibleEntries.map((entry) => {
                  const actionsRevealed = revealedEntryPath === entry.path;
                  const isSelectedFile = entry.kind === "file" && selectedFileKey === entry.path;
                  const isRenaming = renamingEntryPath === entry.path;
                  const shareTarget = shareTargetForEntry(entry, directory);
                  return (
                    <div
                      className={`browser-voice-file-row ${selectedFileKey === entry.path ? "is-selected" : ""} ${actionsRevealed ? "has-actions-revealed" : ""} ${isSelectedFile ? "has-inline-actions" : ""}${shareTarget ? " has-share-action" : ""}`}
                      key={`${entry.kind}:${entry.path}`}
                    >
                      <div className="browser-voice-file-swipe-actions" aria-hidden={!actionsRevealed}>
                        {canWrite ? (
                          <button className="browser-voice-file-swipe-action" onClick={() => beginMove(entry)} tabIndex={actionsRevealed ? 0 : -1} type="button">
                            Move
                          </button>
                        ) : null}
                        {canWrite ? (
                          <button
                            className="browser-voice-file-swipe-action is-danger"
                            onClick={() => void deleteEntry(entry)}
                            tabIndex={actionsRevealed ? 0 : -1}
                            type="button"
                          >
                            Delete
                          </button>
                        ) : null}
                      </div>
                      {isRenaming ? (
                        <form
                          className="browser-voice-file-inline-rename"
                          onSubmit={(event) => {
                            event.preventDefault();
                            void renameEntry(entry);
                          }}
                        >
                          <input
                            aria-label={`Rename ${entry.name}`}
                            autoFocus
                            onChange={(event) => setRenameName(event.target.value)}
                            value={renameName}
                          />
                          <button aria-label="Save new name" disabled={Boolean(busy) || !renameName.trim()} title="Save new name" type="submit">✓</button>
                          <button aria-label="Cancel rename" onClick={() => setRenamingEntryPath(null)} title="Cancel rename" type="button">×</button>
                        </form>
                      ) : (
                        <div className="browser-voice-file-row-body">
                          <button
                            aria-label={`Open ${entry.kind === "directory" ? "folder" : "file"} ${entry.name}`}
                            className="browser-voice-file-open"
                            onClick={() => handleFileRowClick(entry)}
                            onPointerCancel={finishFileRowPointerGesture}
                            onPointerDown={(event) => startFileRowPointerGesture(entry, event)}
                            onPointerMove={moveFileRowPointerGesture}
                            onPointerUp={finishFileRowPointerGesture}
                            type="button"
                          >
                            <WorkspaceEntryIcon kind={entry.kind} />
                            <span className="browser-voice-file-open-copy">
                              <strong>{entry.name}</strong>
                              <small>{typeLabel(entry)} · {entry.kind === "file" ? formatBytes(entry.sizeBytes) : entry.path}</small>
                            </span>
                            {shareTarget ? null : <em aria-hidden="true">›</em>}
                          </button>
                          {shareTarget ? (
                            <button
                              aria-label={`Share ${entry.kind === "directory" ? "folder" : "file"} ${entry.name}`}
                              className="browser-voice-file-share-button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setShareDialogTarget({
                                  path: shareTarget,
                                  kind: entry.kind === "directory" ? "folder" : "file",
                                });
                              }}
                              type="button"
                            >
                              <WorkspaceShareIcon />
                            </button>
                          ) : null}
                          {isSelectedFile ? (
                            <div className="browser-voice-file-inline-actions">
                              <button aria-label={`Rename ${entry.name}`} disabled={Boolean(busy)} onClick={() => beginRename(entry)} title="Rename" type="button">
                                <svg aria-hidden="true" fill="none" viewBox="0 0 24 24"><path d="m4 16.5-.8 4.3 4.3-.8L18.7 8.8l-3.5-3.5L4 16.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="m13.8 6.7 3.5 3.5" stroke="currentColor" strokeWidth="1.7" /></svg>
                              </button>
                              <button aria-label={`Download ${entry.name}`} disabled={Boolean(busy)} onClick={() => void downloadFile(entry.path)} title="Download" type="button">
                                <svg aria-hidden="true" fill="none" viewBox="0 0 24 24"><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 20h14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></svg>
                              </button>
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  );
                })
              ) : (
                <p className="browser-voice-empty">{searchQuery.trim() ? "No matching files." : "No files in this folder."}</p>
              )}
              {upDirectory !== null ? (
                <button
                  aria-label="Up one folder"
                  className="browser-voice-files-up-button"
                  disabled={Boolean(busy)}
                  onClick={() => setDirectory(upDirectory)}
                  type="button"
                >
                  <WorkspaceUpIcon />
                  <span>Up one folder</span>
                </button>
              ) : null}
            </div>

            <div className={`browser-voice-files-preview ${selectedFile || selectedEntry ? "has-selection" : "is-empty"}`} aria-label="File preview">
              {selectedFile ? (
                <>
                  <div className="browser-voice-files-preview-head">
                    <button
                      aria-label={`Close preview of ${selectedFile.filename}`}
                      className="browser-voice-chip"
                      onClick={() => closePreview()}
                      type="button"
                    >
                      Close
                    </button>
                  </div>
                  {selectedFile.editable ? (
                    <>
                      <textarea
                        aria-label={`Edit ${selectedFile.filename}`}
                        className="browser-voice-file-editor"
                        onChange={(event) => setEditorContent(event.target.value)}
                        value={editorContent}
                      />
                      <button
                        className="browser-voice-submit browser-voice-files-save-button"
                        disabled={Boolean(busy) || !hasUnsavedChanges}
                        onClick={() => void saveSelectedFile()}
                        type="button"
                      >
                        Save
                      </button>
                    </>
                  ) : preview.kind === "image" && preview.url ? (
                    <div className="browser-voice-file-asset-preview">
                      <img alt={selectedFile.filename} src={preview.url} />
                    </div>
                  ) : preview.kind === "pdf" && preview.url ? (
                    <div className="browser-voice-file-asset-preview">
                      <iframe src={preview.url} title={selectedFile.filename} />
                    </div>
                  ) : (
                    <div className="browser-voice-files-feedback">This file can be shown or downloaded, but it is not text-editable here.</div>
                  )}
                </>
              ) : selectedEntry ? (
                <div className="browser-voice-files-feedback">Opening {selectedEntry.name}...</div>
              ) : (
                <div className="browser-voice-files-feedback">Open a file to preview or edit it.</div>
              )}
            </div>
          </div>

          {movingEntry ? (
            <div className="browser-voice-file-move-box">
              <div>
                <p className="browser-voice-panel-label">Move</p>
                <strong>{movingEntry.path}</strong>
                <span>Destination: {moveDirectory || "Workspace root"}</span>
              </div>
              <div className="browser-voice-files-actions">
                {moveDirectoryData?.parentDirectory !== null && moveDirectoryData ? (
                  <button className="browser-voice-chip" onClick={() => setMoveDirectory(moveDirectoryData.parentDirectory ?? "")} type="button">
                    Up
                  </button>
                ) : null}
                <button className="browser-voice-chip" onClick={() => setMoveDirectory("")} type="button">
                  Root
                </button>
                <button className="browser-voice-submit" disabled={Boolean(busy)} onClick={() => void confirmMove()} type="button">
                  Move here
                </button>
                <button className="browser-voice-chip" onClick={() => setMovingEntry(null)} type="button">
                  Cancel
                </button>
              </div>
              <div className="browser-voice-file-move-folders">
                {moveFolders.length ? (
                  moveFolders.map((entry) => (
                    <button className="browser-voice-file-folder-choice" key={entry.path} onClick={() => setMoveDirectory(entry.path)} type="button">
                      {entry.path}
                    </button>
                  ))
                ) : (
                  <span>No child folders here.</span>
                )}
              </div>
            </div>
          ) : null}
        </>
      ) : null}
      {shareDialogTarget ? (
        <WorkspaceShareDialog
          folderPath={shareDialogTarget.path}
          shareKind={shareDialogTarget.kind}
          onClose={() => setShareDialogTarget(null)}
        />
      ) : null}
    </section>
  );
}
