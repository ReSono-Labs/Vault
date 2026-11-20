import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { safeExternalHref, VaultMarkdown } from "./VaultMarkdown";

describe("VaultMarkdown", () => {
  it("drops unsafe link schemes from model-written Markdown (SEC-03)", () => {
    const { container } = render(<VaultMarkdown source={"[click](javascript:alert(1)) and [ok](https://example.com)"} />);
    const hrefs = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href") ?? "");
    expect(hrefs.some((href) => href.toLowerCase().startsWith("javascript:"))).toBe(false);
    expect(screen.getByText("ok").getAttribute("href")).toBe("https://example.com");
  });

  it("renders tables, lists and code like the old Guides renderer", () => {
    const { container } = render(<VaultMarkdown source={"### Steps\n\n1. One\n2. Two\n\n| A | B |\n|---|---|\n| x | `y` |\n\n```\ncode\n```"} />);
    expect(container.querySelector("h3")?.textContent).toBe("Steps");
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(container.querySelector(".browser-voice-document-table-wrap table td code")?.textContent).toBe("y");
    expect(container.querySelector("pre code")?.textContent).toContain("code");
  });

  it("allows only http(s) for web source links", () => {
    expect(safeExternalHref("javascript:alert(1)")).toBeUndefined();
    expect(safeExternalHref("data:text/html,x")).toBeUndefined();
    expect(safeExternalHref("https://example.com/a")).toBe("https://example.com/a");
    expect(safeExternalHref(undefined)).toBeUndefined();
  });
});
