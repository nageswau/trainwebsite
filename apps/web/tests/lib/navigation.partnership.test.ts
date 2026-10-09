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

  it("links only the live entries, plus Profile (upc-003 University Master, upc-007 Partnership Pipeline, upc-009 Meetings, upc-010 University Visits, upc-014 MoU & Agreements, upc-020 Follow-ups & Tasks, upc-026 Documents)", () => {
    expect(PARTNERSHIP_MENU.filter((e) => e.live).map((e) => e.label)).toEqual(["Dashboard", "University Master", "Partnership Pipeline", "Meetings", "University Visits", "MoU & Agreements", "Follow-ups & Tasks", "Documents"]);
    expect(PARTNERSHIP_NAV).toEqual([
      { label: "Dashboard", href: "/partnership/dashboard" }, { label: "University Master", href: "/partnership/universities" },
      { label: "Partnership Pipeline", href: "/partnership/pipeline" }, { label: "Meetings", href: "/partnership/meetings" },
      { label: "University Visits", href: "/partnership/visits" }, { label: "MoU & Agreements", href: "/partnership/agreements" },
      { label: "Follow-ups & Tasks", href: "/partnership/tasks" }, { label: "Documents", href: "/partnership/documents" }, { label: "Profile", href: "/partnership/profile" },
    ]);
    expect(PARTNERSHIP_HEAD_NAV).toEqual([
      { label: "Team", href: "/partnership/head/team" }, { label: "University Master", href: "/partnership/universities" },
      { label: "Partnership Pipeline", href: "/partnership/pipeline" }, { label: "Meetings", href: "/partnership/meetings" }, // upc-009
      { label: "University Visits", href: "/partnership/visits" }, { label: "Visit approvals", href: "/partnership/visits/approvals" },
      { label: "MoU & Agreements", href: "/partnership/agreements" }, { label: "Follow-ups & Tasks", href: "/partnership/tasks" },
      { label: "Documents", href: "/partnership/documents" },
      { label: "Message templates", href: "/partnership/head/templates" },
    ]);
  });

  it("gives the Super Admin the visit approval queue (upc-010 VS4 fallback)", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Visit Approvals", href: "/partnership/visits/approvals" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Follow-ups & Tasks", href: "/partnership/tasks" }); // upc-020 QA-03
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Meetings", href: "/partnership/meetings" }); // upc-009 MG14
  });

  it("gives the Super Admin and Overseas Admin a Partnership managers entry", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership managers", href: "/admin/partnership-managers" });
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "Partnership managers", href: "/overseas/admin/partnership-managers" });
    expect(PORTAL_NAV["it/admin"].some((x) => x.href.includes("partnership"))).toBe(false);
  });
});
