import { describe, expect, it } from "vitest";

import {
  bdmPath, bdmPerformanceUrl, hierarchyUrl, isBdmPerformance, isBdmType, isHierarchy, isPerformance, performancePath, performanceUrl,
  periodText, readFilters, typePath, typeTotals, valueText,
} from "@/lib/bdmPerformance";

const M1 = "11111111-1111-4111-8111-111111111111";

describe("bdm-024 performance lib", () => {
  it("reads only well-formed filters from the URL; a manager only for super_admin", () => {
    expect(readFilters({ from: "2026-10-01", to: "2026-10-31", manager: M1 }, true)).toEqual({ from: "2026-10-01", to: "2026-10-31", manager: M1 });
    expect(readFilters({ from: "1 Oct", to: "2026-10-31<script>", manager: "nope" }, true)).toEqual({ from: undefined, to: undefined, manager: undefined });
    expect(readFilters({ manager: M1 }, false).manager).toBeUndefined();
  });

  it("builds the API URLs with the period, the type and the API's manager parameter", () => {
    expect(performanceUrl({})).toBe("/api/v1/bdm/manager/performance");
    expect(performanceUrl({ from: "2026-10-01", to: "2026-10-31", manager: M1 }, "agent")).toBe(
      `/api/v1/bdm/manager/performance?from=2026-10-01&to=2026-10-31&type=agent&manager_user_id=${M1}`);
    expect(bdmPerformanceUrl("b1", { from: "2026-10-01", manager: M1 })).toBe("/api/v1/bdm/manager/performance/bdms/b1?from=2026-10-01");
    expect(hierarchyUrl({ manager: M1, from: "2026-10-01" })).toBe(`/api/v1/bdm/manager/hierarchy?manager_user_id=${M1}`);
  });

  it("keeps the period (and super_admin's manager) on every drill-down link", () => {
    const f = { from: "2026-10-01", to: "2026-10-31", manager: M1 };
    expect(performancePath(f)).toBe(`/bdm/manager/performance?from=2026-10-01&to=2026-10-31&manager=${M1}`);
    expect(typePath("school", f)).toBe(`/bdm/manager/performance/school?from=2026-10-01&to=2026-10-31&manager=${M1}`);
    expect(bdmPath("b1", f)).toBe("/bdm/manager/performance/bdms/b1?from=2026-10-01&to=2026-10-31"); // a BDM defines its own scope
    expect(typePath("agent", {})).toBe("/bdm/manager/performance/agent");
  });

  it("says Not tracked instead of 0, and formats counts and INR the Indian way", () => {
    expect(valueText(null)).toBe("Not tracked");
    expect(valueText(0)).toBe("0");
    expect(valueText(125000)).toBe("1,25,000");
    expect(valueText("1250.5")).toBe("₹1,250.50");
    expect(valueText("0.00")).toBe("₹0.00");
  });

  it("reads one type's column of the table as the Total row of its BDM list", () => {
    const cells = (values: (number | string | null)[]) => (["agent", "school", "college"] as const).map((type, i) => ({ type, tracked: values[i] !== null, value: values[i], definition: "d" }));
    const data = { from: "a", to: "b", manager: null, type: null, bdms: [], rows: [
      { key: "P-01", label: "BDMs", cells: cells([3, 2, 3]) }, { key: "P-02", label: "Meetings", cells: cells([80, 65, 75]) },
      { key: "P-03", label: "Travel Trips", cells: cells([1, 2, 3]) }, { key: "P-04", label: "New Organizations", cells: cells([0, 0, 0]) },
      { key: "P-05", label: "MoUs", cells: cells([1, 1, 1]) }, { key: "P-06", label: "Leads", cells: cells([5, 6, 7]) },
      { key: "P-07", label: "Students", cells: cells([8, 9, 10]) }, { key: "P-08", label: "Revenue", cells: cells([null, null, "10.00"]) },
    ] };
    expect(typeTotals(data, "school")).toEqual({ meetings: 65, trips: 2, new_organizations: 0, mous: 1, leads: 6, students: 9, revenue: null });
    expect(typeTotals(data, "college").revenue).toBe("10.00");
  });

  it("names the period's inclusive dates", () => {
    expect(periodText("2026-10-01", "2026-10-31")).toBe("1 Oct 2026 – 31 Oct 2026");
  });

  it("guards the three response shapes and the type parameter", () => {
    expect(isPerformance({ from: "a", to: "b", rows: [], bdms: [] })).toBe(true);
    expect(isPerformance({ rows: [] })).toBe(false);
    expect(isBdmPerformance({ bdm: {}, totals: {}, organizations: [], trips: [] })).toBe(true);
    expect(isBdmPerformance(null)).toBe(false);
    expect(isHierarchy({ as_of: "x", types: [] })).toBe(true);
    expect(isHierarchy({ types: [] })).toBe(false);
    expect(isBdmType("agent") && !isBdmType("telecaller") && !isBdmType(undefined)).toBe(true);
  });
});
