import { request } from "./request";

export type MailAccount = {
  mailboxAccountId: string;
  mailboxRole: "normal_email" | "agent_mail";
  emailAddress: string;
  displayName: string | null;
  lifecycleStatus: "active" | "disabled" | "disconnected" | "removed";
  syncEnabled: boolean;
  syncStatus: string;
};

export const mailApi = {
  mailAccounts: () => request<{ items: MailAccount[] }>("/mail/accounts"),
  agentMailAccounts: () => request<{ items: MailAccount[] }>("/mail/agent-accounts"),
  connectMail: (value: {
    displayName?: string;
    credentials: {
      emailAddress: string;
      imap: {
        host: string;
        port: number;
        username: string;
        password: string;
        useTls: true;
      };
      smtp: {
        host: string;
        port: number;
        username: string;
        password: string;
        useTls: true;
      };
    };
    validateConnection: boolean;
  }) =>
    request<MailAccount>("/mail/accounts", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  connectAgentMail: (value: {
    displayName?: string;
    credentials: { emailAddress: string; imap: { host: string; port: number; username: string; password: string; useTls: true }; smtp: { host: string; port: number; username: string; password: string; useTls: true } };
    validateConnection: boolean;
  }) => request<MailAccount>("/mail/agent-accounts", { method: "POST", body: JSON.stringify(value) }),
};
