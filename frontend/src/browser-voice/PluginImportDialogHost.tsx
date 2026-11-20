import { useEffect, useState } from "react";
import { PluginLocalShareImportDialog } from "@/browser-voice/PluginLocalShareImportDialog";
import {
  getPendingPluginImport,
  notifyPluginImportComplete,
  setPendingPluginImport,
  subscribePendingPluginImport,
} from "@/browser-voice/pluginImportUi";

export function PluginImportDialogHost() {
  const [pending, setPending] = useState(getPendingPluginImport());

  useEffect(() => subscribePendingPluginImport(setPending), []);

  if (!pending) {
    return null;
  }

  return (
    <PluginLocalShareImportDialog
      onClose={() => setPendingPluginImport(null)}
      onComplete={async (result) => {
        setPendingPluginImport(null);
        await notifyPluginImportComplete(result);
      }}
      pending={pending}
    />
  );
}
