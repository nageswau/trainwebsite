import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { bdmDashboardHref, bdmDashboardQuery, bdmDashboardUrl } from "@/lib/managementBdm";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("mgmt-020 managementBdm", () => {
  it("reads the type and period from the address, dropping malformed or repeated values", () => {
    expect(bdmDashboardQuery({ type: "school", from: "2026-05-01", to: "2026-05-31" })).toEqual({ type: "school", from: "2026-05-01", to: "2026-05-31" });
    expect(bdmDashboardQuery({ type: "corporate", from: "2026-02-30", to: "31-05-2026" })).toEqual({ type: "agent", from: "", to: "" });
    expect(bdmDashboardQuery({ type: ["school", "college"], from: ["2026-05-01"] })).toEqual({ type: "agent", from: "", to: "" });
  });

  it("builds the API url with only the values set", () => {
    expect(bdmDashboardUrl({ type: "agent", from: "", to: "" })).toBe("/api/v1/management/bdm?type=agent");
    expect(bdmDashboardUrl({ type: "college", from: "2026-05-01", to: "2026-05-31" })).toBe("/api/v1/management/bdm?type=college&from=2026-05-01&to=2026-05-31");
  });

  it("links a tab to its type and keeps the chosen period", () => {
    expect(bdmDashboardHref({ type: "agent", from: "", to: "" }, "school")).toBe("/management/bdm?type=school");
    expect(bdmDashboardHref({ type: "agent", from: "2026-05-01", to: "2026-05-31" }, "college")).toBe("/management/bdm?type=college&from=2026-05-01&to=2026-05-31");
  });

  it("makes the Sales BDM entry live for the operational tier, and gives the super admin a link in their own sidebar (BD12)", () => {
    const sales = MANAGEMENT_PILLARS.find((p) => p.title === "Sales")!;
    expect(sales.entries.find((e) => e.item === "mgmt-020")).toEqual({ label: "BDM", item: "mgmt-020", tier: "operational", href: "/management/bdm" });
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual({ label: "BDM", href: "/management/bdm" });
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).not.toContainEqual({ label: "BDM", href: "/management/bdm" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management BDM figures", href: "/management/bdm" });
  });
});
