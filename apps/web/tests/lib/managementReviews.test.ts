import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { finishedMonths, formatPercent, inrOrNone, reviewHref } from "@/lib/managementReviews";

describe("mgmt-032 review helpers", () => {
  it("formats money and none", () => {
    expect(inrOrNone("120000.00")).toBe("₹1,20,000.00");
    expect(inrOrNone(null)).toBe("—");
  });

  it("formats a percentage and none", () => {
    expect(formatPercent(12.5)).toBe("12.5%");
    expect(formatPercent("33.33")).toBe("33.33%");
    expect(formatPercent(null)).toBe("—");
  });

  it("lists the finished months newest first, skipping reviewed ones", () => {
    expect(finishedMonths("2026-10-14", ["2026-08"], 4)).toEqual(["2026-09", "2026-07", "2026-06"]);
    expect(finishedMonths("2026-01-01", [], 2)).toEqual(["2025-12", "2025-11"]);
  });

  it("links a month", () => {
    expect(reviewHref("2026-09")).toBe("/management/reviews/2026-09");
  });

  it("puts the live BI entry in the partners' sidebar only", () => {
    const entry = MANAGEMENT_PILLARS.flatMap((p) => p.entries).find((e) => e.item === "mgmt-032");
    expect(entry).toEqual({ label: "Monthly business review", item: "mgmt-032", tier: "partner_only", href: "/management/reviews" });
    const link = { label: "Monthly business review", href: "/management/reviews" };
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual(link);
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).not.toContainEqual(link);
    expect(managementNavFor({ operational: true, finance: false, partner_only: false })).not.toContainEqual(link);
  });
});
