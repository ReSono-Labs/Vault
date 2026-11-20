import type { PendingPluginImport } from "@/browser-voice/pluginPackageFlow";

type PendingListener = (pending: PendingPluginImport | null) => void;
type CompleteHandler = (result: { identity: string; message: string }) => void | Promise<void>;

let pending: PendingPluginImport | null = null;
let completeHandler: CompleteHandler | null = null;
const listeners = new Set<PendingListener>();

export function getPendingPluginImport(): PendingPluginImport | null {
  return pending;
}

export function setPendingPluginImport(value: PendingPluginImport | null): void {
  pending = value;
  listeners.forEach((listener) => listener(value));
}

export function subscribePendingPluginImport(listener: PendingListener): () => void {
  listeners.add(listener);
  listener(pending);
  return () => listeners.delete(listener);
}

export function registerPluginImportCompleteHandler(handler: CompleteHandler | null): void {
  completeHandler = handler;
}

export async function notifyPluginImportComplete(result: { identity: string; message: string }): Promise<void> {
  if (completeHandler) {
    await completeHandler(result);
  }
}
