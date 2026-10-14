import { describe, expect, it } from "vitest";

import { drillHref, drillQuery, drillUrl, isDrillChain } from "@/lib/managementDrill";

const A = "11111111-1111-4111-8111-111111111111";
const B = "22222222-2222-4222-8222-222222222222";

describe("mgmt-033 drill-down address", () => {
  it("knows the three chains only", () => {
    expect(["abroad", "it", "recruitment"].every(isDrillChain)).toBe(true);
    expect(isDrillChain("visa")).toBe(false);
  });

  it("reads month, period, path and page, and drops anything malformed", () => {
    expect(drillQuery({ month: "2026-05", period: "year", path: `${A},none,${B}`, page: "3" })).toEqual({ month: "2026-05", period: "year", path: [A, "none", B], page: 3 });
    expect(drillQuery({ month: "2026-13", period: "week", path: `${A},x`, page: "0" })).toEqual({ month: "", period: "month", path: [], page: 1 });
    expect(drillQuery({ path: Array(8).fill(A).join(",") }).path).toEqual([]);
  });

  it("builds the API address with paging", () => {
    expect(drillUrl("it", { month: "2026-05", period: "month", path: [A, "none"], page: 2 })).toBe(`/api/v1/management/drill/it?month=2026-05&period=month&path=${A}%2Cnone&limit=25&offset=25`);
    expect(drillUrl("abroad", { month: "", period: "month", path: [], page: 1 })).toBe("/api/v1/management/drill/abroad?period=month&limit=25&offset=0");
  });

  it("builds a page address one level down, keeping the period", () => {
    expect(drillHref("recruitment", { month: "2026-05", period: "year" }, [A, B])).toBe(`/management/drill/recruitment?month=2026-05&period=year&path=${A}%2C${B}`);
    expect(drillHref("it", { month: "", period: "month" }, [], 2)).toBe("/management/drill/it?period=month&page=2");
  });
});
