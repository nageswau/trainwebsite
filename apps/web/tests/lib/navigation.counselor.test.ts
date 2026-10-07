import { describe, expect, it } from "vitest";

import { dashboardPathFor, PORTAL_NAV, ROLE_DASHBOARD_PATH } from "@/lib/navigation";

// tel-017 (DEC-SCOPE-076): a counselor belongs to IT or Overseas; the IT workspace is Dashboard + My Leads (C1).
describe("tel-017 IT counselor navigation", () => {
  it("lands an IT counselor on the IT workspace and everyone else as before", () => {
    expect(dashboardPathFor({ role: "counselor", division: "it" })).toBe("/it/counselor/dashboard");
    expect(dashboardPathFor({ role: "counselor", division: "overseas" })).toBe("/overseas/counselor/dashboard");
    expect(dashboardPathFor({ role: "trainer", division: "it" })).toBe(ROLE_DASHBOARD_PATH.trainer);
    expect(dashboardPathFor({ role: "telecaller", division: "it" })).toBe("/telecaller/dashboard");
    expect(dashboardPathFor({ role: "nobody" })).toBe("/");
  });

  // tel-016 (DEC-SCOPE-095 AP14) adds Appointments (the lead bookings).
  it("gives the IT counselor Dashboard, Leads and Appointments only", () => {
    expect(PORTAL_NAV["it/counselor"]).toEqual([
      { label: "Dashboard", href: "/it/counselor/dashboard" },
      { label: "Leads", href: "/it/counselor/leads" },
      { label: "Appointments", href: "/it/counselor/appointments" },
    ]);
  });

  it("lists Counselors for the IT admin, after Trainers", () => {
    const hrefs = PORTAL_NAV["it/admin"].map((item) => item.href);
    expect(hrefs.indexOf("/it/admin/counselors")).toBe(hrefs.indexOf("/it/admin/trainers") + 1);
  });

  it("keeps the overseas counselor nav unchanged", () => {
    expect(PORTAL_NAV["overseas/counselor"].map((item) => item.href.split("/").pop())).toEqual(
      ["dashboard", "students", "leads", "documents", "applications", "school-applications", "visa", "appointments", "counselor-chat", "reports"],
    );
  });
});
