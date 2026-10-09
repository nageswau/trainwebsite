import { describe, expect, it } from "vitest";

import {
  apiPath, type CalendarItem, datesText, isCalendarData, itemHref, itemsOn, KIND_LABELS, overlapText, pageHref, parseDate, parseView,
  rangeDays, rangeOf, stepDate,
} from "@/lib/partnershipCalendar";

// upc-011 (DEC-SCOPE-150 CL1, CL13): the pure calendar helpers.
const item = (over: Partial<CalendarItem> = {}): CalendarItem => ({
  source: "event", id: "e1", code: "PEV-000001", title: "QS Fair", kind: "education_fair", starts_on: "2031-03-04", ends_on: "2031-03-06",
  starts_at: null, status: "scheduled", university: null, people: [], overlaps: [], ...over,
});

describe("partnershipCalendar", () => {
  it("names all eight §9 kinds in source order", () => {
    expect(Object.values(KIND_LABELS)).toEqual([
      "University meeting", "University visit", "Conference", "Education fair", "Partner meeting", "MoU signing", "Webinar", "University presentation",
    ]);
  });

  it("parses the view and date, falling back to week and today", () => {
    expect(parseView("month")).toBe("month");
    expect(parseView("year")).toBe("week");
    expect(parseDate("2031-02-30", "2031-03-04")).toBe("2031-03-04");
    expect(parseDate("2031-03-10", "2031-03-04")).toBe("2031-03-10");
  });

  it("gives Monday-Sunday weeks and whole calendar months (≤ 31 days)", () => {
    expect(rangeOf("week", "2031-03-05")).toEqual({ from: "2031-03-03", to: "2031-03-09" });
    expect(rangeOf("month", "2031-02-14")).toEqual({ from: "2031-02-01", to: "2031-02-28" });
    expect(rangeOf("month", "2032-02-14")).toEqual({ from: "2032-02-01", to: "2032-02-29" });
    expect(rangeOf("month", "2031-12-31")).toEqual({ from: "2031-12-01", to: "2031-12-31" });
    expect(rangeDays("week", "2031-03-05")).toHaveLength(7);
  });

  it("steps a week or a month at a time, across years", () => {
    expect(stepDate("week", "2031-03-05", 1)).toBe("2031-03-12");
    expect(stepDate("week", "2031-03-05", -1)).toBe("2031-02-26");
    expect(stepDate("month", "2031-01-31", 1)).toBe("2031-02-01");
    expect(stepDate("month", "2031-01-15", -1)).toBe("2030-12-01");
  });

  it("puts a multi-day event on each of its days (E1)", () => {
    const fair = item();
    expect(itemsOn([fair], "2031-03-03")).toEqual([]);
    expect(itemsOn([fair], "2031-03-04")).toEqual([fair]);
    expect(itemsOn([fair], "2031-03-06")).toEqual([fair]);
    expect(itemsOn([fair], "2031-03-07")).toEqual([]);
  });

  it("links each source to its own page", () => {
    expect(itemHref({ source: "meeting", id: "m1" })).toBe("/partnership/meetings/m1");
    expect(itemHref({ source: "visit", id: "v1" })).toBe("/partnership/visits/v1");
    expect(itemHref({ source: "event", id: "e1" })).toBe("/partnership/events/e1");
  });

  it("builds page and API URLs", () => {
    expect(pageHref({ view: "month", date: "2031-03-01" })).toBe("/partnership/calendar?view=month&date=2031-03-01");
    expect(pageHref({ view: "week", date: "2031-03-01", employee: "u1" })).toBe("/partnership/calendar?view=week&date=2031-03-01&employee=u1");
    expect(apiPath("2031-03-01", "2031-03-31", "u1")).toBe("/api/v1/partnership/calendar?date_from=2031-03-01&date_to=2031-03-31&user_id=u1");
    expect(apiPath("2031-03-01", "2031-03-07")).toBe("/api/v1/partnership/calendar?date_from=2031-03-01&date_to=2031-03-07");
  });

  it("recognises calendar data", () => {
    expect(isCalendarData({ items: [], today: "2031-03-04" })).toBe(true);
    expect(isCalendarData({ detail: "nope" })).toBe(false);
    expect(isCalendarData(null)).toBe(false);
  });

  it("words overlaps and date ranges", () => {
    const o = { employee: { id: "u1", full_name: "Asha Rao", active: true }, item: { source: "visit" as const, id: "v1", code: "VIS-000003", title: "Oxford, Oxford" } };
    expect(overlapText(o)).toBe("Asha Rao is also at VIS-000003 (Oxford, Oxford)");
    expect(datesText("2031-03-04", "2031-03-04")).toBe("4 Mar 2031");
    expect(datesText("2031-03-04", "2031-03-06")).toBe("4–6 Mar 2031");
    expect(datesText("2031-03-30", "2031-04-02")).toBe("30 Mar – 2 Apr 2031");
    expect(datesText("2031-12-30", "2032-01-02")).toBe("30 Dec 2031 – 2 Jan 2032");
  });
});
