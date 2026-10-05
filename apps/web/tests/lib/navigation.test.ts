import { describe, expect, it } from "vitest";

import { agentNavFor, PORTAL_NAV } from "@/lib/navigation";

describe("agentNavFor (AGN-002, AGN-003)", () => {
  const nav = PORTAL_NAV["overseas/agent"];

  it("hides Team and Commissions from staff", () => {
    const hrefs = agentNavFor(nav, "staff").map((item) => item.href);
    expect(hrefs).not.toContain("/overseas/agent/team");
    expect(hrefs).not.toContain("/overseas/agent/commissions");
    expect(hrefs).toContain("/overseas/agent/students");
  });

  it("keeps the full nav for Masters and unknown roles", () => {
    expect(agentNavFor(nav, "master")).toEqual(nav);
    expect(agentNavFor(nav, null)).toEqual(nav);
  });

  it("hides Reports from staff unless their Reports permission is on (AGN-003)", () => {
    const off = agentNavFor(nav, "staff", { can_verify_documents: true, can_view_reports: false }).map((item) => item.href);
    expect(off).not.toContain("/overseas/agent/reports");
    expect(off).toContain("/overseas/agent/documents");
    expect(agentNavFor(nav, "staff").map((item) => item.href)).not.toContain("/overseas/agent/reports");
    const on = agentNavFor(nav, "staff", { can_verify_documents: false, can_view_reports: true }).map((item) => item.href);
    expect(on).toContain("/overseas/agent/reports");
    expect(on).not.toContain("/overseas/agent/team");
  });

  it("never limits a Master's nav by permissions", () => {
    expect(agentNavFor(nav, "master", { can_verify_documents: false, can_view_reports: false })).toEqual(nav);
  });
});
