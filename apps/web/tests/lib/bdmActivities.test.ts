import { describe, expect, it } from "vitest";

import { activityRuleField, isCalendarDate, contactText, isDayPage, needsDirection, placeNewest, type Activity } from "@/lib/bdmActivities";

const a = (over: Partial<Activity> = {}): Activity => ({
  id: "a1", organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
  contact_id: null, contact_name: null, contact_removed: false, channel: "call", direction: "outbound", occurred_at: "2026-10-03T05:00:00Z",
  note: null, created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true }, ...over,
});

describe("bdmActivities", () => {
  it("isCalendarDate accepts only real YYYY-MM-DD days (QA9B-01)", () => {
    expect(isCalendarDate("2026-02-28")).toBe(true);
    expect(isCalendarDate("2028-02-29")).toBe(true);
    for (const bad of ["2026-02-30", "2026-13-01", "2026-00-10", "20261-10-01", "2026-1-1", "", "x"]) expect(isCalendarDate(bad)).toBe(false);
  });

  it("knows which channels carry a direction", () => {
    expect(["call", "whatsapp", "email"].every((c) => needsDirection(c as Activity["channel"]))).toBe(true);
    expect(["visit", "meeting", "other"].some((c) => needsDirection(c as Activity["channel"]))).toBe(false);
  });

  it("words a removed contact", () => {
    expect(contactText(a())).toBeNull();
    expect(contactText(a({ contact_id: "c1", contact_name: "Dr Rao" }))).toBe("Dr Rao");
    expect(contactText(a({ contact_name: "Dr Rao", contact_removed: true }))).toBe("Dr Rao (removed)");
  });

  it("puts the API's time and contact sentences on their fields", () => {
    expect(activityRuleField("When can't be in the future")).toEqual({ occurred_at: "When can't be in the future" });
    expect(activityRuleField("Activities can be logged up to 7 days back")).toHaveProperty("occurred_at");
    expect(activityRuleField("An activity can only be moved within today")).toHaveProperty("occurred_at");
    expect(activityRuleField("Choose a contact of this organization")).toHaveProperty("contact_id");
    expect(activityRuleField("Only the organization's assigned BDM can log activity")).toEqual({});
    expect(activityRuleField([{ loc: ["body", "x"] }])).toEqual({});
  });

  it("places an activity newest first and replaces an edited one", () => {
    const list = [a({ id: "a2", occurred_at: "2026-10-03T06:00:00Z" }), a({ id: "a1" })];
    expect(placeNewest(list, a({ id: "a3", occurred_at: "2026-10-03T05:30:00Z" })).map((x) => x.id)).toEqual(["a2", "a3", "a1"]);
    expect(placeNewest(list, a({ id: "a1", occurred_at: "2026-10-03T07:00:00Z" })).map((x) => x.id)).toEqual(["a1", "a2"]);
  });

  it("trusts a day page only with counts", () => {
    expect(isDayPage({ items: [], total: 0, limit: 50, offset: 0 })).toBe(false);
    expect(isDayPage({ items: [], total: 0, limit: 50, offset: 0, counts: { day: "2026-10-03", by_channel: {}, calls_made: 0, organizations_contacted: 0 } })).toBe(true);
  });
});
