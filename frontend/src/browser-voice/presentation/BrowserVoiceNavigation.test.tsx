import { expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { BrowserVoiceFutureNavigation } from "./BrowserVoiceIcons";

it("keeps mobile navigation closed until requested and closes after selection", () => {
  Object.defineProperty(HTMLDialogElement.prototype,"showModal",{configurable:true,value:function () { this.setAttribute("open", ""); }});
  Object.defineProperty(HTMLDialogElement.prototype,"close",{configurable:true,value:function () { this.removeAttribute("open"); }});
  const navigate=vi.fn();
  render(<BrowserVoiceFutureNavigation placement="mobile" onNavigate={navigate} />);
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Menu"}));
  const drawer=screen.getByRole("dialog",{name:"Navigation"});
  fireEvent.click(within(drawer).getByRole("button",{name:"Chat"}));
  expect(navigate).toHaveBeenCalledWith("chat");
  expect(screen.queryByRole("dialog")).toBeNull();
  vi.restoreAllMocks();
});
