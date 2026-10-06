import { describe, expect, it } from "vitest";

import { BDM_MANAGER_NAV, BDM_NAV, BDM_SIGN_IN, PORTAL_NAV, ROLE_DASHBOARD_PATH, SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("bdm-001 navigation", () => {
  it("lands each BDM role on its own page (AC05)", () => {
    expect(ROLE_DASHBOARD_PATH.bdm).toBe("/bdm/my-day");
    expect(ROLE_DASHBOARD_PATH.bdm_manager).toBe("/bdm/manager/dashboard");
  });

  it("has a BDM nav, a manager nav and the sign-in chooser path", () => {
    expect(BDM_NAV.map((x) => x.href)).toEqual([
      "/bdm/my-day", "/bdm/calendar", "/bdm/organizations", "/bdm/pipeline", "/bdm/mous", "/bdm/appointments", "/bdm/follow-ups", "/bdm/activities",
      "/bdm/travel", "/bdm/notifications", "/bdm/profile",
    ]);
    expect(BDM_MANAGER_NAV.map((x) => x.href)).toEqual([
      "/bdm/manager/dashboard", "/bdm/manager/team", "/bdm/manager/organizations", "/bdm/manager/pipeline", "/bdm/manager/mous", "/bdm/manager/appointments",
      "/bdm/manager/follow-ups", "/bdm/manager/calendar", "/bdm/manager/activities", "/bdm/manager/approvals", "/bdm/manager/notifications",
    ]);
    expect(BDM_SIGN_IN).toBe("/bdm/sign-in");
  });

  it("gives each admin a BDMs entry, spelled BDMs", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "BDMs", href: "/admin/bdms" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "BDM Travel Approvals", href: "/admin/bdm-travel-approvals" }); // bdm-010 T8
    expect(PORTAL_NAV["it/admin"]).toContainEqual({ label: "BDMs", href: "/it/admin/bdms" });
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "BDMs", href: "/overseas/admin/bdms" });
  });
});
