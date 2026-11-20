import { render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useChatViewport } from "./useChatViewport";

function Panel() {
  const ref = useChatViewport(true);
  return <section data-testid="panel" ref={ref} />;
}
const box = (top: number, height: number) => ({ top, height, bottom: top + height, left: 0, right: 0, width: 0, x: 0, y: top, toJSON: () => ({}) }) as DOMRect;
afterEach(() => { document.body.innerHTML = ""; vi.restoreAllMocks(); });

function layout(menuTop: number) {
  const menu = document.createElement("button");
  menu.className = "browser-voice-mobile-menu-trigger";
  document.body.append(menu);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return this === menu ? box(menuTop, 40) : box(92, 0);
  });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });
}

it("gives Chat the space below it when the Menu sits in the header above it", () => {
  layout(30);
  const { getByTestId } = render(<Panel />);
  expect(getByTestId("panel").style.height).toBe(`${800 - 20 - 92 - 12}px`);
});

it("stops Chat above a menu that sits below it", () => {
  layout(740);
  const { getByTestId } = render(<Panel />);
  expect(getByTestId("panel").style.height).toBe(`${740 - 92 - 12}px`);
});
