import { describe, expect, it } from "vitest";
import { NO_STATUS_LABEL, statusLabel, statusOptions } from "@/lib/careerRecords";

describe("statusOptions", () => {
  it("offers the three initial statuses on create", () => {
    expect(statusOptions(undefined, true)).toEqual(["not_started", "scheduled", "completed"]);
  });
  it("offers the current status plus its allowed next states", () => {
    expect(statusOptions("completed", false)).toEqual(["completed", "follow_up_required"]);
    expect(statusOptions("follow_up_required", false)).toEqual(["follow_up_required", "scheduled", "completed"]);
  });
  it("offers only completed/follow-up for a legacy record", () => {
    expect(statusOptions(null, false)).toEqual(["completed", "follow_up_required"]);
  });
  it("labels a legacy record", () => {
    expect(statusLabel(null)).toBe(NO_STATUS_LABEL);
    expect(statusLabel("follow_up_required")).toBe("Follow-up Required");
  });
});
