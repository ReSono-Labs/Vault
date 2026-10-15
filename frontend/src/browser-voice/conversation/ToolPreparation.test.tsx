import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ToolPreparation } from "./ToolPreparation";

it("shows learned applicability without raw JSON or executing untrusted markup", () => {
  render(<ToolPreparation tool={{ kind: "learned_rule", description: JSON.stringify({
    description: "<script>contact lookup</script>", conditions: { all: ["User requests contact lookup"] },
    required_slots: ["query"], exclusions: ["No modifications"],
  }) }} />);
  expect(screen.getByText("<script>contact lookup</script>")).toBeInTheDocument();
  expect(screen.getByText("Learned read-only rule")).toBeInTheDocument();
  expect(screen.getByText("When: User requests contact lookup")).toBeInTheDocument();
  expect(screen.getByText("Needs: query")).toBeInTheDocument();
  expect(screen.getByText("Excludes: No modifications")).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
});

it("retains plain catalog and malformed future descriptions", () => {
  const view = render(<ToolPreparation tool={{ kind: "catalog_proposal", description: "Contacts search" }} />);
  expect(screen.getByText("Catalog proposal")).toBeInTheDocument();
  view.rerender(<ToolPreparation tool={{ kind: "learned_rule", description: "Not JSON" }} />);
  expect(screen.getByText("Not JSON")).toBeInTheDocument();
});
