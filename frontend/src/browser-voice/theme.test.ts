import { afterEach, expect, it } from "vitest";
import { applyTheme, setTheme, storedTheme, THEME_KEY } from "./theme";

afterEach(() => { localStorage.clear(); document.documentElement.removeAttribute("data-theme"); });

it("defaults to Midnight and persists Aurora on the root element", () => {
  expect(storedTheme()).toBe("midnight");
  setTheme("aurora");
  expect(localStorage.getItem(THEME_KEY)).toBe("aurora");
  expect(document.documentElement.getAttribute("data-theme")).toBe("aurora");
  expect(storedTheme()).toBe("aurora");
  applyTheme("midnight");
  expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
});
