import { describe, expect, it } from "vitest";
import { agentNavFor, PORTAL_NAV } from "@/lib/navigation";

// AGN-004 G2/G3 (identical to AGN-002): an agency's staff lose Team and Commissions from the sidebar.
describe("agentNavFor", () => {
  const nav = PORTAL_NAV["overseas/agent"];

  // AGN-003 (DEC-SCOPE-044 P1, reconciled on merging `main`): Reports is also off for staff until their Master switches it on.
  it("hides Team and Commissions from staff", () => {
    expect(agentNavFor(nav, "staff", { can_verify_documents: false, can_view_reports: true }).map((i) => i.href)).toEqual([
      "/overseas/agent/dashboard",
      "/overseas/agent/students",
      "/overseas/agent/applications",
      "/overseas/agent/documents",
      "/overseas/agent/reports",
    ]);
    expect(agentNavFor(nav, "staff").map((i) => i.href)).toEqual([
      "/overseas/agent/dashboard",
      "/overseas/agent/students",
      "/overseas/agent/applications",
      "/overseas/agent/documents",
    ]);
  });

  it("leaves a Master's nav unchanged", () => {
    expect(agentNavFor(nav, "master")).toEqual(nav);
    expect(agentNavFor(nav, null)).toEqual(nav);
    expect(agentNavFor(nav)).toEqual(nav);
  });
});
