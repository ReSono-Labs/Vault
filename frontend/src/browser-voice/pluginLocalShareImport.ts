/** What a plugin package asks for in its localShare block (from preflight). */
export type PluginLocalSharePreflight = {
  mountName: string;
  permission: "read" | "write";
  label: string;
  required: boolean;
  permissionChoices: Array<"read" | "write">;
};

/** The user's folder chosen for the plugin. */
export type PluginLocalShareRegistration = {
  folderId: string;
  /** True when the folder was added in the import dialog; it is removed again if the import fails. */
  createdDuringImport: boolean;
};
