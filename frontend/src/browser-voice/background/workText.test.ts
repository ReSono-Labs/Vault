import { expect, it } from "vitest";
import { scheduleText, shortTitle, stopReason, workStatusText } from "./workText";

it("shortens an instruction to its first sentence", () => {
  expect(shortTitle("Every morning, run the UAP watch. Then refresh the cards.")).toBe("Every morning, run the UAP watch.");
  expect(shortTitle("No full stop here")).toBe("No full stop here");
  expect(shortTitle("Fetch current U.S. market headlines. Then refresh.")).toBe("Fetch current U.S. market headlines.");
  expect(shortTitle("x".repeat(200)).length).toBe(140);
});

it("describes schedules in plain words", () => {
  expect(scheduleText({ kind: "cron", cron: "0 8 * * *" })).toBe("Every day at 8:00 AM");
  expect(scheduleText({ kind: "cron", cron: "30 12 * * 1-5" })).toBe("Weekdays at 12:30 PM");
  expect(scheduleText({ kind: "cron", cron: "0 16 * * 5" })).toBe("Fridays at 4:00 PM");
  expect(scheduleText({ kind: "cron", cron: "30 7 * * 1,4" })).toBe("Mon, Thu at 7:30 AM");
  expect(scheduleText({ kind: "cron", cron: "*/15 * * * *" })).toBe("Schedule: */15 * * * *");
  expect(scheduleText({ kind: "once", run_at: "not a date" })).toBe("Once");
});

it("explains why a run stopped without raw codes", () => {
  expect(stopReason("unknown", "stalled_outcome_unknown")).toMatch(/lost track/);
  expect(stopReason("failed", "validationerror")).toMatch(/format/);
  expect(stopReason("cancelled", null)).toBe("You stopped it.");
  expect(stopReason("completed", null)).toBeNull();
  expect(stopReason("failed", "something_new")).toBe("It stopped with an error (something_new).");
  expect(workStatusText("waiting_approval")).toBe("Waiting for your approval");
  expect(workStatusText("unknown")).toBe("Outcome not confirmed");
});
