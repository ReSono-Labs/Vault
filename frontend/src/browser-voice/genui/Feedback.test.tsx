import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AnswerFeedback, FeedbackExport, PresentationNoticeCard } from "./Feedback";

const genui = vi.hoisted(() => ({ feedback: vi.fn(), alternatives: vi.fn(), choose: vi.fn(), keep: vi.fn(), undo: vi.fn(),
  exportFeedback: vi.fn() }));
vi.mock("@/browser-voice/conversation/api", () => ({ genuiApi: genui }));
const headlines = { version: 1, layout: "headlines", fallbackText: "News", items: [{ title: "Model A ships", source: "Verge" }] };
const table = { version: 1, layout: "table", fallbackText: "News", columns: ["Story"], rows: [["Model A ships"]] };

beforeEach(() => {
  vi.clearAllMocks();
  genui.feedback.mockImplementation((_c: string, _t: string, verdict: string | null) => Promise.resolve({ verdict, chosenLayout: null, hasPreviews: false, shown: ["text"] }));
  genui.alternatives.mockResolvedValue({ current: { layout: "text", card: null, text: "Plain answer" },
    previews: [{ layout: "headlines", card: headlines }, { layout: "table", card: table }] });
  genui.choose.mockResolvedValue({ verdict: "down", chosenLayout: "table", hasPreviews: true, shown: ["text"] });
});

it("thumbs down opens the carousel; arrows and swipe change format; the checkbox records the choice", async () => {
  const changed = vi.fn();
  render(<AnswerFeedback conversationId="c" turnId="t" onPresentationChanged={changed} />);
  fireEvent.click(screen.getByRole("button", { name: "Could be better" }));
  await waitFor(() => expect(genui.feedback).toHaveBeenCalledWith("c", "t", "down"));
  expect(await screen.findByText("Model A ships")).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "1 of 2: Headlines" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next format" }));
  expect(screen.getByRole("group", { name: "2 of 2: Table" })).toBeInTheDocument();
  const stage = screen.getByRole("group", { name: "2 of 2: Table" }).parentElement!;
  fireEvent.touchStart(stage, { touches: [{ clientX: 200 }] });
  fireEvent.touchEnd(stage, { changedTouches: [{ clientX: 100 }] });
  expect(screen.getByRole("group", { name: "1 of 2: Headlines" })).toBeInTheDocument();
  fireEvent.keyDown(stage, { key: "ArrowLeft" });
  fireEvent.click(screen.getByRole("checkbox"));
  await waitFor(() => expect(genui.choose).toHaveBeenCalledWith("c", "t", "table"));
  expect(await screen.findByText(/Table it is/)).toBeInTheDocument();
  expect(changed).toHaveBeenCalled();
});

it("thumbs up toggles without opening previews", async () => {
  render(<AnswerFeedback conversationId="c" turnId="t" />);
  fireEvent.click(screen.getByRole("button", { name: "Good answer" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Good answer" })).toHaveAttribute("aria-pressed", "true"));
  expect(genui.alternatives).not.toHaveBeenCalled();
});

it("tuner notice shows the change and an example, with Keep and Undo", async () => {
  const done = vi.fn();
  genui.undo.mockResolvedValue({ version: 0, config: {}, notice: null, noticePending: false });
  render(<PresentationNoticeCard onDone={done} state={{ version: 1, config: {}, noticePending: true, notice: {
    summary: "I'll show news as headlines from now on.", layout: "headlines", replaced: "text", events: 5, share: 1,
    example: headlines as never, version: 1 } }} />);
  expect(screen.getByText("I'll show news as headlines from now on.")).toBeInTheDocument();
  expect(screen.getByText("Model A ships")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(genui.undo).toHaveBeenCalledWith(1));
  expect(done).toHaveBeenCalled();
});

it("export previews without request text until opted in", async () => {
  genui.exportFeedback.mockImplementation((text: boolean) => Promise.resolve({ format: "resono-vault-genui-feedback",
    items: [{ item: 1, chosenLayout: "headlines", ...(text ? { request: "Top AI news" } : {}) }] }));
  render(<FeedbackExport />);
  expect(await screen.findByLabelText("Export preview")).not.toHaveTextContent("Top AI news");
  fireEvent.click(screen.getByRole("checkbox", { name: "Include my request text" }));
  await waitFor(() => expect(screen.getByLabelText("Export preview")).toHaveTextContent("Top AI news"));
  expect(genui.exportFeedback).toHaveBeenLastCalledWith(true);
  expect(screen.getByRole("button", { name: "Download 1 item" })).toBeEnabled();
});
