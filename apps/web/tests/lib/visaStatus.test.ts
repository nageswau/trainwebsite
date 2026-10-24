import { describe, expect, it } from "vitest";

import { isVisaDecided, nextVisaStatuses, visaStatusLabel } from "@/lib/visaStatus";

// ccrm-026 (VC4): mirrors app/visa_status.can_move.
describe("visaStatus", () => {
  it("moves forward, with Withdrawn from any open status", () => {
    expect(nextVisaStatuses("not_started")).toEqual(["preparing", "appointment_booked", "submitted", "additional_info_requested", "decision_pending", "approved", "refused", "withdrawn"]);
    expect(nextVisaStatuses("submitted")).toEqual(["additional_info_requested", "decision_pending", "approved", "refused", "withdrawn"]);
  });

  it("allows Additional information requested and Decision pending both ways", () => {
    expect(nextVisaStatuses("decision_pending")).toEqual(["additional_info_requested", "approved", "refused", "withdrawn"]);
    expect(nextVisaStatuses("additional_info_requested")).toContain("decision_pending");
  });

  it("offers only the other decisions once decided", () => {
    expect(nextVisaStatuses("approved")).toEqual(["refused", "withdrawn"]);
    expect(isVisaDecided("refused")).toBe(true);
    expect(isVisaDecided("submitted")).toBe(false);
  });

  it("labels each status", () => {
    expect(visaStatusLabel("additional_info_requested")).toBe("Additional information requested");
    expect(visaStatusLabel(null)).toBe("");
  });
});
