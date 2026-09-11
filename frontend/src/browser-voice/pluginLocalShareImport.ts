import { computerFoldersSupported, pickComputerFolder } from "@/browser-voice/computerFolders";
import { localApi } from "@/browser-voice/localApi";

export type PluginLocalSharePreflight = {
  mountName: string;
  permission: "read" | "write";
  label: string;
  required: boolean;
  permissionChoices: Array<"read" | "write">;
};

export type PluginLocalShareRegistration = {
  mountId: string;
  mountName: string;
  permission: "read" | "write";
};

export type PluginLocalSharePick = {
  mountId: string;
  suggestedName: string;
  label: string;
};

export function pluginLocalShareSupported(): boolean {
  return computerFoldersSupported();
}

/**
 * Open the folder picker. Must be the first await in a click handler — no setState
 * or other awaits before this call.
 */
export async function pickPluginLocalShareFolder(): Promise<PluginLocalSharePick> {
  if (!computerFoldersSupported()) {
    throw new Error("Your browser cannot link folders. Use Chrome or Edge on this computer.");
  }
  // Request read/write at pick time so either UI choice works without a second picker.
  return pickComputerFolder("write");
}

export async function ensureComputerFoldersEnabled(): Promise<void> {
  const settings = await localApi.hostFilesystemSettings();
  if (settings.enabled) {
    return;
  }
  const enable = window.confirm(
    "Computer folder linking is off. Turn it on now so this plugin can link a folder from this computer?",
  );
  if (!enable) {
    throw new Error("Computer folders must be enabled to link a folder during import.");
  }
  await localApi.saveHostFilesystemSettings({ enabled: true });
}

export function buildPluginLocalShareRegistration(
  share: PluginLocalSharePreflight,
  picked: PluginLocalSharePick,
  permission: "read" | "write",
): PluginLocalShareRegistration {
  const mountName = share.mountName.trim() || picked.suggestedName;
  return { mountId: picked.mountId, mountName, permission };
}

export async function preparePluginLocalShareImport(
  share: PluginLocalSharePreflight,
  picked: PluginLocalSharePick,
  permission: "read" | "write",
): Promise<PluginLocalShareRegistration> {
  await ensureComputerFoldersEnabled();
  return buildPluginLocalShareRegistration(share, picked, permission);
}
