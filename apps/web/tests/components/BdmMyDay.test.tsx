import { describe, expect, it } from "vitest";

import BdmMyDay from "@/components/BdmMyDay";
import type { MyDay } from "@/lib/bdmMyDay";
import { elements, text } from "@/tests/helpers/elementTree";

// bdm-014 (DEC-SCOPE-097): the My Day view is a plain function of its data, so it is called directly.
const org = (name: string) => ({ id: `o-${name}`, code: "ORG-1", name, org_type: "college", archived: false });
const appt = (id: string, startsAt: string, name: string, status = "scheduled") => ({
  id, code: `APT-${id}`, starts_at: startsAt, duration_minutes: 60, appointment_type: "college_meeting", status, organization: org(name),
});
const data = (over: Partial<MyDay> = {}): MyDay => ({
  today: "2026-09-13", bdm_type: "college",
  appointments: {
    count: 3, truncated: false,
    items: [appt("a1", "2026-09-13T04:30:00Z", "ABC College"), appt("a2", "2026-09-13T07:30:00Z", "XYZ College", "confirmed"), appt("a3", "2026-09-13T10:30:00Z", "PQR College")],
  },
  trips: {
    total: 2,
    items: [
      { id: "t1", code: "TRV-1", travel_date: "2026-09-18", return_date: "2026-09-19", from_place: "Hyderabad", to_place: "Vijayawada", approval_status: "approved", travel_status: "planned", appointment_count: 3 },
      { id: "t2", code: "TRV-2", travel_date: "2026-09-22", return_date: "2026-09-24", from_place: "Hyderabad", to_place: "Bangalore", approval_status: "draft", travel_status: "planned", appointment_count: 5 },
    ],
  },
  follow_ups: { total: 7, groups: [{ key: "college", count: 4 }, { key: "agent", count: 2 }, { key: "mou", count: 1 }] },
  tiles: [
    { key: "T-K1", label: "College meetings", tracked: true, value: 3, note: null },
    { key: "T-K7", label: "MoU follow-ups", tracked: false, value: null, note: "MoU follow-ups are not created in EduSphere yet." },
  ],
  ...over,
});
const empty = data({
  appointments: { count: 0, truncated: false, items: [] }, trips: { total: 0, items: [] }, follow_ups: { total: 0, groups: [] },
  tiles: [{ key: "T-K1", label: "College meetings", tracked: true, value: 0, note: null }],
});
const tree = (d: MyDay) => elements(BdmMyDay({ data: d }));
const allText = (t: ReturnType<typeof elements>) => t.map((el) => text(el)).join(" ");
const hrefs = (t: ReturnType<typeof elements>) => t.map((el) => el.props.href).filter((h): h is string => typeof h === "string");
const region = (t: ReturnType<typeof elements>, name: string) => t.find((el) => el.props["aria-labelledby"] === name);

describe("bdm-014 My Day view", () => {
  it("renders the §15 example: appointments by time and organization, trips with counts, follow-ups by type (AC1)", () => {
    const t = tree(data());
    const words = allText(t);
    expect(words).toContain("Today's appointments: 3");
    expect(words).toContain("10:00 AM — ABC College");
    expect(words).toContain("1:00 PM — XYZ College");
    expect(words).toContain("4:00 PM — PQR College");
    expect(words).toContain("Confirmed");
    expect(words).toContain("18 Sep — Hyderabad → Vijayawada");
    expect(words).toContain("3 appointments scheduled");
    expect(words).toContain("22 Sep — Hyderabad → Bangalore");
    expect(words).toContain("5 appointments scheduled");
    expect(words).toContain("4 College follow-ups");
    expect(words).toContain("2 Agent follow-ups");
    expect(words).toContain("1 MoU follow-up");
    expect(hrefs(t)).toEqual(expect.arrayContaining(["/bdm/appointments/a1", "/bdm/travel/t1", "/bdm/travel/t2", "/bdm/follow-ups", "/bdm/travel"]));
  });

  it("each section is a labelled region", () => {
    const t = tree(data());
    for (const id of ["my-day-appointments", "my-day-travel", "my-day-follow-ups", "my-day-overview"]) expect(region(t, id)).toBeTruthy();
  });

  it("shows tracked tiles as numbers and untracked ones as a label with the reason, never 0 (AC3)", () => {
    const t = tree(data());
    const tiles = t.filter((el) => el.props.className === "kpi-tile");
    expect(tiles.map((el) => text(el))).toEqual([
      "College meetings3",
      "MoU follow-upsNot tracked yetMoU follow-ups are not created in EduSphere yet.",
    ]);
    expect(allText(t)).toContain("College overview");
  });

  it("a new BDM sees empty states with a call to action in each section", () => {
    const t = tree(empty);
    const words = allText(t);
    expect(words).toContain("No appointments today.");
    expect(words).toContain("No upcoming travel.");
    expect(words).toContain("No follow-ups due.");
    expect(hrefs(t)).toEqual(expect.arrayContaining(["/bdm/appointments/new", "/bdm/travel/new", "/bdm/follow-ups"]));
    expect(t.filter((el) => el.props.className === "kpi-tile").map((el) => text(el))).toEqual(["College meetings0"]);
  });

  it("says when the appointment list is cut and when more trips exist", () => {
    const words = allText(tree(data({ appointments: { ...data().appointments, count: 60, truncated: true }, trips: { ...data().trips, total: 9 } })));
    expect(words).toContain("Showing the first 3 of 60 appointments.");
    expect(words).toContain("All travel (9)");
  });
});
