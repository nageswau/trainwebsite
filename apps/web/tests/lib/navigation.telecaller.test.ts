import { describe, expect, it } from "vitest";

import { PORTAL_NAV, ROLE_DASHBOARD_PATH, SUPER_ADMIN_NAV, TELECALLER_MANAGER_NAV, TELECALLER_NAV, TELECALLER_SIGN_IN } from "@/lib/navigation";

describe("tel-001 navigation", () => {
  it("lands each telecaller role on its own page (AC3)", () => {
    expect(ROLE_DASHBOARD_PATH.telecaller).toBe("/telecaller/dashboard");
    expect(ROLE_DASHBOARD_PATH.telecaller_manager).toBe("/telecaller/manager/team");
  });

  it("has a telecaller nav, a manager nav and the sign-in chooser path", () => {
    // tel-008 adds My Leads after Dashboard, and the manager's Leads after Team; tel-011 Follow-ups after them.
    // tel-020 adds Notifications before Profile.
    expect(TELECALLER_NAV.map((x) => x.href)).toEqual(["/telecaller/dashboard", "/telecaller/leads", "/telecaller/follow-ups", "/telecaller/meeting-requests", "/telecaller/notifications", "/telecaller/profile"]);
    // tel-002 adds the catalogue pages after Team; tel-022 Targets after Team; tel-007 Lead assignment and Distribution rules after
    // Leads; tel-006 Lead import after them; tel-023 Performance after Targets; tel-024 Reports after it; tel-020 Alert settings after Reports; tel-012 the content
    // library at the end.
    expect(TELECALLER_MANAGER_NAV.map((x) => x.href)).toEqual([
      "/telecaller/manager/team", "/telecaller/manager/leads", "/telecaller/manager/follow-ups", "/telecaller/manager/assignment", "/telecaller/manager/distribution",
      "/telecaller/manager/imports", "/telecaller/manager/targets", "/telecaller/manager/performance", "/telecaller/manager/reports", "/telecaller/manager/alerts", "/telecaller/manager/products", "/telecaller/manager/campaigns",
      "/telecaller/manager/scripts",
      "/telecaller/manager/templates", "/telecaller/manager/brochures",
    ]);
    expect(TELECALLER_SIGN_IN).toBe("/telecaller/sign-in");
  });

  it("gives each admin a Telecallers entry", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Telecallers", href: "/admin/telecallers" });
    expect(PORTAL_NAV["it/admin"]).toContainEqual({ label: "Telecallers", href: "/it/admin/telecallers" });
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "Telecallers", href: "/overseas/admin/telecallers" });
  });
});
