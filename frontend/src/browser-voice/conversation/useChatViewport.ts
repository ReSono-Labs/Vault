import { useEffect, useRef } from "react";

// Presentation only: reserve the actual existing mobile nav/visual viewport,
// without hardcoding its row count or owning the Voice/navigation lifecycle.
export function useChatViewport(active: boolean) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const panel = ref.current;
    if (!active || !panel) return;
    const nav = document.querySelector<HTMLElement>(".browser-voice-mobile-menu-trigger");
    const header = document.querySelector<HTMLElement>(".browser-voice-header");
    const update = () => {
      const viewport = window.visualViewport;
      const bottom = (viewport?.offsetTop ?? 0) + (viewport?.height ?? window.innerHeight);
      const top = panel.getBoundingClientRect().top;
      const navRect = nav?.getBoundingClientRect();
      // The Menu now sits in the header above Chat; only a menu below the panel takes room from it.
      const navBelow = navRect && navRect.height > 0 && navRect.top > top;
      const available = Math.max(0, Math.min(bottom, navBelow ? navRect.top : bottom - 20) - top - 12);
      panel.style.height = `${available}px`;
    };
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    if (nav) observer?.observe(nav);
    if (header) observer?.observe(header);
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    update();
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, [active]);
  return ref;
}
