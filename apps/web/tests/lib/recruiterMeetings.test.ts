import { describe, expect, it } from "vitest";

import { isMeetingListPage, isView, MEETING_TYPES, meetingsUrl, meetingTypeLabel, MODES } from "@/lib/recruiterMeetings";

// rec-028 (MT1, MT4, MT10): the §20 types in source order, the modes and the list URL.
describe("recruiterMeetings (rec-028)", () => {
  it("has the seven EVID-018 §20 meeting types in source order and the three modes", () => {
    expect(MEETING_TYPES.map((t) => t.label)).toEqual([
      "Company meeting", "HR meeting", "Requirement discussion", "Recruitment presentation", "Contract discussion",
      "Campus recruitment discussion", "Placement drive discussion",
    ]);
    expect(meetingTypeLabel("hr_meeting")).toBe("HR meeting");
    expect(meetingTypeLabel("unknown")).toBe("unknown");
    expect(MODES).toEqual(["Online", "Phone", "In person"]);
  });

  it("builds the list URL, recognises the views and a list page", () => {
    expect(meetingsUrl("awaiting_outcome", 50)).toBe("/api/v1/recruiter/meetings?view=awaiting_outcome&limit=50&offset=50");
    expect(isView("cancelled")).toBe(true);
    expect(isView("today")).toBe(false);
    expect(isMeetingListPage({ items: [], total: 0, limit: 50, offset: 0, counts: {} })).toBe(true);
    expect(isMeetingListPage({ items: [], total: 0, limit: 50, offset: 0 })).toBe(false);
  });
});
