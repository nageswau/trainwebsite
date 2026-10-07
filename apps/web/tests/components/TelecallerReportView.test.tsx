import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TelecallerReportView from "@/components/TelecallerReportView";
import { csvUrl, reportKind, reportQuery, tabHref, type TelecallerReport } from "@/lib/telecallerReports";

afterEach(cleanup);

const OPTIONS = {
  teams: ["it", "overseas"],
  sources: [{ key: "instagram", label: "Instagram" }, { key: "website", label: "Website" }],
  products: [{ id: "p1", name: "Cyber Security" }],
  campaigns: [{ id: "c1", name: "Instagram Cyber Security" }],
};
const FUNNEL = [
  { key: "label", label: "Campaign" }, { key: "leads", label: "Leads" }, { key: "connected", label: "Connected" },
  { key: "qualified", label: "Qualified" }, { key: "counselling", label: "Counselling" }, { key: "enrolled", label: "Enrolled" },
];
const report = (over: Partial<TelecallerReport> = {}): TelecallerReport => ({
  kind: "campaign", title: "Campaign Report", date_from: "2026-10-01", date_to: "2026-10-07", columns: FUNNEL,
  items: [{ label: "Instagram Cyber Security", leads: 250, connected: 160, qualified: 75, counselling: 40, enrolled: 12 }],
  totals: { label: "Total", leads: 250, connected: 160, qualified: 75, counselling: 40, enrolled: 12 }, options: OPTIONS, ...over,
});
const BASE = "/telecaller/manager/reports";

describe("telecallerReports helpers (tel-024)", () => {
  it("keeps only known, non-empty filters and drops lead filters on the telecaller report", () => {
    const params = { date_from: "2026-10-01", date_to: "", team: "it", source: "website", report: "x", product_id: "p1" };
    expect(reportQuery("campaign", params)).toBe("?date_from=2026-10-01&team=it&product_id=p1&source=website");
    expect(reportQuery("telecaller", params)).toBe("?date_from=2026-10-01&team=it");
    expect(csvUrl("campaign", {})).toBe("/api/v1/telecaller/reports/campaign.csv");
  });

  it("falls back to the source report for an unknown key and builds tab links that keep the filters", () => {
    expect(reportKind("nope")).toBe("source");
    expect(reportKind("handover")).toBe("handover");
    expect(tabHref(BASE, "product", { date_from: "2026-10-01", campaign_id: "c1" })).toBe(`${BASE}?report=product&date_from=2026-10-01&campaign_id=c1`);
  });
});

describe("TelecallerReportView (tel-024 §21)", () => {
  it("shows the five reports as links, the current one marked", () => {
    render(<TelecallerReportView kind="campaign" report={report()} error="" params={{}} basePath={BASE} />);
    const nav = screen.getByRole("navigation", { name: "Reports" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["Lead Source", "Course", "Telecaller", "Counselor Handover", "Campaign"]);
    expect(links[4]).toHaveAttribute("aria-current", "page");
    expect(links[0]).not.toHaveAttribute("aria-current");
  });

  it("lays the report out as a table with the server's columns and a Total row", () => {
    render(<TelecallerReportView kind="campaign" report={report()} error="" params={{}} basePath={BASE} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(FUNNEL.map((c) => c.label));
    expect(within(table).getByRole("rowheader", { name: "Instagram Cyber Security" })).toBeInTheDocument();
    const total = within(table).getByRole("rowheader", { name: "Total" }).closest("tr")!;
    expect(within(total).getAllByRole("cell").map((c) => c.textContent)).toEqual(["250", "160", "75", "40", "12"]);
    expect(screen.getByRole("heading", { name: "Campaign Report" })).toBeInTheDocument();
  });

  it("offers every filter on a lead report, with the range the server used", () => {
    render(<TelecallerReportView kind="campaign" report={report()} error="" params={{ source: "website" }} basePath={BASE} />);
    expect(screen.getByLabelText("From")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("To")).toHaveValue("2026-10-07");
    expect(screen.getByLabelText("Team")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Course")).getByRole("option", { name: "Cyber Security" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("Campaign")).getByRole("option", { name: "Instagram Cyber Security" })).toBeInTheDocument();
    expect(screen.getByLabelText("Source")).toHaveValue("website");
    expect(screen.getByRole("link", { name: "Clear filters" })).toHaveAttribute("href", `${BASE}?report=campaign`);
  });

  it("offers only the dates (and a team to pick) on the telecaller report", () => {
    const one = { ...OPTIONS, teams: ["it"] };
    render(<TelecallerReportView kind="telecaller" report={report({ kind: "telecaller", options: one })} error="" params={{}} basePath={BASE} />);
    expect(screen.queryByLabelText("Course")).toBeNull();
    expect(screen.queryByLabelText("Campaign")).toBeNull();
    expect(screen.queryByLabelText("Source")).toBeNull();
    expect(screen.queryByLabelText("Team")).toBeNull(); // only one team in scope: nothing to choose
  });

  it("says when nothing matches and still offers the filters", () => {
    render(<TelecallerReportView kind="campaign" report={report({ items: [] })} error="" params={{}} basePath={BASE} />);
    expect(screen.getByRole("status")).toHaveTextContent("No leads in this range.");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Download CSV" })).toBeNull();
  });

  it("shows a refused or failed read as an alert above the form", () => {
    render(<TelecallerReportView kind="source" report={null} error="'From' must be on or before 'To'" params={{ date_from: "2026-10-09", date_to: "2026-10-01" }} basePath={BASE} />);
    expect(screen.getByRole("alert")).toHaveTextContent("'From' must be on or before 'To'");
    expect(screen.getByLabelText("From")).toHaveValue("2026-10-09");
    expect(screen.queryByRole("table")).toBeNull();
    // QA-01: the heading is the report's name even without a response; QA-02: no empty Team picker when the options are unknown.
    expect(screen.getByRole("heading", { name: "Lead Source Report" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Team")).toBeNull();
  });

  it("keeps a chosen team in the form when the read failed", () => {
    render(<TelecallerReportView kind="handover" report={null} error="Unavailable" params={{ team: "overseas" }} basePath={BASE} />);
    expect(screen.getByRole("heading", { name: "Counselor Handover Report" })).toBeInTheDocument();
    expect(screen.getByLabelText("Team")).toHaveValue("overseas");
  });

  it("downloads the same report as CSV", () => {
    render(<TelecallerReportView kind="campaign" report={report()} error="" params={{ campaign_id: "c1" }} basePath={BASE} />);
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
  });
});
