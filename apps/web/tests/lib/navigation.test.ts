import { describe, expect, it } from "vitest";

import { agentNavFor, PORTAL_NAV } from "@/lib/navigation";

describe("agentNavFor (AGN-002)", () => {
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
});
