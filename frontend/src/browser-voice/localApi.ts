/** The Vault API client. One module per area (api/*.ts), matching the backend route modules; this object stays the public import. */
export { request } from "./api/request";
export type { A2AConnection, A2ANotification } from "./api/agentNetwork";
export type { BackgroundRun, VaultTask } from "./api/background";
export type { CalendarAccount } from "./api/calendar";
export type { CommandSettings, PendingCommand } from "./api/commands";
export type { LocalExtension, LocalTool, ExtensionGrant, BuiltinPlugin } from "./api/extensions";
export type { ExternalMemoryIntegration, ExternalMemoryPairing } from "./api/externalMemory";
export type { FolderPermission, FolderStatus, UserFolder, FolderList, FolderPlace, FolderBrowse, FolderLocations, FolderAccess } from "./api/folders";
export type { HelpMessage, HelpAnswer } from "./api/help";
export type { LocalUser, LocalWorkspace, PasswordMode, ManagedLocalUser, ProvisionedLocalUser } from "./api/identity";
export type { MailAccount } from "./api/mail";
export type { VaultNotification } from "./api/notifications";
export type { VoiceProviderStatus, AIProviderCatalog, AccountProviderAccess } from "./api/providers";
export type { WorkspaceFileEntry, WorkspaceFileDirectoryResponse, WorkspaceFileReadResponse, WorkspaceFileMutationResponse, WorkspaceFolderShare } from "./api/workspaceFiles";
import { helpApi } from "./api/help";
import { identityApi } from "./api/identity";
import { extensionsApi } from "./api/extensions";
import { backgroundApi } from "./api/background";
import { providersApi } from "./api/providers";
import { mailApi } from "./api/mail";
import { calendarApi } from "./api/calendar";
import { externalMemoryApi } from "./api/externalMemory";
import { linkCompanionApi } from "./api/linkCompanion";
import { commandsApi } from "./api/commands";
import { foldersApi } from "./api/folders";
import { agentNetworkApi } from "./api/agentNetwork";
import { notificationsApi } from "./api/notifications";
import { voiceApi } from "./api/voice";
import { workspaceFilesApi } from "./api/workspaceFiles";

export const localApi = {
  ...helpApi,
  ...identityApi,
  ...extensionsApi,
  ...backgroundApi,
  ...providersApi,
  ...mailApi,
  ...calendarApi,
  ...externalMemoryApi,
  ...linkCompanionApi,
  ...commandsApi,
  ...foldersApi,
  ...agentNetworkApi,
  ...notificationsApi,
  ...voiceApi,
  ...workspaceFilesApi,
};
