/** Per-browser display preference for the live preparation window. Display-only: the live
 *  memory/tool stream keeps running either way; this only decides whether the panel is drawn. */
export type LiveSurface = "chat" | "voice";
const key = (surface: LiveSurface) => `resono_vault_live_panel_${surface}`;
export const LIVE_PANEL_EVENT = "vault-live-panel";

export function livePanelShown(surface: LiveSurface): boolean {
  try { return localStorage.getItem(key(surface)) !== "hidden"; } catch { return true; }
}

export function setLivePanelShown(surface: LiveSurface, shown: boolean): void {
  try { localStorage.setItem(key(surface), shown ? "shown" : "hidden"); } catch { /* storage unavailable */ }
  window.dispatchEvent(new Event(LIVE_PANEL_EVENT));
}
