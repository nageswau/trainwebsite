import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ManagementPlanProgress from "@/components/ManagementPlanProgress";
import ManagementPlans from "@/components/ManagementPlans";
import type { PlanProgress, PlanSummary } from "@/lib/managementPlans";

const VERTICALS = [{ key: "abroad", label: "Abroad Education" }, { key: "it", label: "IT Training" }, { key: "other", label: "Other" }];

function progress(overrides: Partial<PlanProgress> = {}): PlanProgress {
  return {
    month: "2026-10", label: "October 2026", state: "running", start: "2026-10-01", end: "2026-10-31", free_text: { total: 4, done: 1 },
    rows: [
      { item_id: "i1", vertical: "abroad", text: "Recruit 30 new agents", kpi: "agents", kpi_label: "New agents", unit: "count", target: "30.00", actual: "27", achievement: 90 },
      { item_id: "i2", vertical: "other", text: "Revenue ₹50L", kpi: "revenue", kpi_label: "Revenue (₹)", unit: "inr", target: "5000000.00", actual: "4100000.00", achievement: 82 },
    ],
    ...overrides,
  };
}

afterEach(cleanup);

describe("mgmt-026 target vs actual", () => {
  it("shows each KPI item's department, target, actual and achievement (§26)", () => {
    render(<ManagementPlanProgress progress={progress()} error="" verticals={VERTICALS} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell").map((c) => c.textContent));
    const headers = within(screen.getByRole("table")).getAllByRole("rowheader").map((h) => h.textContent);
    expect(headers).toEqual(["Abroad Education", "Other"]);
    expect(rows[0]).toEqual(["Recruit 30 new agents", "New agents", "30", "27", "90%"]);
    expect(rows[1]).toEqual(["Revenue ₹50L", "Revenue (₹)", "₹50,00,000", "₹41,00,000", "82%"]);
    expect(screen.getByText(/month to date/i)).toBeTruthy();
    expect(screen.getByText("Other plan items: 1 of 4 done.")).toBeTruthy();
  });

  it("says when there are no KPI items, and when the month has not started", () => {
    render(<ManagementPlanProgress progress={progress({ rows: [], state: "upcoming", start: "2026-11-01", free_text: { total: 0, done: 0 } })} error="" verticals={VERTICALS} />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText(/No KPI items yet/)).toBeTruthy();
    expect(screen.getByText(/starts on 1 Nov 2026/)).toBeTruthy();
  });

  it("shows the read error instead of the table", () => {
    render(<ManagementPlanProgress progress={null} error="Target vs actual is unavailable right now." verticals={VERTICALS} />);
    expect(screen.getByRole("alert").textContent).toBe("Target vs actual is unavailable right now.");
  });
});

describe("mgmt-026 plan list", () => {
  const plan: PlanSummary = {
    id: "p1", month: "2026-11", status: "active", label: "November 2026", item_count: 16, kpi_count: 9, done_count: 2,
    created_by: { id: "u1", full_name: "Arjun Partner", role: "partner" }, updated_at: "2026-10-01T04:30:00Z",
  };

  it("links each month's plan with its status and counts", () => {
    render(<ManagementPlans data={{ items: [plan] }} error="" />);
    expect(screen.getByRole("link", { name: "November 2026" }).getAttribute("href")).toBe("/management/plans/2026-11");
    const cells = within(screen.getAllByRole("row")[1]).getAllByRole("cell").map((c) => c.textContent);
    expect(cells).toEqual(["Active", "16", "9", "2 of 7"]);
  });

  it("has an empty state", () => {
    render(<ManagementPlans data={{ items: [] }} error="" />);
    expect(screen.getByText("No plans yet. Plan a month to get started.")).toBeTruthy();
  });
});
