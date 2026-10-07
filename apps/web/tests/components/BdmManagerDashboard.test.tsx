import { describe, expect, it } from "vitest";

import BdmManagerDashboard from "@/components/BdmManagerDashboard";
import type { DashboardAlert, ManagerDashboard } from "@/lib/bdmManagerDashboard";
import { elements, text } from "@/tests/helpers/elementTree";

// bdm-023 (DEC-SCOPE-104): the dashboard view is a plain function of its data, so it is called directly.
const TILES: [string, string, number][] = [
  ["T-M01", "Total BDMs", 8], ["T-M02", "Today's Appointments", 14], ["T-M03", "Upcoming Appointments", 36], ["T-M04", "BDMs Travelling", 4],
  ["T-M05", "Trips This Month", 18], ["T-M06", "Meetings Completed", 86], ["T-M07", "MoUs in Progress", 21], ["T-M08", "MoUs Signed", 9],
];
const quiet = (key: string, label: string, record: DashboardAlert["record"]): DashboardAlert => ({ key, label, tone: "warning", record, count: 0, items: [] });
const data = (over: Partial<ManagerDashboard> = {}): ManagerDashboard => ({
  today: "2026-10-07", month: "2026-10-01", manager: null,
  tiles: TILES.map(([key, label, value]) => ({ key, label, definition: `${label} definition.`, value })),
  alerts: [
    {
      key: "AL-1", label: "Appointment not confirmed", tone: "warning", record: "appointment", count: 12,
      items: [{ id: "a1", title: "APT-1 · Sunrise College", bdm: { id: "b1", full_name: "Asha" }, at: "2026-10-08T04:30:00Z", organization_id: "o1" }],
    },
    quiet("AL-2", "Travel approval pending", "trip"),
    {
      key: "AL-3", label: "Follow-up overdue", tone: "danger", record: "task", count: 1,
      items: [{ id: "t1", title: "Call back", bdm: { id: "b1", full_name: "Asha" }, at: "2026-10-05", organization_id: null }],
    },
    {
      key: "AL-5", label: "Appointment completed", tone: "success", record: "appointment", count: 1,
      items: [{ id: "a2", title: "APT-2 · Lake School", bdm: { id: "b2", full_name: "Ravi" }, at: "2026-10-07T09:45:00Z", organization_id: "o2" }],
    },
    {
      key: "AL-7", label: "Daily report not submitted", tone: "warning", record: "daily_report", count: 1,
      items: [{ id: "b3", title: "Kiran", bdm: { id: "b3", full_name: "Kiran" }, at: "2026-10-06", organization_id: null }],
    },
  ],
  ...over,
});
const tree = (d: ManagerDashboard, superAdmin = false) => elements(BdmManagerDashboard({ data: d, superAdmin }));
const allText = (t: ReturnType<typeof elements>) => t.map((el) => text(el)).join(" ");
const hrefs = (t: ReturnType<typeof elements>) => t.map((el) => el.props.href).filter((h): h is string => typeof h === "string");

describe("bdm-023 management dashboard view", () => {
  it("shows the 8 overview tiles in source order with their definitions (§13 example)", () => {
    const t = tree(data());
    const words = allText(t);
    for (const [, label, value] of TILES) expect(words).toContain(`${label}${value}`);
    expect(words).toContain("Total BDMs definition.");
    const labels = t.filter((el) => el.type === "dt").map((el) => text(el));
    expect(labels).toEqual(TILES.map(([, label]) => label));
  });

  it("lists only alerts that have records, each with a text status word, its count and linked items (AC1, AC4)", () => {
    const t = tree(data());
    const words = allText(t);
    expect(words).toContain("Attention");
    expect(words).toContain("Appointment not confirmed: 12");
    expect(words).toContain("Urgent");
    expect(words).toContain("Follow-up overdue: 1");
    expect(words).toContain("Done");
    expect(words).not.toContain("Travel approval pending");
    expect(words).toContain("Asha · Starts 8 Oct, 10:00 AM");
    expect(words).toContain("Ravi · Completed 3:15 PM");
    expect(words).toContain("Report for 6 Oct");
    expect(hrefs(t)).toEqual(expect.arrayContaining([
      "/bdm/manager/appointments/a1", "/bdm/manager/follow-ups", "/bdm/manager/appointments/a2", "/bdm/manager/daily-reports/b3?date=2026-10-06",
    ]));
  });

  it("says how many are shown when an alert has more than the first ten, with a link to the full list (R8)", () => {
    const t = tree(data());
    expect(allText(t)).toContain("Showing 1 of 12.");
    expect(hrefs(t)).toContain("/bdm/manager/appointments");
  });

  it("each alert is a labelled region", () => {
    const t = tree(data());
    for (const id of ["dashboard-overview", "dashboard-alerts", "alert-AL-1", "alert-AL-3"]) {
      const region = t.find((el) => el.props["aria-labelledby"] === id);
      expect(region, id).toBeTruthy();
      expect(t.some((el) => el.props.id === id)).toBe(true);
    }
  });

  it("says there are no alerts when every count is 0 (AC2: resolved alerts disappear)", () => {
    const t = tree(data({ alerts: [quiet("AL-1", "Appointment not confirmed", "appointment"), quiet("AL-2", "Travel approval pending", "trip")] }));
    expect(allText(t)).toContain("No alerts right now.");
    expect(allText(t)).not.toContain("Appointment not confirmed");
  });

  it("sends super_admin to the admin approvals queue", () => {
    const busy = data({ alerts: [{ ...quiet("AL-2", "Travel approval pending", "trip"), count: 1, items: [{ id: "t9", title: "TRV-9 · A → B", bdm: { id: "b1", full_name: "Asha" }, at: "2026-10-18", organization_id: null }] }] });
    expect(hrefs(tree(busy, true))).toContain("/admin/bdm-travel-approvals");
    expect(hrefs(tree(busy, false))).toContain("/bdm/manager/approvals");
  });
});
