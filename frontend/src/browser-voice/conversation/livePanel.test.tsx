import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { LivePreparationPanel } from "./LivePreparationPanel";
import { setLivePanelShown } from "./livePanel";
import type { Preparation } from "./api";

const value = { state: "ready", memories: [], tools: [], toolState: "no_tool" } as unknown as Preparation;
afterEach(() => localStorage.clear());

it("hides and shows each surface's live window independently without touching its data", () => {
  render(<><LivePreparationPanel value={value} surface="chat" /><LivePreparationPanel value={value} surface="voice" /></>);
  expect(screen.getAllByLabelText("Live preparation")).toHaveLength(2);
  act(() => setLivePanelShown("voice", false));
  expect(screen.getAllByLabelText("Live preparation")).toHaveLength(1);
  act(() => setLivePanelShown("chat", false));
  expect(screen.queryByLabelText("Live preparation")).toBeNull();
  act(() => { setLivePanelShown("chat", true); setLivePanelShown("voice", true); });
  expect(screen.getAllByLabelText("Live preparation")).toHaveLength(2);
});
