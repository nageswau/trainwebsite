import { describe, expect, it } from "vitest";

import { cellText, managerTargetHref, managerTargetUrl, type TargetKpiDef } from "@/lib/partnershipTargets";

const tracked: TargetKpiDef = { key: "proposals", label: "Proposals", definition: "", tracked: true };
const untracked: TargetKpiDef = { key: "meetings", label: "Meetings", definition: "", tracked: false };

describe("upc-021 targets words", () => {
  it("shows actual / target with the achievement when there is one", () => {
    expect(cellText(tracked, { key: "proposals", target: 4, achieved: 1, percent: 25 }, "current")).toBe("1 / 4 · 25%");
    expect(cellText(tracked, { key: "proposals", target: null, achieved: 3, percent: null }, "past")).toBe("3 / —");
  });

  it("never shows 0 for a KPI that is not tracked, nor an actual before the month starts", () => {
    expect(cellText(untracked, { key: "meetings", target: 2, achieved: null, percent: null }, "current")).toBe("Not tracked / 2");
    expect(cellText(tracked, { key: "proposals", target: 5, achieved: null, percent: null }, "future")).toBe("Not started / 5");
  });

  it("builds the API and page addresses for one manager's month", () => {
    expect(managerTargetUrl("m1", "2026-10")).toBe("/api/v1/partnership/targets/m1?month=2026-10");
    expect(managerTargetHref("m1", "2026-10")).toBe("/partnership/targets/m1?month=2026-10");
  });
});
