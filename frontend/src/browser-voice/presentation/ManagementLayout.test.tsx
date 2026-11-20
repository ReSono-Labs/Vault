import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { TabPanel, Tabs } from "./ManagementLayout";
import { SettingsPanel } from "@/browser-voice/SettingsPanel";

function Harness() {
  const [value, setValue] = useState<"a" | "b" | "c">("a");
  return <>
    <Tabs idPrefix="t" label="Sections" onChange={setValue} tabs={[{ id: "a", label: "Alpha" }, { id: "b", label: "Beta" }, { id: "c", label: "Gamma" }]} value={value} />
    <TabPanel id={value} idPrefix="t"><p>{value} panel</p></TabPanel>
  </>;
}

it("links tabs to their panel and moves with arrow, Home and End keys", () => {
  render(<Harness />);
  const alpha = screen.getByRole("tab", { name: "Alpha" });
  expect(alpha).toHaveAttribute("aria-selected", "true");
  expect(alpha).toHaveAttribute("tabindex", "0");
  expect(screen.getByRole("tab", { name: "Beta" })).toHaveAttribute("tabindex", "-1");
  expect(screen.getByRole("tabpanel", { name: "Alpha" })).toHaveTextContent("a panel");
  fireEvent.keyDown(alpha, { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "Beta" })).toHaveFocus();
  expect(screen.getByRole("tabpanel", { name: "Beta" })).toHaveTextContent("b panel");
  fireEvent.keyDown(screen.getByRole("tab", { name: "Beta" }), { key: "End" });
  expect(screen.getByRole("tab", { name: "Gamma" })).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(screen.getByRole("tab", { name: "Gamma" }), { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "Alpha" })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole("tab", { name: "Alpha" }), { key: "ArrowLeft" });
  expect(screen.getByRole("tab", { name: "Gamma" })).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(screen.getByRole("tab", { name: "Gamma" }), { key: "Home" });
  expect(screen.getByRole("tab", { name: "Alpha" })).toHaveAttribute("aria-selected", "true");
  // The narrow-screen selector makes the same choice.
  fireEvent.change(screen.getByRole("combobox", { name: "Sections" }), { target: { value: "b" } });
  expect(screen.getByRole("tab", { name: "Beta" })).toHaveAttribute("aria-selected", "true");
});

function json(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }));
}
afterEach(() => vi.unstubAllGlobals());

it("splits Settings into Display, Folders, Commands and Background assistant, hiding unavailable areas", async () => {
  let foldersAvailable = false;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/folders") return json({ available: foldersAvailable, hasAccess: true, canAddAnywhere: true, folders: [] });
    if (path === "/commands/settings") return json({ available: true, enabled: false });
    if (path.startsWith("/background/preferences")) return json({ enabled: false, quietHours: {} });
    if (path.startsWith("/background")) return json({ items: [] });
    return json({}, 404);
  }));
  const view = render(<SettingsPanel isAdmin />);
  expect(await screen.findByRole("tab", { name: "Commands" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "Folders" })).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Display", selected: true })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 3, name: "Appearance" })).toBeInTheDocument();
  expect(screen.getAllByText("Applies to this browser.")).toHaveLength(1);
  fireEvent.click(screen.getByRole("tab", { name: "Background assistant" }));
  expect(await screen.findByRole("heading", { level: 3, name: "Observation and quiet hours" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 3, name: "Specialist roles" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 3, name: "Routines" })).toBeInTheDocument();
  view.unmount();
  foldersAvailable = true;
  render(<SettingsPanel isAdmin />);
  expect(await screen.findByRole("tab", { name: "Folders" })).toBeInTheDocument();
});
