import { describe, expect, it } from "vitest";

import { PORTAL_NAV, RECRUITER_MANAGER_NAV, RECRUITER_NAV, ROLE_DASHBOARD_PATH, SUPER_ADMIN_NAV, dashboardPathFor } from "@/lib/navigation";

describe("rec-001 navigation", () => {
  it("lands a recruiter on the recruiter dashboard and a manager on their team (AC3)", () => {
    expect(ROLE_DASHBOARD_PATH.placement_team).toBe("/recruiter/dashboard");
    expect(ROLE_DASHBOARD_PATH.placement_manager).toBe("/recruiter/manager/team");
    expect(dashboardPathFor({ role: "placement_team", division: "it" })).toBe("/recruiter/dashboard");
    expect(ROLE_DASHBOARD_PATH.hr_team).toBe("/it/hr/dashboard"); // AC6: unchanged
  });

  it("gives the recruiter their workspace plus the legacy placement screens (Q-29), and the manager only manager pages", () => {
    const hrefs = RECRUITER_NAV.map((x) => x.href);
    expect(hrefs.slice(0, 6)).toEqual(["/recruiter/dashboard", "/recruiter/companies", "/recruiter/profile", "/recruiter/skills", "/recruiter/candidates", "/recruiter/follow-ups"]); // rec-003, rec-006, rec-009, rec-024
    expect(hrefs).toEqual(expect.arrayContaining(["/it/placement/candidates", "/it/placement/company-requirements", "/it/placement/reports"]));
    expect(hrefs.filter((h) => h.startsWith("/recruiter/manager"))).toEqual([]);
    expect(RECRUITER_MANAGER_NAV.map((x) => x.href)).toEqual(["/recruiter/manager/team", "/recruiter/companies", "/recruiter/manager/catalogue", "/recruiter/manager/skills", "/recruiter/candidates", "/recruiter/follow-ups"]); // rec-002, rec-003, rec-006, rec-009, rec-024
    expect(PORTAL_NAV["it/placement"]).toContainEqual({ label: "Recruiter Workspace", href: "/recruiter/dashboard" });
    expect(PORTAL_NAV["it/hr"].map((x) => x.href).filter((h) => h.startsWith("/recruiter"))).toEqual(["/recruiter/candidates"]); // rec-009: read only
  });

  it("gives super admin and IT admin a Recruiter Staff entry, leaving the companies page alone", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiter Staff", href: "/admin/recruiter-staff" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiters", href: "/admin/recruiters" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiter Companies", href: "/recruiter/companies" }); // rec-003
    expect(PORTAL_NAV["it/admin"]).toContainEqual({ label: "Recruiter Staff", href: "/it/admin/recruiter-staff" });
    expect(PORTAL_NAV["overseas/admin"].map((x) => x.href)).not.toContain("/overseas/admin/recruiter-staff");
  });
});
