import { describe, expect, it } from "vitest";

import { achievementClass, formatAchievement, formatTarget, groupByVertical, isMonthKey, monthLabel, monthsBetween, planHref, type PlanItem } from "@/lib/managementPlans";

const VERTICALS = [{ key: "abroad", label: "Abroad Education" }, { key: "it", label: "IT Training" }, { key: "school", label: "Schools" }];

function item(overrides: Partial<PlanItem> = {}): PlanItem {
  return { id: "i1", vertical: "abroad", text: "Recruit 30 new agents", kpi: "agents", target: "30.00", done: false, task_count: 0, updated_at: "2026-10-01T04:30:00Z", ...overrides };
}

describe("mgmt-026 plan helpers", () => {
  it("accepts only a YYYY-MM month key", () => {
    expect(isMonthKey("2026-10")).toBe(true);
    for (const bad of ["2026-13", "2026-1", "next", "2026-10-01", ""]) expect(isMonthKey(bad)).toBe(false);
  });

  it("labels a month and links its plan", () => {
    expect(monthLabel("2026-10")).toBe("October 2026");
    expect(planHref("2026-11")).toBe("/management/plans/2026-11");
  });

  it("lists the months of the planning window, across a year end", () => {
    expect(monthsBetween("2026-11", "2027-02")).toEqual(["2026-11", "2026-12", "2027-01", "2027-02"]);
    expect(monthsBetween("2026-10", "2026-10")).toEqual(["2026-10"]);
  });

  it("formats count targets as whole numbers and revenue in rupees", () => {
    expect(formatTarget("1500.00", "count")).toBe("1,500");
    expect(formatTarget("5000000.00", "inr")).toBe("₹50,00,000");
    expect(formatTarget("1234.50", "inr")).toBe("₹1,234.50");
  });

  it("shows achievement as a whole per cent with a status colour", () => {
    expect(formatAchievement(90)).toBe("90%");
    expect(achievementClass(100)).toBe("status");
    expect(achievementClass(75)).toBe("status pending");
    expect(achievementClass(74)).toBe("status error");
  });

  it("groups items by vertical in the catalogue's order, keeping empty verticals", () => {
    const groups = groupByVertical([item({ id: "a", vertical: "school" }), item({ id: "b" }), item({ id: "c", vertical: "school" })], VERTICALS);
    expect(groups.map((g) => [g.key, g.items.map((i) => i.id)])).toEqual([["abroad", ["b"]], ["it", []], ["school", ["a", "c"]]]);
  });
});
