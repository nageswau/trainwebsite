import { describe, expect, it } from "vitest";
import { agentNavFor, PORTAL_NAV } from "@/lib/navigation";

// AGN-004 G2/G3 (identical to AGN-002): an agency's staff lose Team and Commissions from the sidebar.
describe("agentNavFor", () => {
  const nav = PORTAL_NAV["overseas/agent"];

  it("hides Team and Commissions from staff", () => {
    expect(agentNavFor(nav, "staff").map((i) => i.href)).toEqual([
      "/overseas/agent/dashboard",
      "/overseas/agent/students",
      "/overseas/agent/applications",
      "/overseas/agent/documents",
      "/overseas/agent/reports",
    ]);
  });

  it("leaves a Master's nav unchanged", () => {
    expect(agentNavFor(nav, "master")).toEqual(nav);
    expect(agentNavFor(nav, null)).toEqual(nav);
    expect(agentNavFor(nav)).toEqual(nav);
  });
});
