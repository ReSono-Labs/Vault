import { useEffect, useState } from "react";
import { localApi, type FolderBrowse } from "@/browser-voice/localApi";
import { FolderDialog, errorText } from "@/browser-voice/folders/FolderDialog";

/** Where the picker starts: the user's own access, or (admin) everything Vault can see. */
export type FolderPickerSource = "user" | "admin";

type Place = { id: string; label: string; path: string; canWrite: boolean; note: string | null };

export type PickedFolder = {
  /** grantId (user) or locationId (admin). */
  scopeId: string;
  path: string;
  label: string;
  canWrite: boolean;
};

export type NewFolderRequest = PickedFolder & { name: string };

async function loadPlaces(source: FolderPickerSource): Promise<Place[]> {
  if (source === "user") {
    const result = await localApi.folderPlaces();
    return result.items.map((item) => ({
      id: item.grantId,
      label: item.label,
      path: "",
      canWrite: item.canWrite,
      note: item.status === "ok" ? null : item.statusMessage,
    }));
  }
  const result = await localApi.folderLocations();
  return result.places.map((item) => ({
    id: item.locationId,
    label: item.label,
    path: item.path,
    canWrite: true,
    note: null,
  }));
}

/**
 * Point-and-click folder browser. One click opens a folder, the breadcrumb goes back,
 * and nothing above the starting places can be reached.
 */
export function FolderPicker({
  source,
  title,
  chooseLabel = "Choose this folder",
  allowCreate = false,
  onChoose,
  onCreate,
  onClose,
}: {
  source: FolderPickerSource;
  title: string;
  chooseLabel?: string;
  allowCreate?: boolean;
  onChoose: (picked: PickedFolder) => void;
  onCreate?: (request: NewFolderRequest) => void;
  onClose: () => void;
}) {
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [place, setPlace] = useState<Place | null>(null);
  const [path, setPath] = useState("");
  const [listing, setListing] = useState<FolderBrowse | null>(null);
  const [naming, setNaming] = useState(false);
  const [newName, setNewName] = useState("New folder");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    loadPlaces(source)
      .then((items) => {
        if (!live) return;
        setPlaces(items);
        const first = items.find((item) => !item.note) ?? null;
        if (first) {
          setPlace(first);
          setPath(first.path);
        }
      })
      .catch((caught) => live && setError(errorText(caught, "Folders could not be loaded.")));
    return () => {
      live = false;
    };
  }, [source]);

  useEffect(() => {
    if (!place) return;
    let live = true;
    setLoading(true);
    setError(null);
    const request = source === "user" ? localApi.browseFolder(place.id, path) : localApi.browseLocation(place.id, path);
    request
      .then((value) => live && setListing(value))
      .catch((caught) => {
        if (!live) return;
        setListing(null);
        setError(errorText(caught, "This folder could not be opened."));
      })
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [place, path, source]);

  function openPlace(next: Place) {
    setNaming(false);
    setPlace(next);
    setPath(next.path);
  }

  function open(nextPath: string) {
    setNaming(false);
    setPath(nextPath);
  }

  const crumbs = listing?.breadcrumbs ?? [];
  const label = crumbs.map((crumb) => crumb.label).join(" / ") || place?.label || "";
  const picked: PickedFolder | null = place ? { scopeId: place.id, path, label, canWrite: place.canWrite } : null;
  const canCreate = allowCreate && Boolean(onCreate) && Boolean(listing?.canCreate);

  return (
    <FolderDialog eyebrow="Folders" onClose={onClose} title={title} titleId="folder-picker-title">
      {places && places.length === 0 ? (
        <p className="browser-voice-form-note">
          {source === "user"
            ? "Your admin hasn't shared any folders with you yet."
            : "Folders aren't set up on this computer."}
        </p>
      ) : (
        <div className="browser-voice-folder-picker">
          <nav aria-label="Places" className="browser-voice-folder-places">
            {(places ?? []).map((item) => (
              <button
                aria-current={place?.id === item.id && path === item.path ? "true" : undefined}
                className={place?.id === item.id && path === item.path ? "is-active" : ""}
                disabled={Boolean(item.note)}
                key={`${item.id}:${item.path}`}
                onClick={() => openPlace(item)}
                title={item.note ?? undefined}
                type="button"
              >
                {item.label}
                {item.note ? <small>{item.note}</small> : null}
              </button>
            ))}
          </nav>
          <div className="browser-voice-folder-browser">
            <nav aria-label="Folder path" className="browser-voice-folder-crumbs">
              {crumbs.map((crumb, index) => (
                <span key={crumb.path || "root"}>
                  {index > 0 ? <span aria-hidden="true"> › </span> : null}
                  <button
                    aria-current={index === crumbs.length - 1 ? "true" : undefined}
                    disabled={index === crumbs.length - 1}
                    onClick={() => open(crumb.path)}
                    type="button"
                  >
                    {crumb.label}
                  </button>
                </span>
              ))}
            </nav>
            <ul aria-busy={loading} aria-label="Folders" className="browser-voice-folder-list">
              {listing?.directories.map((directory) => (
                <li key={directory.path}>
                  <button onClick={() => open(directory.path)} type="button">
                    <span aria-hidden="true" className="browser-voice-folder-icon" />
                    {directory.name}
                  </button>
                </li>
              ))}
              {listing && listing.directories.length === 0 ? (
                <li className="browser-voice-folder-empty">No folders inside this one.</li>
              ) : null}
            </ul>
            {naming ? (
              <form
                className="browser-voice-folder-new"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (picked && newName.trim()) onCreate?.({ ...picked, name: newName.trim() });
                }}
              >
                <label>
                  <span>New folder name</span>
                  <input autoFocus maxLength={64} onChange={(event) => setNewName(event.target.value)} value={newName} />
                </label>
                <button className="browser-voice-pill" onClick={() => setNaming(false)} type="button">
                  Cancel
                </button>
                <button className="browser-voice-submit" disabled={!newName.trim()} type="submit">
                  Make folder
                </button>
              </form>
            ) : null}
          </div>
        </div>
      )}
      {error ? <p className="browser-voice-modal-error" role="alert">{error}</p> : null}
      <div className="browser-voice-modal-actions">
        <button className="browser-voice-pill" onClick={onClose} type="button">
          Cancel
        </button>
        {canCreate && !naming ? (
          <button className="browser-voice-pill" onClick={() => setNaming(true)} type="button">
            Make a new folder here
          </button>
        ) : null}
        <button
          className="browser-voice-submit"
          disabled={!picked || !listing || loading}
          onClick={() => picked && onChoose(picked)}
          type="button"
        >
          {chooseLabel}
        </button>
      </div>
    </FolderDialog>
  );
}
