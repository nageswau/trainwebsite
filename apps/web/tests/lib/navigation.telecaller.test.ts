import { describe, expect, it } from "vitest";

import { PORTAL_NAV, ROLE_DASHBOARD_PATH, SUPER_ADMIN_NAV, TELECALLER_MANAGER_NAV, TELECALLER_NAV, TELECALLER_SIGN_IN } from "@/lib/navigation";

describe("tel-001 navigation", () => {
  it("lands each telecaller role on its own page (AC3)", () => {
    expect(ROLE_DASHBOARD_PATH.telecaller).toBe("/telecaller/dashboard");
    expect(ROLE_DASHBOARD_PATH.telecaller_manager).toBe("/telecaller/manager/team");
  });

  it("has a telecaller nav, a manager nav and the sign-in chooser path", () => {
    expect(TELECALLER_NAV.map((x) => x.href)).toEqual(["/telecaller/dashboard", "/telecaller/profile"]);
    // tel-002 adds the catalogue pages after Team; tel-022 adds Targets after Team; tel-007 Lead assignment and Distribution rules
    // after Team; tel-012 the content library at the end.
    expect(TELECALLER_MANAGER_NAV.map((x) => x.href)).toEqual([
      "/telecaller/manager/team", "/telecaller/manager/assignment", "/telecaller/manager/distribution", "/telecaller/manager/targets",
      "/telecaller/manager/products", "/telecaller/manager/campaigns", "/telecaller/manager/scripts", "/telecaller/manager/templates",
      "/telecaller/manager/brochures",
    ]);
    expect(TELECALLER_SIGN_IN).toBe("/telecaller/sign-in");
  });

  it("gives each admin a Telecallers entry", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Telecallers", href: "/admin/telecallers" });
    expect(PORTAL_NAV["it/admin"]).toContainEqual({ label: "Telecallers", href: "/it/admin/telecallers" });
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "Telecallers", href: "/overseas/admin/telecallers" });
  });
});
