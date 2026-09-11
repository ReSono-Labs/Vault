import { blockingExtensionDiagnostics } from "@/browser-voice/extensionImportDiagnostics";
import { localApi, type LocalExtension } from "@/browser-voice/localApi";

export function mcpPackageRemoveMessage(item: Pick<LocalExtension, "displayName" | "configuration">): string {
  const hosted = item.configuration.packageType === "hosted";
  if (!hosted) {
    return `Remove ${item.displayName} from this Vault?`;
  }
  return (
    `Remove ${item.displayName}? Vault will stop the server and delete its package code, ` +
    "database, workspace files, settings, and tool grants from this Vault."
  );
}

export function mcpPackageRowSubtitle(item: LocalExtension): string {
  return item.state === "enabled" ? "On" : "Off";
}

export async function importMcpPackageFile(file: File): Promise<{ identity: string; message: string }> {
  const preview = await localApi.preflightMcpPackage(file);
  const blocked = blockingExtensionDiagnostics(preview.diagnostics);
  if (blocked.length) {
    throw new Error(blocked.join(" "));
  }
  const replacement = preview.replacement
    ? window.confirm(`${preview.identity} is installed. Replace it with this validated version?`)
    : true;
  if (!replacement) {
    return { identity: "", message: "" };
  }
  const replaceMigration = preview.migration?.requiresDecision
    ? window.confirm(
        `${preview.identity} already has package data on this Vault. Replace the imported database/workspace from this package?`,
      )
    : false;
  await localApi.confirmMcpPackage(preview.token, preview.replacement, replaceMigration);
  return {
    identity: preview.identity,
    message: `${preview.identity} imported. Open it to configure settings and grant tools.`,
  };
}
