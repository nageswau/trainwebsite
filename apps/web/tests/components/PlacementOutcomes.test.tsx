import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import PlacementOutcomesPanel from "@/components/PlacementOutcomesPanel";
import {
  OUTCOMES_UNAVAILABLE, drillHref, exportUrl, formatFigure, outcomeParams, outcomesError, type Outcomes,
} from "@/lib/placementOutcomes";

afterEach(cleanup);

const ID = "11111111-2222-3333-4444-555555555555";
const figures = (over: Record<string, number | string | null> = {}) => ({
  placements: 2, joined: 1, pending: 1, did_not_join: 0, joining_rate: 100, time_to_fill_days: 3.5, dropouts: 0, early_dropouts: 0,
  replacements_owed: 0, replacements_filled: 0, client_rating: 4, client_responses: 1, candidate_rating: null, candidate_responses: 0,
  fee_generated: "50000.00", invoiced: "50000.00", collected: "20000.00", outstanding: "30000.00", ...over,
});
const columns = [{ key: "placements", label: "Placements" }, { key: "joining_rate", label: "Joining rate %" }, { key: "invoiced", label: "Invoiced" }];
const outcomes = (over: Partial<Outcomes> = {}): Outcomes => ({
  date_from: "2026-11-01", date_to: "2026-11-08", group_by: "company", group_label: "Company", filters: {}, revenue_visible: true, columns,
  totals: figures(), items: [{ key: ID, label: "Acme", figures: figures() }],
  funnel: { requirements: 4, submissions: 2, interviews: 1, offers: 2, offers_accepted: 2, offers_declined: 0, requirement_to_submission: 50,
    submission_to_interview: 50, interview_to_offer: 200, offer_acceptance: 100 },
  placements: [{ id: "p-1", status: "joined", status_label: "Joined", candidate: { id: "c", code: "CAN-1", name: "Asha" },
    requirement: { id: "j", code: "REQ-1", title: "Java" }, company: { id: ID, name: "Acme" }, vendor: null, role: "Java", recruiter: "Ravi",
    po_owner: "Ravi", source: null, accepted_at: "2026-11-02T10:00:00Z", joined_on: "2026-11-05", dropout_on: null, early_dropout: false,
    client_rating: 4, candidate_rating: null, fee: "50000.00" }],
  placements_total: 1, ...over,
});

describe("placementOutcomes lib (pob-029)", () => {
  it("keeps only well-formed params", () => {
    expect(outcomeParams({ from: "2026-11-01", to: "bad", group_by: "planet", company: ID, vendor: "x" })).toEqual({ from: "2026-11-01", to: undefined, company: ID });
    expect(outcomeParams({ group_by: "po" }).group_by).toBe("po");
  });

  it("formats each kind and shows nothing to divide by as an em dash", () => {
    expect(formatFigure("joining_rate", null)).toBe("—");
    expect(formatFigure("joining_rate", 66.7)).toBe("66.7%");
    expect(formatFigure("time_to_fill_days", 3.5)).toBe("3.5 d");
    expect(formatFigure("invoiced", "50000.00")).toBe("₹50,000.00");
    expect(formatFigure("placements", 1200)).toBe("1,200");
    expect(formatFigure("client_rating", 4)).toBe("4.0"); // QA-05: a rating always shows one decimal
    expect(formatFigure("candidate_rating", 4.25)).toBe("4.3");
  });

  it("exports and drills down with the report's own period and filters", () => {
    const data = outcomes();
    expect(exportUrl(data)).toBe("/api/v1/recruiter/reports/placement-outcomes.csv?from=2026-11-01&to=2026-11-08&group_by=company");
    expect(drillHref(data, data.items[0])).toBe(`/recruiter/manager/placement-outcomes?from=2026-11-01&to=2026-11-08&group_by=company&company=${ID}`);
    expect(drillHref(outcomes({ group_by: "role" }), { key: "java", label: "Java", figures: {} })).toBeNull();
    expect(outcomesError({ status: 422, message: "The range can't end in the future" })).toBe("The range can't end in the future");
    expect(outcomesError(new Error("x"))).toBe(OUTCOMES_UNAVAILABLE);
  });
});

describe("PlacementOutcomesPanel (pob-029)", () => {
  it("shows the totals, the conversions, the table with its Total and the placements behind them", () => {
    render(<PlacementOutcomesPanel data={outcomes()} params={{}} today="2026-11-08" />);
    const tiles = screen.getByRole("list", { name: "Placement outcomes" });
    expect(within(tiles).getByText("Outstanding").nextSibling?.textContent).toBe("₹30,000.00");
    expect(within(screen.getByRole("list", { name: "Conversions" })).getByText("100.0%")).toBeTruthy();
    const table = within(screen.getByRole("region", { name: "Outcomes by company" }));
    expect(table.getByRole("link", { name: "Acme" })).toBeTruthy();
    expect(table.getByRole("rowheader", { name: "Total" })).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Placements behind these figures" })).getByRole("link", { name: "Asha" }).getAttribute("href")).toBe("/recruiter/placements/p-1");
    expect(screen.getByRole("group", { name: "Export the outcome table" })).toBeTruthy();
  });

  it("hides the revenue tiles without the grant and says an empty period plainly", () => {
    render(<PlacementOutcomesPanel data={outcomes({ revenue_visible: false, items: [], placements: [], placements_total: 0, totals: figures({ placements: 0 }) })} params={{}} today="2026-11-08" />);
    expect(screen.queryByText("Outstanding")).toBeNull();
    expect(screen.getByText("Revenue figures need the client commercials permission.")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("No offers were accepted in this period.");
    expect(screen.queryByRole("group", { name: "Export the outcome table" })).toBeNull();
  });

  it("shows the API's sentence when the report cannot be read", () => {
    render(<PlacementOutcomesPanel data={null} error="The range can't end in the future" params={{ from: "2026-11-01" }} today="2026-11-08" />);
    expect(screen.getByRole("alert").textContent).toBe("The range can't end in the future");
  });
});
