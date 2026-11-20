/** True while the browser tab is hidden (another tab, minimized window, locked phone). */
export function pageHidden() {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

/** Wrap a polling tick so it is skipped while the page is hidden; the next visible tick refreshes. */
export function whenVisible(tick: () => void) {
  return () => {
    if (!pageHidden()) tick();
  };
}
