import { describe, expect, it } from "vitest";

import {
  addDays, apiPath, type CalendarData, dayItems, daysOf, dayTitle, headline, isCalendarData, itemHref, pageHref, parseDate, parseView,
  plural, rangeOf, rangeTitle, weekStart,
} from "@/lib/bdmCalendar";

// bdm-013 (DEC-SCOPE-078 K6/K7/K8): the pure calendar helpers. The §5 week: Mon 2031-03-03 … Sun 2031-03-09.
const org = (name: string) => ({ id: `o-${name}`, code: "ORG-1", name, archived: false });
const appt = (id: string, day: string, type: string, time = "10:00", seminar = false) => ({
  id, code: `APT-${id}`, day, starts_at: `${day}T${time}:00+05:30`, duration_minutes: 60, appointment_type: type, status: "scheduled",
  seminar, organization: org("Govt College"),
});
const trip = (id: string, travel: string, ret: string, to: string) => ({
  id, code: `TRV-${id}`, travel_date: travel, return_date: ret, from_place: "Hyderabad", to_place: to, mode: "train",
  approval_status: "approved", travel_status: "planned",
});
const task = (id: string, due: string, kind = "follow_up", status = "open") => ({
  id, kind, title: `Call ${id}`, due_on: due, status, overdue: false, organization: null,
});
const data = (over: Partial<CalendarData> = {}): CalendarData => ({
  bdm: { id: "b1", full_name: "Asha", active: true }, date_from: "2031-03-03", date_to: "2031-03-09", today: "2031-03-04",
  truncated: false, appointments: [], trips: [], tasks: [], ...over,
});

// The source §5 example, reproduced from records.
const section5 = data({
  appointments: [
    appt("a1", "2031-03-03", "agent_meeting"), appt("a2", "2031-03-03", "agent_meeting", "14:00"),
    appt("a3", "2031-03-04", "college_meeting"), appt("a4", "2031-03-04", "college_meeting", "12:00"),
    appt("a5", "2031-03-05", "college_meeting"), appt("a6", "2031-03-05", "principal_meeting", "15:00"),
  ],
  trips: [trip("t1", "2031-03-03", "2031-03-03", "Hyderabad"), trip("t2", "2031-03-04", "2031-03-06", "Vijayawada")],
  tasks: [task("f1", "2031-03-07"), task("f2", "2031-03-07", "task")],
});

describe("dates", () => {
  it("parses view and date, falling back to week and today", () => {
    expect(parseView("day")).toBe("day");
    expect(parseView("month")).toBe("week");
    expect(parseView(undefined)).toBe("week");
    expect(parseDate("2031-03-05", "2031-01-01")).toBe("2031-03-05");
    expect(parseDate("2031-02-30", "2031-01-01")).toBe("2031-01-01");
    expect(parseDate(["2031-03-05"], "2031-01-01")).toBe("2031-01-01");
  });

  it("weeks run Monday to Sunday, across month and year ends", () => {
    expect(weekStart("2031-03-05")).toBe("2031-03-03");
    expect(weekStart("2031-03-03")).toBe("2031-03-03");
    expect(weekStart("2031-03-09")).toBe("2031-03-03");
    expect(weekStart("2031-01-01")).toBe("2030-12-30");
    expect(addDays("2031-02-28", 1)).toBe("2031-03-01");
    expect(rangeOf("week", "2031-03-05")).toEqual({ from: "2031-03-03", to: "2031-03-09" });
    expect(rangeOf("day", "2031-03-05")).toEqual({ from: "2031-03-05", to: "2031-03-05" });
    expect(daysOf("2031-03-08", "2031-03-10")).toEqual(["2031-03-08", "2031-03-09", "2031-03-10"]);
  });

  it("titles days and ranges", () => {
    expect(dayTitle("2031-03-03")).toBe("Monday 3 Mar");
    expect(rangeTitle("2031-03-03", "2031-03-09")).toBe("3–9 Mar 2031");
    expect(rangeTitle("2031-03-31", "2031-04-06")).toBe("31 Mar – 6 Apr 2031");
    expect(rangeTitle("2030-12-30", "2031-01-05")).toBe("30 Dec 2030 – 5 Jan 2031");
    expect(rangeTitle("2031-03-05", "2031-03-05")).toBe("Wednesday 5 Mar 2031");
  });
});

