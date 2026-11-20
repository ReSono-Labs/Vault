/** Diagnostics that should block import confirm; review and partial skill/MCP issues do not. */
export function blockingExtensionDiagnostics(diagnostics: string[] | undefined): string[] {
  if (!diagnostics?.length) {
    return [];
  }
  return diagnostics.filter((item) => {
    if (item.startsWith("review:")) {
      return false;
    }
    if (item.startsWith("skill:")) {
      return false;
    }
    if (item.startsWith("mcp:")) {
      return false;
    }
    if (item.includes("unknown top-level field")) {
      return false;
    }
    return true;
  });
}
