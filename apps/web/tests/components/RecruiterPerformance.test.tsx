import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import RecruiterPerformancePanel from "@/components/RecruiterPerformancePanel";
import {
  FIGURES, PERFORMANCE_PATH, PERFORMANCE_UNAVAILABLE, csvUrl, formatFigure, performanceError, performanceParams, performanceQuery,
  type Performance, type PerformanceRow,
} from "@/lib/recruiterPerformance";

afterEach(cleanup);

const figures = (over: Partial<PerformanceRow> = {}): Omit<PerformanceRow, "user_id" | "full_name" | "active" | "status"> => ({
  recruiter_leads: 3, active_companies: 2, requirements: 4, candidates_sourced: 10, profiles_shared: 6, interviews: 4, selected: 2, joined: 1,
  selection_pct: 20, joining_pct: 50, profile_to_interview: 0.67, interview_to_selection: 0.5, selection_to_joining: 0.5,
  avg_closure_days: 12.5, requirements_closed: 2, ...over,
});
const row = (id: string | null, name: string, over: Partial<PerformanceRow> = {}): PerformanceRow => ({
  user_id: id, full_name: name, active: true, status: id ? "Active" : "", ...figures(over),
});
const performance = (over: Partial<Performance> = {}): Performance => ({
  date_from: "2026-10-01", date_to: "2026-10-11", recruiter: null,
  items: [row("r-1", "Asha"), row("r-2", "Ravi", { active: false, status: "Inactive", selection_pct: null }), row(null, "Unassigned")],
  totals: row(null, "Total", { recruiter_leads: 9 }), ...over,
});
const params = { from: "2026-10-01", to: "2026-10-11" };

describe("recruiterPerformance lib (rec-033 PF3/PF8)", () => {
  it("lists the fifteen §24 figures in the source's order", () => {
    expect(FIGURES.map((f) => f.label)).toEqual([
      "Recruiter Leads", "Active Companies", "Requirements", "Candidates Sourced", "Profiles Shared", "Interviews", "Selected", "Joined",
      "Selection %", "Joining %", "Profile-to-Interview Ratio", "Interview-to-Selection Ratio", "Selection-to-Joining Ratio",
      "Average Closure Time", "Requirements Closed"]);
  });

  it("shows a zero denominator as an em dash (AC1) and formats each kind", () => {
    expect(formatFigure(null, "pct")).toBe("—");
    expect(formatFigure(null, "ratio")).toBe("—");
    expect(formatFigure(null, "days")).toBe("—");
    expect(formatFigure(33.3, "pct")).toBe("33.3%");
    expect(formatFigure(100, "pct")).toBe("100.0%");
    expect(formatFigure(0.5, "ratio")).toBe("0.50");
    expect(formatFigure(12.5, "days")).toBe("12.5 days");
    expect(formatFigure(1, "days")).toBe("1.0 day");
    expect(formatFigure(1200, "count")).toBe("1,200");
  });

  it("only passes well-formed parameters to the API", () => {
    expect(performanceParams({ from: "2026-10-01", to: "nope", recruiter: "x" })).toEqual({ from: "2026-10-01", to: undefined, recruiter: undefined });
    const id = "3f2c1a4e-1b2c-4d5e-8f90-123456789abc";
    expect(performanceParams({ recruiter: id }).recruiter).toBe(id);
    expect(performanceQuery({ from: "2026-10-01", recruiter: id })).toBe(`?from=2026-10-01&recruiter=${id}`);
    expect(performanceQuery({})).toBe("");
    expect(csvUrl(performance())).toBe("/api/v1/recruiter/performance.csv?from=2026-10-01&to=2026-10-11");
  });

  it("shows the API's sentence for a range rule and a generic note otherwise", () => {
    expect(performanceError({ status: 422, message: "The range can't end in the future" })).toBe("The range can't end in the future");
    expect(performanceError({ status: 500, message: "boom" })).toBe(PERFORMANCE_UNAVAILABLE);
  });
});

describe("RecruiterPerformancePanel (rec-033 §24, AC1/AC2)", () => {
  it("shows the period's figures as tiles from the Total", () => {
    render(<RecruiterPerformancePanel data={performance()} params={params} today="2026-10-11" />);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Team figures"); // QA33-01: not the page title again
    const tiles = within(screen.getByRole("list", { name: "Team figures" })).getAllByRole("listitem");
    expect(tiles).toHaveLength(15);
    expect(tiles[0]).toHaveTextContent("Recruiter Leads9");
    expect(tiles[8]).toHaveTextContent("Selection %20.0%");
    expect(tiles[13]).toHaveTextContent("Average Closure Time12.5 days");
  });

  it("compares the recruiters in a table whose footer is the Total, with drill-down links", () => {
    render(<RecruiterPerformancePanel data={performance()} params={params} today="2026-10-11" />);
    const table = screen.getByRole("table");
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers[0]).toBe("Recruiter");
    expect(headers).toHaveLength(16);
    expect(within(table).getByRole("link", { name: "Asha" })).toHaveAttribute("href", `${PERFORMANCE_PATH}?from=2026-10-01&to=2026-10-11&recruiter=r-1`);
    expect(within(table).queryByRole("link", { name: "Unassigned" })).toBeNull();
    const ravi = within(table).getByRole("row", { name: /Ravi/ });
    expect(ravi).toHaveTextContent("Inactive");
    expect(ravi).toHaveTextContent("—");
    expect(within(table).getAllByRole("row").at(-1)).toHaveTextContent(/^Total9/);
    expect(screen.getByRole("button", { name: "Download CSV" }).closest("div[style]")).toHaveStyle({ marginTop: "16px" }); // QA33-02
  });

  it("names the recruiter drilled into, with a way back, and no comparison table", () => {
    const one = performance({ recruiter: { id: "r-1", full_name: "Asha" }, items: [row("r-1", "Asha")], totals: row(null, "Total") });
    render(<RecruiterPerformancePanel data={one} params={{ ...params, recruiter: "r-1" }} today="2026-10-11" />);
    expect(screen.getByRole("list", { name: "Asha's figures" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All recruiters" })).toHaveAttribute("href", `${PERFORMANCE_PATH}?from=2026-10-01&to=2026-10-11`);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("form", { name: "Period" })).toContainHTML('name="recruiter"');
  });

  it("keeps the period form and shows the error when the read failed", () => {
    render(<RecruiterPerformancePanel data={null} error="The range can't end in the future" params={params} today="2026-10-11" />);
    expect(screen.getByRole("alert")).toHaveTextContent("The range can't end in the future");
    expect(screen.getByLabelText("From")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("To")).toHaveAttribute("max", "2026-10-11");
  });

  it("offers the way back to everyone when the recruiter asked for is out of reach", () => {
    render(<RecruiterPerformancePanel data={null} error="That recruiter is not in your team." params={{ ...params, recruiter: "r-9" }} today="2026-10-11" />);
    expect(screen.getByRole("alert")).toHaveTextContent("That recruiter is not in your team.");
    expect(screen.getByRole("link", { name: "All recruiters" })).toHaveAttribute("href", `${PERFORMANCE_PATH}?from=2026-10-01&to=2026-10-11`);
  });

  it("says so when there is nobody to compare", () => {
    render(<RecruiterPerformancePanel data={performance({ items: [row(null, "Unassigned")] })} params={params} today="2026-10-11" />);
    expect(screen.getByText("No recruiters to compare yet. Unassigned companies and requirements still count in the Total.")).toBeInTheDocument();
  });
});
