import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useLivePreparation } from "./useLivePreparation";

const api = vi.hoisted(() => ({ prepare: vi.fn(), preparation: vi.fn(), discardPreparation: vi.fn() }));
vi.mock("./api", () => ({ conversationApi: api }));
const ready = (revision: number, text: string) => ({ revision, state: "ready", toolState: "proposed",
  memories: [{ id: "m", text, methods: ["semantic"] }], tools: [{ id: "contacts", description: "Contacts lookup", kind: "catalog_proposal" }] });
beforeEach(() => {
  vi.clearAllMocks(); api.prepare.mockResolvedValue({}); api.discardPreparation.mockResolvedValue({});
  api.preparation.mockImplementation((_id, _utterance, revision) => Promise.resolve(ready(revision, "Current memory")));
});

it("keeps the box while typing; empty input and Send hide it and fence late replies", async () => {
  const ensure = vi.fn().mockResolvedValue("c");
  const view = renderHook(({ draft }) => useLivePreparation(true, draft, "c", ensure),
    { initialProps: { draft: "Find my contacts" } });
  await waitFor(() => expect(view.result.current.value?.state).toBe("ready"));
  let late!: (value: unknown) => void;
  api.preparation.mockImplementationOnce(() => new Promise(resolve => { late = resolve; }));
  view.rerender({ draft: "Find my invoices" });
  expect(view.result.current.value?.memories[0].text).toBe("Current memory");  // no flicker between edits
  await waitFor(() => expect(api.prepare).toHaveBeenCalledTimes(2));
  expect(api.prepare.mock.calls.every(call => call.length === 2)).toBe(true);  // uploads are never cancelled
  await waitFor(() => expect(late).toBeTypeOf("function"));
  act(() => view.result.current.clear());
  expect(view.result.current.value).toBeNull();
  await act(async () => late(ready(2, "Discarded memory")));
  expect(view.result.current.value).toBeNull();
  expect(api.discardPreparation).toHaveBeenCalled();
  view.rerender({ draft: "Find my calendar" });
  await waitFor(() => expect(view.result.current.value?.state).toBe("ready"));
  view.rerender({ draft: "" });
  expect(view.result.current.value).toBeNull();
  await waitFor(() => expect(api.prepare.mock.calls.at(-1)?.[1].text).toBe(""));
  expect(ensure).not.toHaveBeenCalled();
});

it("keeps the box during composition, tears down scoped observers and reports unavailable without inventing routes", async () => {
  const ensure = vi.fn().mockResolvedValue("c");
  const view = renderHook(({ active }) => useLivePreparation(active, "Find my contacts", "c", ensure),
    { initialProps: { active: true } });
  await waitFor(() => expect(view.result.current.value?.state).toBe("ready"));
  act(() => view.result.current.setComposing(true));
  expect(view.result.current.value?.state).toBe("ready");
  await waitFor(() => expect(api.prepare.mock.calls.at(-1)?.[1].composing).toBe(true));
  api.prepare.mockRejectedValueOnce(new Error("Provider unavailable"));
  act(() => view.result.current.setComposing(false));
  await waitFor(() => expect(view.result.current.value?.state).toBe("unavailable"));
  expect(view.result.current.value?.tools).toEqual([]);
  view.rerender({ active: false });
  expect(view.result.current.value).toBeNull();
  expect(api.discardPreparation).toHaveBeenCalled();
});
