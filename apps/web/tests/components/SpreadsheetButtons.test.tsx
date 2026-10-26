import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpreadsheetButtons, XLSX_TYPE } from "@/components/ExportButtons";

// nehn-004 (DEC-SCOPE-280 X6): the report pages whose export format is the path's extension offer the `.csv` and its `.xlsx` twin
// side by side, each fetched first (ReportDownloadButton), so a refusal is a message, never a saved file.
const saved: string[] = [];
const file = (type: string) => new Response("data", { status: 200, headers: { "content-type": type } });

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
  saved.length = 0;
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    saved.push(this.download);
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SpreadsheetButtons (nehn-004)", () => {
  it("asks for the .csv and its .xlsx twin with the same filters and saves each under its own name", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(file("text/csv; charset=utf-8")).mockResolvedValueOnce(file(XLSX_TYPE));
    vi.stubGlobal("fetch", fetchMock);
    render(<SpreadsheetButtons csvUrl="/api/v1/telecaller/reports/source.csv?date_from=2026-10-01" filename="telecaller-source-2026-10-01-to-2026-10-26.csv" label="Export Source report" />);
    const group = screen.getByRole("group", { name: "Export Source report" });
    fireEvent.click(within(group).getByRole("button", { name: "Download CSV" }));
    await screen.findByText("Report downloaded.");
    fireEvent.click(within(group).getByRole("button", { name: "Download Excel" }));
    await waitFor(() => expect(saved).toHaveLength(2));
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/telecaller/reports/source.csv?date_from=2026-10-01",
      "/api/v1/telecaller/reports/source.xlsx?date_from=2026-10-01",
    ]);
    expect(saved).toEqual(["telecaller-source-2026-10-01-to-2026-10-26.csv", "telecaller-source-2026-10-01-to-2026-10-26.xlsx"]);
  });

  it("works for a URL without a query and describes the group with the hint", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SpreadsheetButtons csvUrl="/api/v1/recruiter/performance.csv" filename="recruiter.csv" label="Export performance" hint="Up to 10,000 rows." />);
    const group = screen.getByRole("group", { name: "Export performance" });
    expect(group).toHaveAccessibleDescription("Up to 10,000 rows.");
  });

  it("only saves a real spreadsheet: a refusal is shown instead", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "This report has more than 10,000 rows; narrow the filters" }), { status: 422 })));
    render(<SpreadsheetButtons csvUrl="/api/v1/x/students.csv" filename="students.csv" label="Export students" />);
    fireEvent.click(screen.getByRole("button", { name: "Download Excel" }));
    expect(await screen.findByText("This report has more than 10,000 rows; narrow the filters")).toBeInTheDocument();
    expect(saved).toEqual([]);
  });
});
