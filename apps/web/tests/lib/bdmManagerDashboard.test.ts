import { describe, expect, it } from "vitest";

import {
  alertHref, alertListHref, alertWhen, dashboardUrl, isManagerDashboard, TONE, type DashboardAlert, type DashboardAlertItem,
} from "@/lib/bdmManagerDashboard";

// bdm-023 (DEC-SCOPE-108): the management dashboard's helpers -- links (R9), the time line per alert, and the tone's text word (AC4).
const item = (over: Partial<DashboardAlertItem> = {}): DashboardAlertItem => ({
  id: "r1", title: "APT-1 · Sunrise College", bdm: { id: "b1", full_name: "Asha" }, at: "2026-10-08T04:30:00Z", organization_id: "o1", ...over,
});
const alert = (key: string, record: DashboardAlert["record"]): DashboardAlert => ({
  key, label: key, tone: "warning", record, count: 1, items: [item()],
});

describe("bdm-023 management dashboard helpers", () => {
  it("reads the API path, with the manager filter only when given", () => {
    expect(dashboardUrl()).toBe("/api/v1/bdm/manager/dashboard");
    expect(dashboardUrl("m1")).toBe("/api/v1/bdm/manager/dashboard?manager_user_id=m1");
  });

  it("links each alert item to its record (R9)", () => {
    expect(alertHref(alert("AL-1", "appointment"), item())).toBe("/bdm/manager/appointments/r1");
    expect(alertHref(alert("AL-2", "trip"), item())).toBe("/bdm/manager/trips/r1");
    expect(alertHref(alert("AL-3", "task"), item())).toBe("/bdm/manager/organizations/o1");
    expect(alertHref(alert("AL-3", "task"), item({ organization_id: null }))).toBe("/bdm/manager/follow-ups");
    expect(alertHref(alert("AL-4", "mou"), item())).toBe("/bdm/manager/organizations/o1");
    expect(alertHref(alert("AL-7", "daily_report"), item({ id: "b1", at: "2026-10-06" }))).toBe("/bdm/manager/daily-reports/b1?date=2026-10-06");
  });

  it("links each alert kind to its full list; super_admin's approvals are the admin queue", () => {
    expect(alertListHref("AL-1", false)).toBe("/bdm/manager/appointments");
    expect(alertListHref("AL-2", false)).toBe("/bdm/manager/approvals");
    expect(alertListHref("AL-2", true)).toBe("/admin/bdm-travel-approvals");
    expect(alertListHref("AL-3", false)).toBe("/bdm/manager/follow-ups");
    expect(alertListHref("AL-4", false)).toBe("/bdm/manager/mous");
    expect(alertListHref("AL-7", false)).toBe("/bdm/manager/daily-reports");
  });

  it("says when, in IST, in the alert's own words", () => {
    expect(alertWhen("AL-1", "2026-10-08T04:30:00Z")).toBe("Starts 8 Oct, 10:00 AM");
    expect(alertWhen("AL-2", "2026-10-18")).toBe("Travels 18 Oct");
    expect(alertWhen("AL-3", "2026-10-05")).toBe("Due 5 Oct");
    expect(alertWhen("AL-4", "2026-09-30T20:00:00Z")).toBe("Waiting since 1 Oct");
    expect(alertWhen("AL-5", "2026-10-07T09:45:00Z")).toBe("Completed 3:15 PM");
    expect(alertWhen("AL-6", "2026-10-07T04:30:00Z")).toBe("Started 7 Oct, 10:00 AM");
    expect(alertWhen("AL-7", "2026-10-06")).toBe("Report for 6 Oct");
  });

  it("gives every tone a text word as well as a colour (AC4)", () => {
    expect(TONE.danger).toEqual({ className: "status error", text: "Urgent" });
    expect(TONE.warning).toEqual({ className: "status pending", text: "Attention" });
    expect(TONE.success).toEqual({ className: "status", text: "Done" });
  });

  it("accepts only a dashboard body", () => {
    const body = { today: "2026-10-07", month: "2026-10-01", manager: null, tiles: [], alerts: [] };
    expect(isManagerDashboard(body)).toBe(true);
    expect(isManagerDashboard({ ...body, alerts: undefined })).toBe(false);
    expect(isManagerDashboard({ items: [], total: 0 })).toBe(false);
    expect(isManagerDashboard(null)).toBe(false);
  });
});
