/** App appearance: "midnight" (dark, default) or "aurora" (light). Stored per browser. */
export type VaultTheme = "midnight" | "aurora";
export const THEME_KEY = "resono_vault_theme";
const META = { midnight: "#0c1630", aurora: "#f4f0ea" } as const;

export function storedTheme(): VaultTheme {
  try { return localStorage.getItem(THEME_KEY) === "aurora" ? "aurora" : "midnight"; } catch { return "midnight"; }
}

export function applyTheme(theme: VaultTheme) {
  const root = document.documentElement;
  if (theme === "aurora") root.setAttribute("data-theme", "aurora"); else root.removeAttribute("data-theme");
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", META[theme]);
}

export function setTheme(theme: VaultTheme) {
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* private mode: applies for this page only */ }
  applyTheme(theme);
  window.dispatchEvent(new CustomEvent("vault-theme", { detail: theme }));
}
