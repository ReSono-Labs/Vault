// Developer-only visual fixture. No real identity, provider, database or tool call.
import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserVoiceApp } from "../src/browser-voice/BrowserVoiceApp";
import "../src/browser-voice/browser-voice.css";

if (!import.meta.env.DEV) throw new Error("Synthetic mobile fixture is development-only");
const title = "A long project session title with several decisions and follow-up notes";
const headers = Array.from({ length: 12 }, (_, i) => ({ conversationId: `synthetic-${i}`, title: `${title} ${i+1}`, historyVersion: 10, state: "open" }));
const longUrl = `https://example.invalid/${"long-path-segment-".repeat(16)}`;
const turns = Array.from({ length: 10 }, (_, i) => ({ turnId: `turn-${i}`, state: "completed", input: `Check the project notes and explain the next step ${i+1}.`,
  answer: `Here is the saved project context. This is synthetic text, not a model response.\n\nThe relevant notes should wrap neatly and remain readable on a narrow screen.\n\n${longUrl}\n\n• Review the last decision.\n• Confirm the current scope.\n• Keep the next action separate from preparation.` }));
window.fetch = async (input, options) => {
  const path = String(input);
  if (path.includes("/preparation") && (options?.method ?? "GET") !== "GET")
    return new Response("{}", { status: 202, headers: { "Content-Type": "application/json" } });
  if ((options?.method ?? "GET") !== "GET") throw new Error("This layout fixture refuses durable mutations");
  if (path.includes("/preparation?")) {
    const revision = Number(new URL(path,"http://fixture.invalid").searchParams.get("revision"));
    return new Response(JSON.stringify({revision,state:"ready",toolState:"proposed",
      memories:[{id:"synthetic-memory",text:"Synthetic project memory preview with a long description for mobile wrapping.",methods:["semantic"]}],
      tools:[{id:"synthetic-tool",description:"Synthetic proposed tool route, not an executed action.",kind:"catalog_proposal"}]}),
      {status:200,headers:{"Content-Type":"application/json"}});
  }
  if (path==="/live-memory") return new Response(JSON.stringify({enabled:true,epoch:0}),
    {status:200,headers:{"Content-Type":"application/json"}});
  const value = path === "/identity/status" ? { setupComplete: true } : path === "/me" ? { user: {
    userId: "synthetic-owner", username: "owner", displayName: "Test Owner", experienceStyle: "concise", isDeviceOwner: true,
    activeWorkspaceId: "synthetic-workspace", mustChangePassword: false, ageGroup: "adult", passwordMode: "user_managed",
  } } : path === "/conversations" ? { items: headers } : path.startsWith("/conversations/") ? { ...headers[0], turns } : { items: [] };
  return new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
};
createRoot(document.getElementById("root")!).render(<React.StrictMode><BrowserVoiceApp /></React.StrictMode>);

// Open the real navigation and history, not a copied Chat component layout.
const timer = window.setInterval(() => {
  const chat = document.querySelector<HTMLButtonElement>('.browser-voice-future-nav.is-mobile button[title="Chat"]')
    ?? document.querySelector<HTMLButtonElement>('.browser-voice-future-nav button[title="Chat"]');
  if (!chat) return;
  chat.click();
  const details = document.querySelector<HTMLDetailsElement>(".vault-chat-sessions details");
  if (details && !details.open) details.open = true;
  const session = document.querySelector<HTMLButtonElement>(".vault-chat-sessions details button");
  if (!session) return;
  session.click();
  window.clearInterval(timer);
  window.setTimeout(() => { document.documentElement.dataset.mobileReady = "true"; }, 250);
}, 50);
