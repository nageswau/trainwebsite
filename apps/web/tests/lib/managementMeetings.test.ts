import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, pillarsFor } from "@/lib/management";
import { calendarHref, calendarUrl, istDay, istTime, KIND_LABEL, meetingsOn, progressText, safeLink } from "@/lib/managementMeetings";

describe("managementMeetings (mgmt-029)", () => {
  it("lists the seven §29 kinds in source order and wording", () => {
    expect(Object.values(KIND_LABEL)).toEqual([
      "Partner meeting", "Department meeting", "School meeting", "University meeting", "Agent meeting", "Recruiter meeting", "Marketing review",
    ]);
  });

  it("places a meeting on its IST day, not the UTC one", () => {
    const early = { starts_at: "2026-10-13T18:45:00Z" }; // 00:15 IST on the 14th
    const late = { starts_at: "2026-10-14T18:15:00Z" }; // 23:45 IST on the 14th
    expect(istDay(early.starts_at)).toBe("2026-10-14");
    expect(istTime(early.starts_at)).toBe("00:15");
    expect(meetingsOn([early, late, { starts_at: "2026-10-14T18:30:00Z" }], "2026-10-14")).toEqual([early, late]);
  });

  it("builds the calendar's page and API links", () => {
    expect(calendarHref("month", "2026-10-14")).toBe("/management/meetings?view=month&date=2026-10-14");
    expect(calendarUrl("2026-10-12", "2026-10-18")).toBe("/api/v1/management/meetings?date_from=2026-10-12&date_to=2026-10-18");
  });

  it("puts the roll-up in words", () => {
    expect(progressText({ done: 0, total: 0 })).toBe("No decisions or tasks yet");
    expect(progressText({ done: 1, total: 3 })).toBe("1 of 3 completed");
  });

  it("links the Command Center's Meetings entry for the operational tier only (MM14)", () => {
    const entry = MANAGEMENT_PILLARS.flatMap((p) => p.entries).find((e) => e.item === "mgmt-029");
    expect(entry).toMatchObject({ label: "Meetings", tier: "operational", href: "/management/meetings" });
    const finance = pillarsFor({ operational: false, finance: true, partner_only: false }).flatMap((p) => p.entries);
    expect(finance.some((e) => e.item === "mgmt-029")).toBe(false);
  });

  it("renders only http(s) links", () => {
    expect(safeLink("https://meet.example.com/a")).toBe("https://meet.example.com/a");
    expect(safeLink("javascript:alert(1)")).toBeNull();
    expect(safeLink(null)).toBeNull();
  });
});
