const DB_NAME = "resono-vault-computer-folders";
const DB_VERSION = 1;
const STORE = "handles";

declare global {
  interface Window {
    showDirectoryPicker?: (options?: { mode?: "read" | "readwrite" }) => Promise<FileSystemDirectoryHandle>;
  }
}

type StoredFolderHandle = {
  mountId: string;
  handle: FileSystemDirectoryHandle;
};

function sanitizeMountName(rawName: string): string {
  const trimmed = rawName.trim().replace(/[^\w.-]+/g, "-").replace(/^-+|-+$/g, "");
  const normalized = trimmed || "Folder";
  return normalized.slice(0, 64);
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onerror = () => reject(request.error ?? new Error("Computer folder storage failed to open."));
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE)) {
        database.createObjectStore(STORE, { keyPath: "mountId" });
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function withStore<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE, mode);
    const store = transaction.objectStore(STORE);
    const request = action(store);
    request.onerror = () => reject(request.error ?? new Error("Computer folder storage failed."));
    request.onsuccess = () => resolve(request.result);
    transaction.oncomplete = () => database.close();
    transaction.onerror = () => reject(transaction.error ?? new Error("Computer folder storage failed."));
  });
}

export function computerFoldersSupported(): boolean {
  return typeof window.showDirectoryPicker === "function";
}

export async function pickComputerFolder(permission: "read" | "write"): Promise<{
  mountId: string;
  suggestedName: string;
  label: string;
}> {
  const picker = window.showDirectoryPicker;
  if (!picker) {
    throw new Error("Your browser does not support folder linking. Try Chrome or Edge on this computer.");
  }
  const handle = await picker({
    mode: permission === "write" ? "readwrite" : "read",
  });
  const mountId = crypto.randomUUID();
  await withStore("readwrite", (store) => store.put({ mountId, handle } satisfies StoredFolderHandle));
  return {
    mountId,
    suggestedName: sanitizeMountName(handle.name),
    label: handle.name,
  };
}

export async function removeComputerFolderHandle(mountId: string): Promise<void> {
  await withStore("readwrite", (store) => store.delete(mountId));
}

export async function hasComputerFolderHandle(mountId: string): Promise<boolean> {
  const record = await withStore<StoredFolderHandle | undefined>("readonly", (store) => store.get(mountId));
  return Boolean(record?.handle);
}
