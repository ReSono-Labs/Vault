import { blockingExtensionDiagnostics } from "@/browser-voice/extensionImportDiagnostics";
import { localApi } from "@/browser-voice/localApi";
import {
  preparePluginLocalShareImport,
  type PluginLocalSharePreflight,
  type PluginLocalSharePick,
  type PluginLocalShareRegistration,
} from "@/browser-voice/pluginLocalShareImport";

type PluginPreflight = {
  token: string;
  identity: string;
  replacement: boolean;
  diagnostics?: string[];
  migration?: {
    requiresDecision: boolean;
  };
  workspaceImport?: {
    requiresDecision: boolean;
    conflicts?: string[];
  };
  localShare?: PluginLocalSharePreflight;
};

export type PendingPluginImport = {
  preview: PluginPreflight;
  replaceMigration: boolean;
  replaceWorkspaceImport: boolean;
  share: PluginLocalSharePreflight;
};

export type PluginImportOutcome =
  | { kind: "complete"; identity: string; message: string }
  | { kind: "cancelled" }
  | { kind: "needs_local_share"; pending: PendingPluginImport };

export function pluginRemoveMessage(
  item: { displayName: string; configuration: Record<string, unknown> },
): string {
  if (item.configuration.packageData) {
    return (
      `Remove ${item.displayName}? Vault will delete the plugin, its package data ` +
      "(database and workspace files), settings, and grants from this Vault."
    );
  }
  return `Remove ${item.displayName} from this Vault?`;
}

async function confirmPluginImport(
  preview: PluginPreflight,
  replaceMigration: boolean,
  replaceWorkspaceImport: boolean,
  localShareRegistration: PluginLocalShareRegistration | null,
): Promise<{ identity: string; message: string }> {
  await localApi.confirmExtension(
    "plugin",
    preview.token,
    preview.replacement,
    replaceMigration,
    localShareRegistration,
    replaceWorkspaceImport,
  );
  return {
    identity: preview.identity,
    message: `${preview.identity} imported. Open it under Plugins to configure settings and grant skills.`,
  };
}

export async function importPluginFile(file: File): Promise<PluginImportOutcome> {
  const preview = (await localApi.preflight("plugin", file)) as PluginPreflight;
  const blocked = blockingExtensionDiagnostics(preview.diagnostics);
  if (blocked.length) {
    throw new Error(blocked.join(" "));
  }
  const replacement = preview.replacement
    ? window.confirm(`${preview.identity} is installed. Replace it with this validated version?`)
    : true;
  if (!replacement) {
    return { kind: "cancelled" };
  }
  const replaceMigration = preview.migration?.requiresDecision
    ? window.confirm(
        `${preview.identity} already has package data on this Vault. Replace the imported database/workspace from this package?`,
      )
    : false;
  const replaceWorkspaceImport = preview.workspaceImport?.requiresDecision
    ? window.confirm(
        `${preview.identity} would overwrite existing Vault workspace paths` +
          (preview.workspaceImport.conflicts?.length
            ? ` (${preview.workspaceImport.conflicts.join(", ")})`
            : "") +
          `. Import these workspace files from the package?`,
      )
    : false;

  if (preview.localShare) {
    return {
      kind: "needs_local_share",
      pending: {
        preview,
        replaceMigration,
        replaceWorkspaceImport,
        share: preview.localShare,
      },
    };
  }

  const result = await confirmPluginImport(preview, replaceMigration, replaceWorkspaceImport, null);
  return { kind: "complete", ...result };
}

export async function completePluginImportWithLocalShare(
  pending: PendingPluginImport,
  picked: PluginLocalSharePick,
  permission: "read" | "write",
): Promise<{ identity: string; message: string }> {
  const localShareRegistration = await preparePluginLocalShareImport(pending.share, picked, permission);
  return confirmPluginImport(
    pending.preview,
    pending.replaceMigration,
    pending.replaceWorkspaceImport,
    localShareRegistration,
  );
}

export async function completePluginImportWithoutLocalShare(
  pending: PendingPluginImport,
): Promise<{ identity: string; message: string }> {
  if (pending.share.required) {
    throw new Error("This plugin requires linking a local folder on import.");
  }
  const result = await confirmPluginImport(
    pending.preview,
    pending.replaceMigration,
    pending.replaceWorkspaceImport,
    null,
  );
  return result;
}
