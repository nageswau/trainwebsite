import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import PartnershipReportView from "@/components/PartnershipReportView";
import { csvUrl, type PartnershipReport, reportKind, reportParams, reportQuery, reportUrl, tabHref } from "@/lib/partnershipReports";

afterEach(cleanup);

const report = (over: Partial<PartnershipReport> = {}): PartnershipReport => ({
  kind: "expected", title: "Expected Partnerships Report", as_of: "2026-10-10", filters: { window: "this_month" },
  columns: [
    { key: "university", label: "University", numeric: false }, { key: "owner", label: "Owner", numeric: false },
    { key: "probability", label: "Probability (%)", numeric: true }, { key: "weighted", label: "Weighted", numeric: true },
  ],
  items: [{ university: "ABC University", owner: null, probability: 80, weighted: 0.8 }],
  totals: { university: "Total", owner: null, probability: null, weighted: 0.8 }, total: 1, truncated: false, notes: [], ...over,
});

describe("partnershipReports helpers (upc-031)", () => {
  it("sends only the kind's own, non-empty filters", () => {
    const params = reportParams({ window: "undated", from: "2026-10-01", to: "", month: "2026-10", report: "x", extra: "y" });
    expect(params).toEqual({ window: "undated", from: "2026-10-01", month: "2026-10" });
    expect(reportQuery("expected", params)).toBe("?window=undated");
    expect(reportQuery("performance", params)).toBe("?from=2026-10-01");
    expect(reportQuery("pipeline", params)).toBe("");
    expect(reportUrl("targets", params)).toBe("/api/v1/partnership/reports/targets?month=2026-10");
    expect(csvUrl("agreements", params)).toBe("/api/v1/partnership/reports/agreements.csv");
  });

  it("falls back to the pipeline report for an unknown or missing key", () => {
    expect(reportKind("nope")).toBe("pipeline");
    expect(reportKind(undefined)).toBe("pipeline");
    expect(reportKind("targets")).toBe("targets");
    expect(tabHref("agreements")).toBe("/partnership/reports?report=agreements");
  });
});

describe("PartnershipReportView (upc-031)", () => {
  it("lists every report as a link and marks the open one", () => {
    render(<PartnershipReportView kind="expected" report={report()} error="" params={{}} />);
    const tabs = within(screen.getByRole("navigation", { name: "Reports" })).getAllByRole("link");
    expect(tabs.map((t) => t.textContent)).toEqual(["Pipeline by Country", "Expected Partnerships", "University Performance", "Agreements Expiring", "Targets vs Actual"]);
    expect(tabs[1]).toHaveAttribute("aria-current", "page");
  });

  it("shows the server's columns, a dash for a blank cell, numbers right-aligned and the Total row last", () => {
    render(<PartnershipReportView kind="expected" report={report()} error="" params={{}} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["University", "Owner", "Probability (%)", "Weighted"]);
    const [, row, total] = within(table).getAllByRole("row");
    expect(within(row).getByRole("rowheader")).toHaveTextContent("ABC University");
    const cells = within(row).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("—");
    expect(cells[1]).toHaveTextContent("80");
    expect(cells[1]).toHaveClass("num");
    expect(cells[1]).toHaveAttribute("data-label", "Probability (%)");
    expect(total.closest("tfoot")).not.toBeNull();
    expect(within(total).getByRole("rowheader")).toHaveTextContent("Total");
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
  });

  it("offers the window filter on the expected report, the period on performance, the month on targets, none on pipeline", () => {
    const { rerender } = render(<PartnershipReportView kind="expected" report={report()} error="" params={{ window: "undated" }} />);
    expect(screen.getByRole("combobox", { name: "Expected date window" })).toHaveValue("undated");
    // QA31-01: Back must not restore a value the browser remembered over the one in the address.
    expect(screen.getByRole("form", { name: "Report filters" })).toHaveAttribute("autocomplete", "off");
    rerender(<PartnershipReportView kind="performance" report={report({ kind: "performance", filters: { from: "2026-10-01", to: "2026-10-10" } })} error="" params={{}} />);
    expect(screen.getByLabelText("From")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("To")).toHaveValue("2026-10-10");
    rerender(<PartnershipReportView kind="targets" report={report({ kind: "targets", filters: { month: "2026-10" } })} error="" params={{}} />);
    expect(screen.getByLabelText("Month")).toHaveValue("2026-10");
    rerender(<PartnershipReportView kind="pipeline" report={report({ kind: "pipeline", filters: {} })} error="" params={{}} />);
    expect(screen.queryByRole("form", { name: "Report filters" })).toBeNull();
  });

  it("says when there are no rows and offers no download", () => {
    render(<PartnershipReportView kind="agreements" report={report({ kind: "agreements", items: [], totals: null, total: 0 })} error="" params={{}} />);
    expect(screen.getByRole("status")).toHaveTextContent("No agreements expire in the next 90 days.");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Download CSV" })).toBeNull();
  });

  it("says when the screen shows only the first rows, and shows the server's notes", () => {
    render(<PartnershipReportView kind="expected" report={report({ total: 900, truncated: true, notes: ["Leads are not tracked."] })} error="" params={{}} />);
    expect(screen.getByText(/Showing the first 1 of 900 rows/)).toBeInTheDocument();
    expect(screen.getByText("Leads are not tracked.")).toBeInTheDocument();
  });

  it("shows a refused input above the form, keeping what was typed", () => {
    render(<PartnershipReportView kind="performance" report={null} error="From: use a real date (YYYY-MM-DD)" params={{ from: "2026-02-30" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("From: use a real date");
    expect(screen.getByLabelText("From")).toHaveValue("");  // a date input cannot hold an impossible day; the message names it
    expect(screen.queryByRole("table")).toBeNull();
  });
});
