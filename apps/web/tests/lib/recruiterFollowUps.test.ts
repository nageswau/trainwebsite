import { describe, expect, it } from "vitest";

import { followUpsUrl, isFollowUpListPage, REASONS, reasonLabel } from "@/lib/recruiterFollowUps";

// rec-024 (FU10, FU2): the §18 reasons in source order and the list URL.
describe("recruiterFollowUps (rec-024)", () => {
  it("has the nine EVID-018 §18 reasons in source order", () => {
    expect(REASONS.map((r) => r.label)).toEqual([
      "Follow-up for new requirement", "Follow-up for JD", "Follow-up for profile feedback", "Interview feedback", "Offer status",
      "Joining confirmation", "New openings", "Contract/MoU", "Payment/commercial discussion",
    ]);
    expect(reasonLabel("contract_mou")).toBe("Contract/MoU");
    expect(reasonLabel("unknown")).toBe("unknown");
  });

  it("builds the list URL and recognises a list page", () => {
    expect(followUpsUrl("upcoming", 50)).toBe("/api/v1/recruiter/follow-ups?due=upcoming&limit=50&offset=50");
    expect(isFollowUpListPage({ items: [], total: 0, limit: 50, offset: 0, day: "2026-10-08", counts: {} })).toBe(true);
    expect(isFollowUpListPage({ items: [], total: 0, limit: 50, offset: 0 })).toBe(false);
  });
});
