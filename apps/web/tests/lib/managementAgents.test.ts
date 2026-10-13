import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { agentsQuery, agentsUrl } from "@/lib/managementAgents";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("mgmt-021 managementAgents", () => {
  it("reads the period from the address, dropping malformed or repeated values", () => {
    expect(agentsQuery({ from: "2026-05-01", to: "2026-05-31" })).toEqual({ from: "2026-05-01", to: "2026-05-31" });
    expect(agentsQuery({ from: "2026-02-30", to: "31-05-2026" })).toEqual({ from: "", to: "" });
    expect(agentsQuery({ from: ["2026-05-01", "2026-05-02"] })).toEqual({ from: "", to: "" });
  });

  it("builds the API url with only the values set", () => {
    expect(agentsUrl({ from: "", to: "" })).toBe("/api/v1/management/agents");
    expect(agentsUrl({ from: "2026-05-01", to: "" })).toBe("/api/v1/management/agents?from=2026-05-01");
    expect(agentsUrl({ from: "2026-05-01", to: "2026-05-31" })).toBe("/api/v1/management/agents?from=2026-05-01&to=2026-05-31");
  });

  it("makes the Agents entry live for the operational tier, and links the super admin's sidebar (AN14)", () => {
    const entry = MANAGEMENT_PILLARS.find((p) => p.title === "Partnerships")!.entries.find((e) => e.label === "Agents");
    expect(entry).toEqual({ label: "Agents", item: "mgmt-021", tier: "operational", href: "/management/agents" });
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual({ label: "Agents", href: "/management/agents" });
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).not.toContainEqual({ label: "Agents", href: "/management/agents" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management agent figures", href: "/management/agents" });
  });
});
