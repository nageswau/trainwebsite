import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { FUNNEL_DIMENSIONS, funnelQuery, funnelUrl } from "@/lib/managementFunnel";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("mgmt-016 managementFunnel", () => {
  it("reads the period and the breakdown from the address, dropping malformed, unknown or repeated values", () => {
    expect(funnelQuery({ from: "2026-05-01", to: "2026-05-31", by: "country" })).toEqual({ from: "2026-05-01", to: "2026-05-31", by: "country" });
    expect(funnelQuery({ from: "2026-02-30", to: "31-05-2026", by: "city" })).toEqual({ from: "", to: "", by: "" });
    expect(funnelQuery({ from: ["2026-05-01", "2026-05-02"], by: ["school", "agent"] })).toEqual({ from: "", to: "", by: "" });
  });

  it("builds the API url with only the values set", () => {
    expect(funnelUrl({ from: "", to: "", by: "" })).toBe("/api/v1/management/funnel");
    expect(funnelUrl({ from: "2026-05-01", to: "", by: "" })).toBe("/api/v1/management/funnel?from=2026-05-01");
    expect(funnelUrl({ from: "2026-05-01", to: "2026-05-31", by: "bdm" })).toBe("/api/v1/management/funnel?from=2026-05-01&to=2026-05-31&by=bdm");
  });

  it("offers §11's nine breakdowns in source order", () => {
    expect(FUNNEL_DIMENSIONS.map((d) => d.label)).toEqual(["Country", "Course", "Agent", "School", "Counselor", "Marketing source", "BDM", "Intake", "Branch"]);
  });

  it("makes the Student funnel entry live for the operational tier, and links the super admin's sidebar", () => {
    const entry = MANAGEMENT_PILLARS.find((p) => p.title === "Students")!.entries.find((e) => e.label === "Student funnel");
    expect(entry).toEqual({ label: "Student funnel", item: "mgmt-016", tier: "operational", href: "/management/funnel" });
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual({ label: "Student funnel", href: "/management/funnel" });
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).not.toContainEqual({ label: "Student funnel", href: "/management/funnel" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management student funnel", href: "/management/funnel" });
  });
});
