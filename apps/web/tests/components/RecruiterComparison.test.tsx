import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import RecruiterComparisonPanel from "@/components/RecruiterComparisonPanel";
import { COMPARISON_GROUPS, COMPARISON_PATH, comparisonHref, type Comparison, type ComparisonRow } from "@/lib/recruiterComparison";

afterEach(cleanup);

const row = (id: string | null, name: string, over: Partial<ComparisonRow> = {}): ComparisonRow => ({
  user_id: id, full_name: name, active: true, companies_contacted: 5, meetings: 2, new_leads: 3, new_companies: 1, new_contracts: 1,
  new_requirements: 2, candidates_sourced: 12, profiles_shared: 8, interviews: 4, selections: 2, joining: 1, revenue: "150000.00", ...over,
});
const comparison = (over: Partial<Comparison> = {}): Comparison => ({
  date_from: "2026-10-01", date_to: "2026-10-11", recruiter: null,
  items: [row("r-1", "Asha"), row("r-2", "Ravi", { active: false, meetings: 0 })],
  totals: row(null, "Total", { companies_contacted: 10, revenue: "300000.00" }), ...over,
});
const params = { from: "2026-10-01", to: "2026-10-11" };
const view = (data: Comparison | null, extra: { error?: string; own?: boolean } = {}) =>
  render(<RecruiterComparisonPanel data={data} error={extra.error} params={params} today="2026-10-11" own={extra.own ?? false} />);

describe("recruiterComparison lib (rec-034 B1-B12)", () => {
  it("groups the twelve §25 metrics in the source's order", () => {
    expect(COMPARISON_GROUPS.map((g) => [g.label, g.figures.map((f) => f.label)])).toEqual([
      ["Business development", ["Companies contacted", "Meetings", "New recruiter leads", "New companies", "New contracts", "New requirements"]],
      ["Recruitment", ["Candidates sourced", "Profiles shared", "Interviews", "Selections", "Joining", "Revenue"]],
    ]);
  });

  it("keeps the period when narrowing to one recruiter", () => {
    expect(comparisonHref("2026-10-01", "2026-10-11")).toBe(`${COMPARISON_PATH}?from=2026-10-01&to=2026-10-11`);
    expect(comparisonHref("2026-10-01", "2026-10-11", "r-1")).toBe(`${COMPARISON_PATH}?from=2026-10-01&to=2026-10-11&recruiter=r-1`);
  });
});

describe("RecruiterComparisonPanel (rec-034)", () => {
  it("compares recruiters side by side under the two §25 headings with a Total (BP4)", () => {
    view(comparison());
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Business development" })).toHaveAttribute("colspan", "6");
    expect(within(table).getByRole("columnheader", { name: "Recruitment" })).toHaveAttribute("colspan", "6");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(5); // 2 header rows, 2 recruiters, Total
    expect(within(rows[2]).getByRole("link", { name: "Asha" })).toHaveAttribute("href", `${COMPARISON_PATH}?from=2026-10-01&to=2026-10-11&recruiter=r-1`);
    expect(within(rows[2]).getByText("₹1,50,000.00")).toBeInTheDocument();
    expect(within(rows[3]).getByText("Inactive")).toBeInTheDocument();
    expect(within(rows[4]).getByRole("rowheader", { name: "Total" })).toBeInTheDocument();
    expect(within(rows[4]).getByText("₹3,00,000.00")).toBeInTheDocument();
    expect(within(rows[4]).getByText("10")).toBeInTheDocument();
  });

  it("shows a recruiter their own row only, without links or a Total", () => {
    view(comparison({ items: [row("r-1", "Asha")], totals: null, recruiter: { id: "r-1", full_name: "Asha" } }), { own: true });
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).queryByRole("link")).toBeNull();
    expect(screen.queryByRole("link", { name: "All recruiters" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Your figures" })).toBeInTheDocument();
  });

  it("offers the way back to the team when narrowed to one recruiter", () => {
    render(<RecruiterComparisonPanel data={comparison({ items: [row("r-1", "Asha")], recruiter: { id: "r-1", full_name: "Asha" } })}
      params={{ ...params, recruiter: "r-1" }} today="2026-10-11" own={false} />);
    expect(screen.getByRole("link", { name: "All recruiters" })).toHaveAttribute("href", `${COMPARISON_PATH}?from=2026-10-01&to=2026-10-11`);
    expect(screen.getByRole("heading", { name: "Asha's figures" })).toBeInTheDocument();
  });

  it("QA34-01: keeps the way back to the team when the recruiter asked for is not in it", () => {
    render(<RecruiterComparisonPanel data={null} error="That recruiter is not in your team." params={{ ...params, recruiter: "r-9" }} today="2026-10-11" own={false} />);
    expect(screen.getByRole("link", { name: "All recruiters" })).toHaveAttribute("href", `${COMPARISON_PATH}?from=2026-10-01&to=2026-10-11`);
  });

  it("QA34-03: starts each metric group with a divider so the two halves read apart", () => {
    view(comparison());
    const headers = within(screen.getByRole("table")).getAllByRole("columnheader");
    const starts = headers.filter((th) => th.classList.contains("group-start")).map((th) => th.textContent);
    expect(starts).toEqual(["Business development", "Recruitment", "Companies contacted", "Candidates sourced"]);
  });

  it("says so when there is no recruiter to compare", () => {
    view(comparison({ items: [], totals: row(null, "Total") }));
    expect(screen.getByRole("status")).toHaveTextContent("No recruiters to compare");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows the error in place of the table and keeps the period form", () => {
    view(null, { error: "The range can't end in the future" });
    expect(screen.getByText("The range can't end in the future")).toHaveAttribute("role", "alert");
    expect(screen.getByLabelText("From")).toHaveValue("2026-10-01");
    expect(screen.queryByRole("table")).toBeNull();
  });
});