describe("placing items (AC1)", () => {
  it("puts a trip on every day from travel to return, with its role", () => {
    const d = data({ trips: [trip("t2", "2031-03-04", "2031-03-06", "Vijayawada")] });
    expect(dayItems(d, "2031-03-03").trips).toEqual([]);
    expect(dayItems(d, "2031-03-04").trips.map((t) => t.role)).toEqual(["departs"]);
    expect(dayItems(d, "2031-03-05").trips.map((t) => t.role)).toEqual(["away"]);
    expect(dayItems(d, "2031-03-06").trips.map((t) => t.role)).toEqual(["returns"]);
    expect(dayItems(data({ trips: [trip("t1", "2031-03-03", "2031-03-03", "Hyderabad")] }), "2031-03-03").trips.map((t) => t.role)).toEqual(["day trip"]);
  });

  it("puts appointments on their IST day and tasks on their due date", () => {
    const items = dayItems(section5, "2031-03-04");
    expect(items.appointments.map((a) => a.id)).toEqual(["a3", "a4"]);
    expect(dayItems(section5, "2031-03-07").tasks.map((t) => t.id)).toEqual(["f1", "f2"]);
    expect(dayItems(section5, "2031-03-08")).toEqual({ trips: [], appointments: [], tasks: [] });
  });
});

describe("headline (K6, AC2)", () => {
  it("reproduces the §5 week", () => {
    expect(daysOf("2031-03-03", "2031-03-09").map((d) => headline(section5, d))).toEqual([
      "Hyderabad – Agent Meetings",
      "Vijayawada – College Meetings",
      "Vijayawada – College Meetings",
      "Return travel",
      "Follow-ups",
      "Nothing planned",
      "Nothing planned",
    ]);
  });

  it("covers travel days without meetings, returns with meetings, meetings at home, and tasks only", () => {
    const d = data({
      trips: [trip("t", "2031-03-03", "2031-03-05", "Vijayawada")],
      appointments: [appt("r", "2031-03-05", "hod_meeting"), appt("h", "2031-03-06", "seminar_workshop", "10:00", true)],
      tasks: [task("x", "2031-03-07", "task")],
    });
    expect(headline(d, "2031-03-03")).toBe("Travel to Vijayawada");
    expect(headline(d, "2031-03-04")).toBe("Vijayawada");
    expect(headline(d, "2031-03-05")).toBe("Return travel – HOD Meetings");
    expect(headline(d, "2031-03-06")).toBe("Seminar / Workshops");
    expect(headline(d, "2031-03-07")).toBe("Tasks");
  });

  it("breaks a dominant-type tie by the earliest appointment", () => {
    const d = data({ appointments: [appt("b", "2031-03-03", "hod_meeting", "11:00"), appt("a", "2031-03-03", "faculty_meeting", "09:00")] });
    expect(headline(d, "2031-03-03")).toBe("Faculty Meetings");
  });

  it("pluralizes labels", () => {
    expect(plural("College Meeting")).toBe("College Meetings");
    expect(plural("Business")).toBe("Business");
    expect(plural("Other")).toBe("Others");
  });
});

describe("links (K8)", () => {
  it("opens each item for a BDM and for a manager", () => {
    const a = section5.appointments[0];
    const t = section5.trips[0];
    const withOrg = { ...task("f", "2031-03-07"), organization: org("X") };
    expect(itemHref("appointment", a, null)).toBe("/bdm/appointments/a1");
    expect(itemHref("trip", t, null)).toBe("/bdm/travel/t1");
    expect(itemHref("task", withOrg, null)).toBe("/bdm/organizations/o-X");
    expect(itemHref("task", task("f", "2031-03-07"), null)).toBe("/bdm/follow-ups");
    expect(itemHref("appointment", a, "b1")).toBe("/bdm/manager/appointments/a1");
    expect(itemHref("trip", t, "b1")).toBe("/bdm/manager/trips/t1");
    expect(itemHref("task", withOrg, "b1")).toBe("/bdm/manager/organizations/o-X");
    expect(itemHref("task", task("f", "2031-03-07"), "b1")).toBe("/bdm/manager/follow-ups?bdm=b1");
  });

  it("builds page and API URLs", () => {
    expect(pageHref("/bdm/calendar", { view: "day", date: "2031-03-05" })).toBe("/bdm/calendar?view=day&date=2031-03-05");
    expect(pageHref("/bdm/manager/calendar", { view: "week", date: "2031-03-05", bdm: "b1" })).toBe("/bdm/manager/calendar?view=week&date=2031-03-05&bdm=b1");
    expect(apiPath("2031-03-03", "2031-03-09")).toBe("/api/v1/bdm/calendar?date_from=2031-03-03&date_to=2031-03-09");
    expect(apiPath("2031-03-03", "2031-03-09", "b1")).toBe("/api/v1/bdm/calendar?date_from=2031-03-03&date_to=2031-03-09&bdm_user_id=b1");
  });
});

it("recognizes a calendar response", () => {
  expect(isCalendarData(section5)).toBe(true);
  expect(isCalendarData({ items: [] })).toBe(false);
  expect(isCalendarData(null)).toBe(false);
});
