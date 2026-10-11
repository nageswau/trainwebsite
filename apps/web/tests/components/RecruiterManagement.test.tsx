import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import RecruiterManagementPanel from "@/components/RecruiterManagementPanel";
import {
  MANAGEMENT_PATH, MANAGEMENT_UNAVAILABLE, TOTALS, managementError, managementParams, managementQuery, type Management,
} from "@/lib/recruiterManagement";

afterEach(cleanup);

const management = (over: Partial<Management> = {}): Management => ({
  date_from: "2026-10-01", date_to: "2026-10-11",
  totals: { companies: 85, active_recruiters: 62, open_requirements: 145, candidates_in_pipeline: 2350, interviews: 420, selected: 160, joined: 125 },
  top_companies: [{ id: "c-1", name: "ABC Technologies", joined: 18 }, { id: "c-2", name: "XYZ Solutions", joined: 1 }],
  top_categories: [{ id: "k-1", name: "IT", open_requirements: 40 }, { id: "k-2", name: "Sales", open_requirements: 1 }],
  ...over,
});
const params = { from: "2026-10-01", to: "2026-10-11" };

describe("recruiterManagement lib (rec-035 MG3)", () => {
  it("lists the seven §26 totals in the source's order", () => {
    expect(TOTALS.map((t) => t.label)).toEqual([
      "Companies", "Active Recruiters", "Open Requirements", "Candidates in Pipeline", "Interviews", "Selected", "Joined"]);
  });

  it("only passes well-formed dates to the API", () => {
    expect(managementParams({ from: "2026-10-01", to: "nope" })).toEqual({ from: "2026-10-01", to: undefined });
    expect(managementQuery({ from: "2026-10-01", to: "2026-10-11" })).toBe("?from=2026-10-01&to=2026-10-11");
    expect(managementQuery({})).toBe("");
  });

  it("shows the API's sentence for a range rule and a generic note otherwise", () => {
    expect(managementError({ status: 422, message: "The range can't end in the future" })).toBe("The range can't end in the future");
    expect(managementError({ status: 500, message: "boom" })).toBe(MANAGEMENT_UNAVAILABLE);
    expect(managementError(new Error("network"))).toBe(MANAGEMENT_UNAVAILABLE);
  });
});

describe("RecruiterManagementPanel (rec-035 §26)", () => {
  it("shows the seven totals as tiles", () => {
    render(<RecruiterManagementPanel data={management()} params={params} today="2026-10-11" />);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("At a glance"); // QA35-01: not the page title again
    const tiles =within(screen.getByRole("list", { name: "Recruiter business totals" })).getAllByRole("listitem");
    expect(tiles).toHaveLength(7);
    expect(tiles[0]).toHaveTextContent("Companies85");
    expect(tiles[3]).toHaveTextContent("Candidates in Pipeline2,350");
    expect(tiles[6]).toHaveTextContent("Joined125");
  });

  it("ranks the top companies by hires and the top job categories, in the API's order", () => {
    render(<RecruiterManagementPanel data={management()} params={params} today="2026-10-11" />);
    const companies = within(screen.getByRole("list", { name: "Top Companies" })).getAllByRole("listitem").map((li) => li.textContent);
    expect(companies).toEqual(["ABC Technologies – 18 hires", "XYZ Solutions – 1 hire"]);
    const categories = within(screen.getByRole("list", { name: "Top Job Categories" })).getAllByRole("listitem").map((li) => li.textContent);
    expect(categories).toEqual(["IT – 40 open requirements", "Sales – 1 open requirement"]);
  });

  it("says so when there is no data", () => {
    const empty = management({ top_companies: [], top_categories: [] });
    render(<RecruiterManagementPanel data={empty} params={params} today="2026-10-11" />);
    expect(screen.getByText("No hires in this period yet.")).toHaveAttribute("role", "status");
    expect(screen.getByText("No open requirements with a job category.")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("list", { name: "Top Companies" })).toBeNull();
  });

  it("keeps the period form (a GET to the page) and shows the error when the read failed", () => {
    render(<RecruiterManagementPanel data={null} error="The range can't end in the future" params={params} today="2026-10-11" />);
    expect(screen.getByRole("alert")).toHaveTextContent("The range can't end in the future");
    expect(screen.getByRole("form", { name: "Period" })).toHaveAttribute("action", MANAGEMENT_PATH);
    expect(screen.getByLabelText("From")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("To")).toHaveAttribute("max", "2026-10-11");
    expect(screen.queryByRole("list")).toBeNull();
  });
});
