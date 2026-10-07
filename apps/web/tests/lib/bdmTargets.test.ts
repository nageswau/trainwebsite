import { describe, expect, it } from "vitest";

import { achievedText, chosenMonth, isTargetSheet, monthLabel, monthOptions, parseTarget, percentText, type TargetKpi } from "@/lib/bdmTargets";

const kpi = (over: Partial<TargetKpi> = {}): TargetKpi => ({ key: "meetings", label: "Meetings", definition: "-", tracked: true, target: 30, achieved: 22, percent: 73, ...over });

describe("bdm-016 targets lib", () => {
  it("keeps a valid YYYY-MM month and replaces anything else with the current month and a note", () => {
    expect(chosenMonth("2026-09", "2026-10")).toEqual({ month: "2026-09", note: null });
    expect(chosenMonth(undefined, "2026-10")).toEqual({ month: "2026-10", note: null });
    for (const bad of ["2026-13", "2026-9", "x", "2026-10-01"]) {
      expect(chosenMonth(bad, "2026-10")).toEqual({ month: "2026-10", note: "That isn't a valid month — showing this month." });
    }
  });

  it("offers the 12 months before and after the current one, newest last", () => {
    const options = monthOptions("2026-10");
    expect(options).toHaveLength(25);
    expect([options[0].value, options[12].value, options[24].value]).toEqual(["2025-10", "2026-10", "2027-10"]);
    expect(options[12].label).toBe("October 2026");
    expect(monthOptions("2026-01")[0].value).toBe("2025-01");
  });

  it("labels a month in words", () => {
    expect(monthLabel("2026-02")).toBe("February 2026");
  });

  it("writes achieved and percent without ever faking a number", () => {
    expect(achievedText(kpi(), "current")).toBe("22");
    expect(achievedText(kpi({ tracked: false, achieved: null }), "current")).toBe("Not tracked");
    expect(achievedText(kpi({ achieved: null }), "future")).toBe("Month not started");
    expect(percentText(kpi())).toBe("73%");
    expect(percentText(kpi({ percent: null }))).toBe("—");
  });

  it("parses a target input: blank clears, a whole number 0-100000 is kept, anything else is refused", () => {
    expect(parseTarget("")).toEqual({ ok: true, value: null });
    expect(parseTarget(" 30 ")).toEqual({ ok: true, value: 30 });
    expect(parseTarget("0")).toEqual({ ok: true, value: 0 });
    for (const bad of ["-1", "2.5", "1e3", "100001", "abc"]) expect(parseTarget(bad).ok).toBe(false);
  });

  it("recognises a target sheet", () => {
    expect(isTargetSheet({ month: "2026-10", month_status: "current", kpis: [] })).toBe(true);
    expect(isTargetSheet({ detail: "nope" })).toBe(false);
    expect(isTargetSheet(null)).toBe(false);
  });
});
