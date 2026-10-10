import { describe, expect, it } from "vitest";

import { PARTNERSHIP_HEAD_NAV, PARTNERSHIP_MENU, PARTNERSHIP_NAV, PORTAL_NAV, ROLE_DASHBOARD_PATH, SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("upc-001 navigation", () => {
  it("lands each partnership role on its own page (AC3)", () => {
    expect(ROLE_DASHBOARD_PATH.partnership_manager).toBe("/partnership/dashboard");
    expect(ROLE_DASHBOARD_PATH.partnership_head).toBe("/partnership/head/team");
  });

  it("holds the §32 menu: 19 entries in source order, each naming its item (PU8)", () => {
    expect(PARTNERSHIP_MENU.map((e) => e.label)).toEqual([
      "Dashboard", "Global University Database", "University Master", "Contact Management", "Partnership Pipeline", "Meetings",
      "University Visits", "MoU & Agreements", "Commercial Terms", "Courses & Programs", "Student Opportunities", "University Performance",
      "Follow-ups & Tasks", "Calendar", "Documents", "Alerts", "Targets & Forecast", "Global Partnership Map", "Reports",
    ]);
    expect(PARTNERSHIP_MENU.every((e) => /^upc-\d{3}$/.test(e.item) && e.href.startsWith("/partnership/"))).toBe(true);
    expect(new Set(PARTNERSHIP_MENU.map((e) => e.href)).size).toBe(19);
  });

  it("links only the live entries, plus Profile (upc-003 University Master, upc-007 Partnership Pipeline, upc-009 Meetings, upc-010 University Visits, upc-014 MoU & Agreements, upc-016 Commercial Terms, upc-017 Courses & Programs, upc-018 Student Opportunities + University Performance, upc-020 Follow-ups & Tasks, upc-011 Calendar, upc-026 Documents, upc-015 Alerts, upc-021 Targets & Forecast)", () => {
    expect(PARTNERSHIP_MENU.filter((e) => e.live).map((e) => e.label)).toEqual(["Dashboard", "University Master", "Partnership Pipeline", "Meetings", "University Visits", "MoU & Agreements", "Commercial Terms", "Courses & Programs", "Student Opportunities", "University Performance", "Follow-ups & Tasks", "Calendar", "Documents", "Alerts", "Targets & Forecast"]);
    expect(PARTNERSHIP_NAV).toEqual([
      { label: "Dashboard", href: "/partnership/dashboard" }, { label: "University Master", href: "/partnership/universities" },
      { label: "Partnership Pipeline", href: "/partnership/pipeline" }, { label: "Meetings", href: "/partnership/meetings" },
      { label: "University Visits", href: "/partnership/visits" }, { label: "MoU & Agreements", href: "/partnership/agreements" },
      { label: "Commercial Terms", href: "/partnership/commercial-terms" }, { label: "Courses & Programs", href: "/partnership/courses" },
      { label: "Student Opportunities", href: "/partnership/opportunities" }, { label: "University Performance", href: "/partnership/performance" }, // upc-018
      { label: "Follow-ups & Tasks", href: "/partnership/tasks" }, { label: "Calendar", href: "/partnership/calendar" },
      { label: "Documents", href: "/partnership/documents" }, { label: "Alerts", href: "/partnership/alerts" }, // upc-015
      { label: "Targets & Forecast", href: "/partnership/targets" },
      { label: "Profile", href: "/partnership/profile" },
    ]);
    expect(PARTNERSHIP_HEAD_NAV).toEqual([
      { label: "Team", href: "/partnership/head/team" }, { label: "University Master", href: "/partnership/universities" },
      { label: "Partnership Pipeline", href: "/partnership/pipeline" }, { label: "Meetings", href: "/partnership/meetings" }, // upc-009
      { label: "University Visits", href: "/partnership/visits" }, { label: "Visit approvals", href: "/partnership/visits/approvals" },
      { label: "MoU & Agreements", href: "/partnership/agreements" }, { label: "Commercial Terms", href: "/partnership/commercial-terms" },
      { label: "Courses & Programs", href: "/partnership/courses" },
      { label: "Student Opportunities", href: "/partnership/opportunities" }, { label: "University Performance", href: "/partnership/performance" }, // upc-018
      { label: "Follow-ups & Tasks", href: "/partnership/tasks" }, { label: "Calendar", href: "/partnership/calendar" }, // upc-011
      { label: "Documents", href: "/partnership/documents" }, { label: "Alerts", href: "/partnership/alerts" }, // upc-015
      { label: "Message templates", href: "/partnership/head/templates" }, { label: "Targets & Forecast", href: "/partnership/targets" },
    ]);
  });

  it("gives the Super Admin the partnership calendar (upc-011 CL9: everyone)", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Calendar", href: "/partnership/calendar" });
  });

  it("gives the Super Admin the visit approval queue (upc-010 VS4 fallback)", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Visit Approvals", href: "/partnership/visits/approvals" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Follow-ups & Tasks", href: "/partnership/tasks" }); // upc-020 QA-03
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Meetings", href: "/partnership/meetings" }); // upc-009 MG14
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Targets", href: "/partnership/targets" }); // upc-021
  });

  it("gives the Super Admin and Overseas Admin a Partnership managers entry", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership managers", href: "/admin/partnership-managers" });
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "Partnership managers", href: "/overseas/admin/partnership-managers" });
    expect(PORTAL_NAV["it/admin"].some((x) => x.href.includes("partnership"))).toBe(false);
  });
});
