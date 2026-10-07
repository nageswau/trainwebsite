import { describe, expect, it } from "vitest";

import { followUpText, isMyDay, MY_DAY_URL, timeText, tripAppointmentsText, tripDateText } from "@/lib/bdmMyDay";

// bdm-014 (DEC-SCOPE-097): the My Day helpers -- the §15 wording ("10:00 AM", "18 Sep", "3 appointments scheduled", "4 College follow-ups").
describe("bdm-014 My Day helpers", () => {
  it("reads the API path", () => {
    expect(MY_DAY_URL).toBe("/api/v1/bdm/my-day");
  });

  it("shows times in IST, 12-hour like the source", () => {
    expect(timeText("2026-09-13T04:30:00Z")).toBe("10:00 AM");
    expect(timeText("2026-09-13T10:30:00Z")).toBe("4:00 PM");
  });

  it("shows a trip date as day and short month, whatever the viewer's zone", () => {
    expect(tripDateText("2026-09-18")).toBe("18 Sep");
  });

  it("counts a trip's appointments in words", () => {
    expect(tripAppointmentsText(0)).toBe("No appointments scheduled");
    expect(tripAppointmentsText(1)).toBe("1 appointment scheduled");
    expect(tripAppointmentsText(5)).toBe("5 appointments scheduled");
  });

  it("names a follow-up group by organization type, MoU or none", () => {
    expect(followUpText({ key: "college", count: 4 })).toBe("4 College follow-ups");
    expect(followUpText({ key: "agent", count: 1 })).toBe("1 Agent follow-up");
    expect(followUpText({ key: "mou", count: 1 })).toBe("1 MoU follow-up");
    expect(followUpText({ key: "none", count: 2 })).toBe("2 follow-ups without an organization");
    expect(followUpText({ key: "training_institute", count: 2 })).toBe("2 Training Institute follow-ups");
  });

  it("accepts only a My Day body", () => {
    const body = { today: "2026-09-13", bdm_type: "college", appointments: { count: 0, truncated: false, items: [] }, trips: { total: 0, items: [] }, follow_ups: { total: 0, groups: [] }, tiles: [] };
    expect(isMyDay(body)).toBe(true);
    expect(isMyDay({ ...body, tiles: undefined })).toBe(false);
    expect(isMyDay(null)).toBe(false);
    expect(isMyDay({ detail: "x" })).toBe(false);
  });
});
