import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TelecallerReportView from "@/components/TelecallerReportView";
import { reportKind, reportParams, reportQuery, tabHref, type TelecallerReport } from "@/lib/telecallerReports";

// nehn-013 (DEC-SCOPE-300): the counselor, date-wise, follow-up status and pending follow-up reports on the telecaller reports page.
afterEach(cleanup);

const OPTIONS = { teams: ["it"], sources: [], products: [], campaigns: [] };
const BASE = "/telecaller/manager/reports";
const dateReport = (over: Partial<TelecallerReport> = {}): TelecallerReport => ({
  kind: "date", title: "Date-wise Report", date_from: "2026-03-01", date_to: "2026-04-30",
  columns: [{ key: "period", label: "Period" }, { key: "leads", label: "Leads" }, { key: "conversion_rate", label: "Conversion rate (%)" }],
  items: [{ period: "March 2026", leads: 4, conversion_rate: 25 }],
  totals: { period: "Total", leads: 4, conversion_rate: 25 }, options: OPTIONS, ...over,
});

describe("telecallerReports helpers (nehn-013)", () => {
  it("knows the new kinds and sends the grouping only to the date-wise report", () => {
    for (const kind of ["counselor", "date", "follow_ups", "pending_follow_ups"]) expect(reportKind(kind)).toBe(kind);
    const params = reportParams({ group: "week", source: "website" });
    expect(reportQuery("date", params)).toBe("?source=website&group=week");
    expect(reportQuery("campaign", params)).toBe("?source=website");
    expect(reportQuery("pending_follow_ups", params)).toBe("?source=website");
    expect(tabHref(BASE, "campaign", params)).toBe(`${BASE}?report=campaign&source=website&group=week`); // kept for the way back
  });
});

describe("TelecallerReportView (nehn-013)", () => {
  it("adds the four reports as tabs after the existing six", () => {
    render(<TelecallerReportView kind="date" report={dateReport()} error="" params={{}} basePath={BASE} />);
    const links = within(screen.getByRole("navigation", { name: "Reports" })).getAllByRole("link");
    // QA-03: "Follow-up Status" so the heading matches the report's (and its export's) title.
    expect(links.map((l) => l.textContent).slice(6)).toEqual(["Counselor", "Date-wise", "Follow-up Status", "Pending Follow-ups"]);
    expect(links[7]).toHaveAttribute("aria-current", "page");
  });

  it("offers a Group by choice on the date-wise report only, keeping the chosen value", () => {
    render(<TelecallerReportView kind="date" report={dateReport()} error="" params={{ group: "month" }} basePath={BASE} />);
    const group = screen.getByLabelText("Group by");
    expect(within(group).getAllByRole("option").map((o) => o.textContent)).toEqual(["Day", "Week", "Month"]);
    expect(group).toHaveValue("month");
    cleanup();
    render(<TelecallerReportView kind="campaign" report={dateReport({ kind: "campaign" })} error="" params={{}} basePath={BASE} />);
    expect(screen.queryByLabelText("Group by")).not.toBeInTheDocument();
  });

  it("shows the conversion rate with one decimal, as the CSV does (QA-01)", () => {
    render(<TelecallerReportView kind="date" report={dateReport()} error="" params={{}} basePath={BASE} />);
    const row = screen.getByRole("rowheader", { name: "March 2026" }).closest("tr")!;
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["4", "25.0"]);
    const total = screen.getByRole("rowheader", { name: "Total" }).closest("tr")!;
    expect(within(total).getAllByRole("cell").map((c) => c.textContent)).toEqual(["4", "25.0"]);
  });

  it("wraps the report tabs so none hides off the edge (QA-02)", () => {
    render(<TelecallerReportView kind="date" report={dateReport()} error="" params={{}} basePath={BASE} />);
    expect(screen.getByRole("navigation", { name: "Reports" })).toHaveClass("report-tablist", "wrap");
  });

  it.each([
    ["counselor", "No leads with a counselor in this range."],
    ["follow_ups", "No follow-ups due in this range."],
    ["pending_follow_ups", "No overdue follow-ups in this range."],
  ] as const)("names the empty %s report", (kind, message) => {
    render(<TelecallerReportView kind={kind} report={dateReport({ kind, items: [] })} error="" params={{}} basePath={BASE} />);
    expect(screen.getByRole("status")).toHaveTextContent(message);
  });
});
