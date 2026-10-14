import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { healthQuery, healthUrl, measureText, type HealthFactor } from "@/lib/managementHealth";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const base: HealthFactor = {
  key: "revenue", label: "Revenue", tier: "finance", weight: 15, unit: "inr", current: "150000.00", previous: "100000.00", change: 50,
  score: 100, rag: "green", points: 15, note: null,
}; // prettier-ignore

describe("mgmt-030 managementHealth", () => {
  it("reads the month from the address, dropping malformed or repeated values", () => {
    expect(healthQuery({ month: "2026-09" })).toEqual({ month: "2026-09" });
    expect(healthQuery({ month: "2026-13" })).toEqual({ month: "" });
    expect(healthQuery({ month: ["2026-09", "2026-08"] })).toEqual({ month: "" });
  });

  it("builds the API url with only the month set", () => {
    expect(healthUrl({ month: "" })).toBe("/api/v1/management/health");
    expect(healthUrl({ month: "2026-09" })).toBe("/api/v1/management/health?month=2026-09");
  });

  it("writes each factor's measure from the API's figures (BH11)", () => {
    expect(measureText(base)).toBe("₹1,50,000.00 against ₹1,00,000.00 (+50.0%)");
    expect(measureText({ ...base, key: "applications", unit: "count", current: "8", previous: "10", change: -20 })).toBe("8 against 10 (−20.0%)");
    expect(measureText({ ...base, unit: "count", current: "3", previous: "0", change: null })).toBe("3 against 0 (new this month)");
    expect(measureText({ ...base, key: "profit", unit: "percent", current: "12.5", previous: "8.0", change: null })).toBe("Margin 12.5% (8.0% the month before)");
    expect(measureText({ ...base, key: "profit", unit: "percent", current: "12.5", previous: null, change: null })).toBe("Margin 12.5%");
    expect(measureText({ ...base, key: "marketing_roi", unit: "percent", current: "40.0", previous: null, change: null })).toBe("ROI 40.0%");
    expect(measureText({ ...base, key: "productivity", current: "50000.00", previous: "40000.00", change: 25 })).toBe("₹50,000.00 per head against ₹40,000.00 (+25.0%)");
    expect(measureText({ ...base, key: "expenses", current: "20000.00", previous: "10000.00", change: 5 })).toBe("₹20,000.00 against ₹10,000.00: grew 5.0 points faster than revenue");
    expect(measureText({ ...base, key: "expenses", current: "9000.00", previous: "10000.00", change: -12.5 })).toBe("₹9,000.00 against ₹10,000.00: grew 12.5 points slower than revenue");
    expect(measureText({ ...base, score: null, points: null, rag: null, note: "No revenue in either month" })).toBe("No revenue in either month");
  });

  it("makes the health entry live for the operational tier and links the super admin's sidebar (BH13)", () => {
    const entry = MANAGEMENT_PILLARS.find((p) => p.title === "Business Intelligence")!.entries.find((e) => e.label === "Business health score");
    expect(entry).toEqual({ label: "Business health score", item: "mgmt-030", tier: "operational", href: "/management/health" });
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual({ label: "Business health score", href: "/management/health" });
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).not.toContainEqual({ label: "Business health score", href: "/management/health" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management business health", href: "/management/health" });
  });
});
