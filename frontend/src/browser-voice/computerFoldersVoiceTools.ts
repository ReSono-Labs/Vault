import {
  browserLinkedMountForPath,
  listBrowserLocalDirectory,
  readBrowserLocalFile,
  searchBrowserLocalFiles,
} from "@/browser-voice/computerFoldersWorkspace";
import { localApi, type HostFilesystemMount } from "@/browser-voice/localApi";
import { normalizeWorkspaceToolArguments, workspaceToolPath } from "@/browser-voice/workspaceToolArguments";

const WORKSPACE_BROWSER_TOOLS = new Set([
  "workspace_list_directory",
  "workspace_read_file",
  "workspace_search_files",
]);

type VoiceToolResult = {
  content: Array<{ type: "text"; text: string }>;
  isError: boolean;
  structuredContent?: Record<string, unknown>;
  resonoSessionUpdate?: Record<string, unknown>;
};

function mcpResult(payload: Record<string, unknown>, isError = false): VoiceToolResult {
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    isError,
    structuredContent: payload,
  };
}

function toolPath(name: string, args: Record<string, unknown>): string {
  return workspaceToolPath(name, args);
}

export function shouldFulfillBrowserLocalVoiceTool(
  name: string,
  args: Record<string, unknown>,
  mounts: HostFilesystemMount[],
): boolean {
  if (!WORKSPACE_BROWSER_TOOLS.has(name)) {
    return false;
  }
  const path = toolPath(name, args);
  if (name === "workspace_search_files") {
    if (path === "shared" || path.startsWith("shared/")) {
      return false;
    }
    if (!path || path === "local") {
      return false;
    }
  }
  return browserLinkedMountForPath(path, mounts) !== null;
}

export async function fulfillBrowserLocalVoiceTool(
  name: string,
  args: Record<string, unknown>,
  mounts: HostFilesystemMount[],
): Promise<VoiceToolResult> {
  const normalized = normalizeWorkspaceToolArguments(name, args);
  try {
    if (name === "workspace_list_directory") {
      const directory = String(normalized.directory || "").trim();
      const listing = await listBrowserLocalDirectory(directory, mounts);
      return mcpResult({
        ...listing,
        pathArea: "local",
        browserLinked: true,
      });
    }
    if (name === "workspace_read_file") {
      const fileKey = String(normalized.fileKey || "").trim();
      const readBack = await readBrowserLocalFile(fileKey, mounts);
      return mcpResult({
        ...readBack,
        pathArea: "local",
        browserLinked: true,
      });
    }
    const payload = await searchBrowserLocalFiles(
      String(normalized.query || ""),
      String(normalized.directory || ""),
      mounts,
      Number(normalized.limit || 25) || 25,
    );
    return mcpResult({ ...payload, browserLinked: true });
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : "Linked folder could not be read in this browser.";
    return mcpResult({ error: message, pathArea: "local" }, true);
  }
}

export async function overlayLiveBrowserLocalSearch(
  name: string,
  args: Record<string, unknown>,
  result: VoiceToolResult,
): Promise<VoiceToolResult> {
  if (name !== "workspace_search_files" || result.isError) {
    return result;
  }
  const directory = workspaceToolPath(name, args);
  if (directory === "shared" || directory.startsWith("shared/")) {
    return result;
  }
  if (directory && directory !== "local" && !directory.startsWith("local/")) {
    return result;
  }
  const mounts = (await localApi.hostFilesystemMounts()).items.filter((mount) => mount.source !== "helper");
  if (!mounts.length || browserLinkedMountForPath(directory, mounts)) {
    return result;
  }
  const extra = await searchBrowserLocalFiles(
    String(args.query || ""),
    directory === "local" ? "local" : "",
    mounts,
    Number(args.limit || 25) || 25,
  );
  const structured = { ...(result.structuredContent || {}) };
  const existing = Array.isArray(structured.matches) ? structured.matches : [];
  const seen = new Set(existing.map((item) => String((item as { fileKey?: string }).fileKey || "")));
  const merged = [...existing];
  for (const match of extra.matches) {
    if (seen.has(match.fileKey)) {
      continue;
    }
    merged.push(match);
  }
  const payload = {
    ...structured,
    matches: merged,
    matchCount: merged.length,
  };
  return mcpResult(payload);
}

export async function tryFulfillBrowserLocalVoiceTool(
  name: string,
  args: Record<string, unknown>,
): Promise<VoiceToolResult | null> {
  if (!WORKSPACE_BROWSER_TOOLS.has(name)) {
    return null;
  }
  const mounts = (await localApi.hostFilesystemMounts()).items;
  if (!shouldFulfillBrowserLocalVoiceTool(name, args, mounts)) {
    return null;
  }
  return fulfillBrowserLocalVoiceTool(name, args, mounts);
}
