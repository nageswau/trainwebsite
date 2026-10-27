import { describe, expect, it } from "vitest";

import { navForPermissions, PORTAL_NAV, SUPER_ADMIN_NAV, TELECALLER_MANAGER_NAV, type NavItem } from "@/lib/navigation";

// nehn-006 (DEC-SCOPE-295): a sidebar item backed by a catalogue resource carries its key and goes once `<resource>.view` is missing.
const tagged = (nav: NavItem[]) => nav.filter((item) => item.resource).map((item) => [item.href, item.resource]);

describe("nehn-006 permission-driven navigation", () => {
  it("tags only the items whose page a catalogue resource gates", () => {
    expect(tagged(PORTAL_NAV["it/admin"])).toEqual([["/it/admin/payments", "payments"], ["/it/admin/telecaller-reports", "reports.telecaller"]]);
    expect(tagged(PORTAL_NAV["overseas/admin"])).toEqual([["/overseas/admin/payments", "payments"], ["/overseas/admin/telecaller-reports", "reports.telecaller"]]);
    expect(tagged(PORTAL_NAV["it/coordinator"])).toEqual([["/it/coordinator/certificates", "certificates"]]);
    expect(tagged(TELECALLER_MANAGER_NAV)).toEqual([["/telecaller/manager/reports", "reports.telecaller"]]);
    // super_admin holds every key, so its nav never needs the lookup; the IT admin's Certificates keeps its own role check.
    expect(tagged(SUPER_ADMIN_NAV)).toEqual([]);
    expect(PORTAL_NAV["it/admin"].find((item) => item.href === "/it/admin/certificates")?.resource).toBeUndefined();
  });

  it("drops a tagged item without its view grant and keeps everything else", () => {
    const nav = PORTAL_NAV["it/admin"];
    const filtered = navForPermissions(nav, ["reports.telecaller.view", "payments.add"]);
    expect(filtered.map((item) => item.href)).not.toContain("/it/admin/payments");
    expect(filtered.map((item) => item.href)).toContain("/it/admin/telecaller-reports");
    expect(filtered).toHaveLength(nav.length - 1);
  });

  it("leaves the nav as it is while the set is unknown", () => {
    const nav = PORTAL_NAV["it/coordinator"];
    expect(navForPermissions(nav, null)).toBe(nav);
    expect(navForPermissions(nav, [])).toEqual(nav.filter((item) => item.href !== "/it/coordinator/certificates"));
  });
});
