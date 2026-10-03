import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentReportTable from "@/components/AgentReportTable";
import type { AgentReport } from "@/lib/types";

// AGN-020 (DEC-SCOPE-067; spec §6.2): the report table -- presentation only.

const summary: AgentReport = {
  kind: "countries", title: "Applications by country", scope: "agency",
  columns: [{ key: "country", label: "Country", numeric: false }, { key: "applications", label: "Applications", numeric: true }],
  items: [{ country: "<b>Aland</b>", applications: 4 }, { country: null, applications: 0 }],
  totals: { country: "Total", applications: 4 }, total: 2, limit: 2, offset: 0, options: {}, as_of: "2026-10-03T08:05:00Z",
};
const list = (offset: number, total = 312): AgentReport => ({
  ...summary, kind: "students", columns: [{ key: "name", label: "Name", numeric: false }], totals: null, total, limit: 50, offset,
  items: Array.from({ length: Math.min(50, total - offset) }, (_, i) => ({ name: `Student ${offset + i}` })),
});

function renderTable(report: AgentReport, onPage = vi.fn(), busy = false) {
  render(
    <>
      <h3 id="report-heading">Report</h3>
      <AgentReportTable report={report} headingId="report-heading" caption="All dates" busy={busy} onPage={onPage} />
    </>,
  );
  return onPage;
}

afterEach(cleanup);

describe("AgentReportTable", () => {
  it("is a scrollable region named by the report heading, with column and row headers", () => {
    renderTable(summary);
    const region = screen.getByRole("region", { name: "Report" });
    const table = within(region).getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["Country", "Applications"]);
    expect(within(table).getAllByRole("rowheader")[0]).toHaveTextContent("<b>Aland</b>"); // text, never markup
    expect(table.querySelector("caption")).toHaveTextContent("All dates");
  });

  it("right-aligns numbers, labels every cell for phones and shows a dash for no value", () => {
    renderTable(summary);
    const cell = screen.getAllByRole("cell")[0];
    expect(cell).toHaveClass("num");
    expect(cell).toHaveAttribute("data-label", "Applications");
    expect(screen.getAllByRole("rowheader")[1]).toHaveTextContent("—");
  });

  it("puts the Total row in the footer", () => {
    const { container } = render(<AgentReportTable report={summary} headingId="h" caption="" busy={false} onPage={vi.fn()} />);
    expect(container.querySelector("tfoot")).toHaveTextContent("Total4");
  });

  it("pages a list: position, Previous disabled on the first page, Next asks for the next offset", () => {
    const onPage = renderTable(list(0));
    expect(screen.getByText("Showing 1–50 of 312")).toBeInTheDocument();
    const previous = screen.getByRole("button", { name: "Previous" });
    expect(previous).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(previous);
    expect(onPage).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPage).toHaveBeenCalledWith(50);
  });

  it("shows the last page and disables Next there", () => {
    const onPage = renderTable(list(300));
    expect(screen.getByText("Showing 301–312 of 312")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPage).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(onPage).toHaveBeenCalledWith(250);
  });

  it("has no pager for a summary", () => {
    renderTable(summary);
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
  });

  it("keeps a date on one line (browser QA20-06)", () => {
    renderTable({ ...summary, items: [{ country: "Aland", applications: 4, created: "2026-10-03" }], columns: [...summary.columns, { key: "created", label: "Created", numeric: false }] });
    expect(screen.getByText("2026-10-03")).toHaveClass("nowrap");
  });

  it("tells the reader a wide report scrolls sideways (browser QA20-06)", () => {
    const columns = Array.from({ length: 11 }, (_, i) => ({ key: `c${i}`, label: `C${i}`, numeric: false }));
    renderTable({ ...list(0, 1), columns, items: [Object.fromEntries(columns.map((c) => [c.key, "x"]))] });
    expect(screen.getByText("Scroll sideways to see every column.")).toBeInTheDocument();
  });

  it("marks the region busy while a newer report loads", () => {
    renderTable(summary, vi.fn(), true);
    expect(screen.getByRole("region", { name: "Report" })).toHaveAttribute("aria-busy", "true");
  });
});
