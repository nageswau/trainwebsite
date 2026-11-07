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
    expect(hrefs.slice(0, 21)).toEqual(["/recruiter/dashboard", "/recruiter/companies", "/recruiter/vendors", "/recruiter/profile", "/recruiter/skills", "/recruiter/candidates", "/recruiter/website-registrations", "/recruiter/find-candidates", "/recruiter/pools", "/recruiter/pipeline", "/recruiter/requirements", "/recruiter/follow-ups", "/recruiter/tasks", "/recruiter/meetings", "/recruiter/templates", "/recruiter/interviews", "/recruiter/joinings", "/recruiter/receivables", "/recruiter/drives", "/recruiter/colleges", "/recruiter/performance"]); // rec-003, rec-006, rec-009, hrc-025, rec-013, rec-015, rec-005, rec-007, rec-024, hrc-016, rec-028, pob-023, rec-020, rec-023, rec-031, rec-029, pob-013, rec-034
    expect(hrefs).toEqual(expect.arrayContaining(["/it/placement/candidates", "/it/placement/company-requirements", "/it/placement/reports"]));
    expect(hrefs.filter((h) => h.startsWith("/recruiter/manager"))).toEqual([]);
    expect(RECRUITER_MANAGER_NAV.map((x) => x.href)).toEqual(["/recruiter/dashboard", "/recruiter/manager/performance", "/recruiter/recruitment-dashboards", "/recruiter/performance", "/recruiter/manager/business", "/recruiter/manager/team", "/recruiter/companies", "/recruiter/vendors", "/recruiter/manager/catalogue", "/recruiter/manager/skills", "/recruiter/candidates", "/recruiter/website-registrations", "/recruiter/find-candidates", "/recruiter/pools", "/recruiter/candidates/duplicates", "/recruiter/candidates?owner=unassigned", "/recruiter/manager/routing", "/recruiter/notification-exceptions", "/recruiter/insights/skill-demand", "/recruiter/notifications", "/recruiter/pipeline", "/recruiter/requirements", "/recruiter/follow-ups", "/recruiter/tasks", "/recruiter/meetings", "/recruiter/interviews", "/recruiter/joinings", "/recruiter/receivables", "/recruiter/drives", "/recruiter/colleges", "/recruiter/manager/templates", "/recruiter/manager/cadences", "/recruiter/manager/screening-bank", "/recruiter/manager/report-library", "/account/management-tasks"]); // mgmt-028 (MT14); pob-013 // rec-032, rec-033, rec-034, rec-035, rec-002, rec-003, rec-006, rec-009, rec-013, rec-015, rec-005 + rec-007, rec-024, rec-028, rec-020, rec-023, rec-031, rec-026, nehn-016; hrc-014; hrc-024; hrc-025
    expect(PORTAL_NAV["it/placement"]).toContainEqual({ label: "Recruiter Workspace", href: "/recruiter/dashboard" });
    expect(PORTAL_NAV["it/hr"].map((x) => x.href).filter((h) => h.startsWith("/recruiter"))).toEqual(["/recruiter/candidates", "/recruiter/find-candidates", "/recruiter/pools"]); // rec-009 / rec-013 / rec-015: read only
  });

  it("gives super admin and IT admin a Recruiter Staff entry, leaving the companies page alone", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiter Staff", href: "/admin/recruiter-staff" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiters", href: "/admin/recruiters" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiter Companies", href: "/recruiter/companies" }); // rec-003
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiter Requirements", href: "/recruiter/requirements" }); // rec-007
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Find Candidates", href: "/recruiter/find-candidates" }); // rec-013
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Talent Pools", href: "/recruiter/pools" }); // rec-015
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Duplicate Review", href: "/recruiter/candidates/duplicates" }); // hrc-014
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Candidate Routing", href: "/recruiter/manager/routing" }); // hrc-024
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Delivery exceptions", href: "/recruiter/notification-exceptions" }); // hrc-032
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Campus Drives", href: "/recruiter/drives" }); // rec-029
    expect(PORTAL_NAV["it/admin"]).toContainEqual({ label: "Recruiter Staff", href: "/it/admin/recruiter-staff" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiter Performance", href: "/recruiter/manager/performance" }); // rec-033
    expect(PORTAL_NAV["it/admin"]).toContainEqual({ label: "Recruiter Performance", href: "/recruiter/manager/performance" }); // rec-033
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiter Comparison", href: "/recruiter/performance" }); // rec-034
    expect(PORTAL_NAV["it/admin"].map((x) => x.href)).not.toContain("/recruiter/performance"); // rec-034 BP1: revenue (RV10)
    expect(RECRUITER_MANAGER_NAV).toContainEqual({ label: "Management Dashboard", href: "/recruiter/manager/business" }); // rec-035
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiter Management Dashboard", href: "/recruiter/manager/business" }); // rec-035
    expect(PORTAL_NAV["it/admin"]).toContainEqual({ label: "Recruiter Management Dashboard", href: "/recruiter/manager/business" }); // rec-035
    expect(PORTAL_NAV["overseas/admin"].map((x) => x.href)).not.toContain("/overseas/admin/recruiter-staff");
  });
});
