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

type McpPackagePreflight = Awaited<ReturnType<typeof localApi.preflightMcpPackage>>;

export async function importMcpPackageFile(file: File): Promise<{ identity: string; message: string }> {
  return importMcpPackagePreview(await localApi.preflightMcpPackage(file));
}

export async function importMcpPackageFolder(grantId: string, path: string): Promise<{ identity: string; message: string }> {
  return importMcpPackagePreview(
    (await localApi.folderPreflight("mcp-package", grantId, path)) as McpPackagePreflight);
}

/** Decision record 2026-11-20: hosted code is trusted code until Vault confines it. */
export const HOSTED_CODE_WARNING =
  "This package runs its own program on this computer. It runs as trusted code with the same " +
  "access as Vault, including Vault's data and every workspace. Install it only if you trust " +
  "who made it. Continue?";

async function importMcpPackagePreview(preview: McpPackagePreflight): Promise<{ identity: string; message: string }> {
  const blocked = blockingExtensionDiagnostics(preview.diagnostics);
  if (blocked.length) {
    throw new Error(blocked.join(" "));
  }
  if (!window.confirm(`${preview.identity}: ${HOSTED_CODE_WARNING}`)) {
    return { identity: "", message: "" };
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
