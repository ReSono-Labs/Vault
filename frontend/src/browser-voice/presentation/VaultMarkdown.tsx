import type { ComponentPropsWithoutRef } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

// One Markdown renderer for Chat, Guides and Vault Help. Raw HTML stays literal text and
// react-markdown's default URL transform drops unsafe link schemes (javascript:, data: …).
export const REMARK_PLUGINS = [remarkGfm];

export const MARKDOWN_COMPONENTS = {
  a: ({ node: _node, ...props }: ComponentPropsWithoutRef<"a"> & { node?: unknown }) =>
    <a {...props} target="_blank" rel="noopener noreferrer" />,
  table: ({ node: _node, ...props }: ComponentPropsWithoutRef<"table"> & { node?: unknown }) =>
    <div className="vault-chat-table-wrap browser-voice-document-table-wrap"><table {...props} /></div>,
};

export function VaultMarkdown({ source }: { source: string }) {
  return <Markdown remarkPlugins={REMARK_PLUGINS} components={MARKDOWN_COMPONENTS}>{source}</Markdown>;
}

/** An href for a link Vault did not write itself (web search results): http(s) only. */
export function safeExternalHref(url: string | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}
