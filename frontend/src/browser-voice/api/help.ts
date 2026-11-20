import { request } from "./request";

export type HelpMessage = { role: "user" | "assistant"; content: string };

export type HelpAnswer = {
  answer: string;
  providerKey: string;
  modelKey: string;
  sources: Array<{ label: string; kind: "guide" | "source" | "web"; url?: string }>;
  learned: boolean;
};

export const helpApi = {
  askHelp: (message: string, history: HelpMessage[], searchWeb: boolean) =>
    request<HelpAnswer>("/help/ask", {
      method: "POST",
      body: JSON.stringify({ message, history, searchWeb }),
    }),
};
