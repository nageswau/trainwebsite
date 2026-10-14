import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { schoolsQuery, schoolsUrl } from "@/lib/managementSchools";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("mgmt-022 managementSchools", () => {
  it("reads the period from the address, dropping malformed or repeated values", () => {
    expect(schoolsQuery({ from: "2026-05-01", to: "2026-05-31" })).toEqual({ from: "2026-05-01", to: "2026-05-31" });
    expect(schoolsQuery({ from: "2026-02-30", to: "31-05-2026" })).toEqual({ from: "", to: "" });
    expect(schoolsQuery({ from: ["2026-05-01", "2026-05-02"] })).toEqual({ from: "", to: "" });
  });

  it("builds the API url with only the values set", () => {
    expect(schoolsUrl({ from: "", to: "" })).toBe("/api/v1/management/schools");
    expect(schoolsUrl({ from: "2026-05-01", to: "" })).toBe("/api/v1/management/schools?from=2026-05-01");
    expect(schoolsUrl({ from: "2026-05-01", to: "2026-05-31" })).toBe("/api/v1/management/schools?from=2026-05-01&to=2026-05-31");
  });

  it("makes Schools live for the operational tier, School revenue for the finance tier, and links the super admin's sidebar", () => {
    const schools = MANAGEMENT_PILLARS.find((p) => p.title === "Partnerships")!.entries.find((e) => e.label === "Schools");
    expect(schools).toEqual({ label: "Schools", item: "mgmt-022", tier: "operational", href: "/management/schools" });
    const money = { label: "School revenue & contracts", href: "/management/schools#school-money" };
    const accountant = managementNavFor({ operational: false, finance: true, partner_only: false });
    expect(accountant).toContainEqual(money);
    expect(accountant).not.toContainEqual({ label: "Schools", href: "/management/schools" });
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual({ label: "Schools", href: "/management/schools" });
    expect(managementNavFor({ operational: true, finance: false, partner_only: false })).not.toContainEqual(money);
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management school figures", href: "/management/schools" });
  });
});
