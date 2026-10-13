import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { recruitmentRevenueQuery, recruitmentRevenueUrl } from "@/lib/managementRecruitmentRevenue";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("mgmt-008 managementRecruitmentRevenue", () => {
  it("reads the month and period from the address, dropping malformed values", () => {
    expect(recruitmentRevenueQuery({ month: "2026-05", period: "year" })).toEqual({ month: "2026-05", period: "year" });
    expect(recruitmentRevenueQuery({ month: "2026-5", period: "week" })).toEqual({ month: "", period: "month" });
    expect(recruitmentRevenueQuery({ month: ["2026-05", "2026-06"] })).toEqual({ month: "", period: "month" });
  });

  it("builds the API url", () => {
    expect(recruitmentRevenueUrl({ month: "", period: "month" })).toBe("/api/v1/management/revenue/recruitment");
    expect(recruitmentRevenueUrl({ month: "2026-05", period: "month" })).toBe("/api/v1/management/revenue/recruitment?month=2026-05&period=month");
    expect(recruitmentRevenueUrl({ month: "", period: "year" })).toBe("/api/v1/management/revenue/recruitment?period=year");
  });

  it("makes the Finance entry live for the finance tier, and gives the super admin a KPI link in their own sidebar (RR11)", () => {
    const finance = MANAGEMENT_PILLARS.find((p) => p.title === "Finance")!;
    expect(finance.entries.find((e) => e.item === "mgmt-008")).toEqual({ label: "Recruitment revenue", item: "mgmt-008", tier: "finance", href: "/management/revenue/recruitment" });
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).toContainEqual({ label: "Recruitment revenue", href: "/management/revenue/recruitment" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruitment KPIs", href: "/management/revenue/recruitment" });
  });
});
