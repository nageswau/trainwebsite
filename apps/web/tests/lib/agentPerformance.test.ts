import { describe, expect, it } from "vitest";

import { funnelStages, isPerformance, type AgentPerformance } from "@/lib/agentPerformance";

const zeroFunnel = { students: 0, applications: 0, submitted: 0, offers: 0, visa: 0, enrolled: 0 };
const zeroCounts = { students: 0, applications: 0, offers: 0, visa_applications: 0, visa_approvals: 0, enrollments: 0, funnel: zeroFunnel };

describe("agentPerformance (AGN-019)", () => {
  it("lists the six stages in funnel order with the share of students", () => {
    const stages = funnelStages({ students: 8, applications: 7, submitted: 6, offers: 5, visa: 3, enrolled: 2 });
    expect(stages.map((s) => s.label)).toEqual(["Students", "Applications", "Submitted", "Offers", "Visa", "Enrolled"]);
    expect(stages.map((s) => s.count)).toEqual([8, 7, 6, 5, 3, 2]);
    expect(stages.map((s) => s.percent)).toEqual([100, 88, 75, 63, 38, 25]);
  });

  it("has no percentage when there are no students (never NaN)", () => {
    expect(funnelStages(zeroFunnel).every((s) => s.percent === null)).toBe(true);
  });

  it("recognises a performance body and nothing else", () => {
    const body: AgentPerformance = { date_from: null, date_to: null, rows: [], unassigned: null, total: zeroCounts, as_of: "2026-10-03T10:00:00Z" };
    expect(isPerformance(body)).toBe(true);
    for (const bad of [null, {}, { rows: [] }, { ...body, total: null }, "x"]) expect(isPerformance(bad)).toBe(false);
  });
});
