import { describe, expect, it } from "vitest";

import { isUuid, orgUrl } from "@/lib/agentNetwork";
import { PORTAL_NAV } from "@/lib/navigation";

describe("AGN-022 agent network helpers", () => {
  it("accepts only a UUID as an organisation id (AC11)", () => {
    expect(isUuid("3f2b8c1e-9d4a-4b7e-8f21-0c6d5e4a3b2f")).toBe(true);
    expect(isUuid("3F2B8C1E-9D4A-4B7E-8F21-0C6D5E4A3B2F")).toBe(true);
    for (const bad of ["", "abc", "..%2Fagents", "../agents", "3f2b8c1e-9d4a-4b7e-8f21-0c6d5e4a3b2f/students"]) expect(isUuid(bad)).toBe(false);
  });

  it("builds API paths with the id encoded, so a crafted id cannot reach another route", () => {
    expect(orgUrl("a1")).toBe("/api/v1/overseas-admin/agent-orgs/a1");
    expect(orgUrl("a1", "students")).toBe("/api/v1/overseas-admin/agent-orgs/a1/students");
    expect(orgUrl("x/../agents")).toBe("/api/v1/overseas-admin/agent-orgs/x%2F..%2Fagents");
  });

  it("adds an Agent network entry after Agent deposits, leaving the existing entries in place (AC10)", () => {
    const nav = PORTAL_NAV["overseas/admin"];
    const deposits = nav.findIndex((x) => x.href === "/overseas/admin/agent-deposits");
    expect(nav[deposits + 1]).toEqual({ label: "Agent network", href: "/overseas/admin/agent-network" });
    expect(nav).toContainEqual({ label: "BDMs", href: "/overseas/admin/bdms" });
    expect(nav.filter((x) => x.label.startsWith("Agent deposits"))).toHaveLength(1);
  });
});
