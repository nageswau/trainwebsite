import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ReportView, { ReportLibraryList } from "@/components/ReportView";
import { type CatalogueItem, type Report, csvUrl, pageHref, reportParams, reportUrl } from "@/lib/reports";

afterEach(cleanup);

const FILTERS = ["from", "to", "course_id", "batch_id", "trainer_id", "student", "status", "latest", "completion_from", "completion_to"];
const ITEM: CatalogueItem = { id: "enrollments", title: "Enrollments", description: "One row per student enrolment.", filters: FILTERS, can_download: true };
const COLUMNS = [
  { key: "enrollment_code", label: "Enrollment code" }, { key: "student", label: "Student" }, { key: "trainer", label: "Trainer" },
  { key: "progress", label: "Progress %" },
];
const report = (over: Partial<Report> = {}): Report => ({
  id: "enrollments", title: "Enrollments", description: "One row per student enrolment.", columns: COLUMNS,
  items: [{ enrollment_code: "EDU-1", student: "Asha", trainer: null, progress: 42 }], total: 1, page: 1, page_size: 50, filters: FILTERS,
  applied: {}, options: {
    courses: [{ value: "c1", label: "Python" }], batches: [{ value: "b1", label: "PY-01" }], trainers: [{ value: "t1", label: "Ravi" }],
    statuses: [{ value: "active", label: "active" }],
  }, ...over,
});
const BASE = "/it/admin/report-library";

describe("reports helpers (nehn-009)", () => {
  it("keeps only the declared, non-empty filters and the page from the address", () => {
    const search = { report: "enrollments", from: "2026-10-01", to: "", recruiter_id: "r1", status: "active", page: "2", colour: "red", latest: ["1", "2"] };
    expect(reportParams(search, FILTERS)).toEqual({ from: "2026-10-01", status: "active", page: "2" });
  });

  it("builds the read, download and page addresses", () => {
    const params = { from: "2026-10-01", status: "active", page: "2" };
    expect(reportUrl("enrollments", params)).toBe("/api/v1/reports/enrollments?from=2026-10-01&status=active&page=2");
    expect(csvUrl("enrollments", params)).toBe("/api/v1/reports/enrollments.csv?from=2026-10-01&status=active");
    expect(csvUrl("enrollments", {})).toBe("/api/v1/reports/enrollments.csv");
    expect(pageHref(BASE, "enrollments", params, 3)).toBe(`${BASE}?report=enrollments&from=2026-10-01&status=active&page=3`);
    expect(pageHref(BASE, "enrollments", params, 1)).toBe(`${BASE}?report=enrollments&from=2026-10-01&status=active`);
  });
});

describe("ReportLibraryList (nehn-009)", () => {
  it("links every report the caller may view", () => {
    render(<ReportLibraryList items={[ITEM]} basePath={BASE} />);
    const link = screen.getByRole("link", { name: "Enrollments" });
    expect(link.getAttribute("href")).toBe(`${BASE}?report=enrollments`);
    expect(screen.getByText("One row per student enrolment.")).toBeTruthy();
  });

  it("says so when no report is available", () => {
    render(<ReportLibraryList items={[]} basePath={BASE} />);
    expect(screen.getByRole("status").textContent).toBe("No reports are available to you.");
  });
});

describe("ReportView (nehn-009)", () => {
  it("renders a field for each declared filter only, with the server's options", () => {
    render(<ReportView item={{ ...ITEM, filters: ["from", "course_id", "student"] }} report={report()} error="" params={{}} basePath={BASE} />);
    const form = screen.getByRole("form", { name: "Report filters" });
    expect(within(form).getByLabelText("From").getAttribute("type")).toBe("date");
    expect(within(form).getByRole("option", { name: "Python" })).toBeTruthy();
    expect(within(form).getByLabelText("Student").getAttribute("maxlength")).toBe("100");
    expect(within(form).queryByLabelText("Trainer")).toBeNull();
    expect(within(form).queryByLabelText("Latest")).toBeNull();
    expect((within(form).getByDisplayValue("enrollments") as HTMLInputElement).type).toBe("hidden");
  });

  it("keeps the address's values in the form", () => {
    render(<ReportView item={ITEM} report={report()} error="" params={{ status: "active", latest: "50", student: "asha" }} basePath={BASE} />);
    expect((screen.getByLabelText("Status") as HTMLSelectElement).value).toBe("active");
    expect((screen.getByLabelText("Latest") as HTMLInputElement).value).toBe("50");
    expect((screen.getByLabelText("Student") as HTMLInputElement).value).toBe("asha");
  });

  it("offers the attendance report's 'Attendance below %' as a 1-100 number, kept from the address (nehn-011)", () => {
    const attendance = { ...ITEM, id: "attendance", filters: ["from", "to", "attendance_below"] };
    render(<ReportView item={attendance} report={report({ id: "attendance" })} error="" params={{ attendance_below: "75" }} basePath={BASE} />);
    const input = screen.getByLabelText("Attendance below %") as HTMLInputElement;
    expect([input.type, input.min, input.max, input.value]).toEqual(["number", "1", "100", "75"]);
  });

  it("shows the rows with labelled cells, a dash for an empty value, and the downloads", () => {
    render(<ReportView item={ITEM} report={report()} error="" params={{ status: "active" }} basePath={BASE} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Enrollment code", "Student", "Trainer", "Progress %"]);
    expect(within(table).getByRole("rowheader").textContent).toBe("EDU-1");
    expect(within(table).getByText("—").getAttribute("data-label")).toBe("Trainer");
    expect(within(table).getByText("42").className).toBe("num");
    expect(screen.getByRole("group", { name: "Export Enrollments" })).toBeTruthy();
    expect(screen.getByText("Showing 1–1 of 1")).toBeTruthy();
  });

  it("hides the downloads without the download grant", () => {
    render(<ReportView item={{ ...ITEM, can_download: false }} report={report()} error="" params={{}} basePath={BASE} />);
    expect(screen.queryByRole("group", { name: "Export Enrollments" })).toBeNull();
  });

  it("pages with links that keep the filters", () => {
    const items = Array.from({ length: 2 }, (_, i) => ({ enrollment_code: `E${i}`, student: "S", trainer: "T", progress: 1 }));
    render(<ReportView item={ITEM} report={report({ items, total: 5, page: 2, page_size: 2 })} error="" params={{ status: "active", page: "2" }} basePath={BASE} />);
    const pager = screen.getByRole("navigation", { name: "Report pages" });
    expect(within(pager).getByText("Showing 3–4 of 5")).toBeTruthy();
    expect(within(pager).getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe(`${BASE}?report=enrollments&status=active`);
    expect(within(pager).getByRole("link", { name: "Next page" }).getAttribute("href")).toBe(`${BASE}?report=enrollments&status=active&page=3`);
  });

  it("has no pager links on a single page", () => {
    render(<ReportView item={ITEM} report={report()} error="" params={{}} basePath={BASE} />);
    expect(screen.queryByRole("link", { name: /page/ })).toBeNull();
  });

  it("says so when no row matches, without a download", () => {
    render(<ReportView item={ITEM} report={report({ items: [], total: 0 })} error="" params={{}} basePath={BASE} />);
    expect(screen.getByRole("status").textContent).toBe("No rows match these filters.");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("group", { name: "Export Enrollments" })).toBeNull();
  });

  it("QA9-01: a page past the last row says so and links to the first page", () => {
    render(<ReportView item={ITEM} report={report({ items: [], total: 5, page: 9, page_size: 2 })} error="" params={{ status: "active", page: "9" }} basePath={BASE} />);
    expect(screen.getByRole("status").textContent).toMatch(/^This page is past the last row\./);
    expect(screen.getByRole("link", { name: "Go to the first page" }).getAttribute("href")).toBe(`${BASE}?report=enrollments&status=active`);
  });

  it("QA9-02: a date cell never wraps mid-value", () => {
    const items = [{ enrollment_code: "EDU-1", student: "Asha", trainer: "2020-01-10", progress: 1 }];
    render(<ReportView item={ITEM} report={report({ items })} error="" params={{}} basePath={BASE} />);
    expect(screen.getByText("2020-01-10").className).toBe("nowrap");
  });

  it("QA9-03: the filters fold away until one is applied (or refused)", () => {
    const { container, rerender } = render(<ReportView item={ITEM} report={report()} error="" params={{}} basePath={BASE} />);
    const details = () => container.querySelector("details") as HTMLDetailsElement;
    expect(details().open).toBe(false);
    expect(details().querySelector("summary")?.textContent).toBe("Filters");
    rerender(<ReportView item={ITEM} report={report()} error="" params={{ status: "active", latest: "5", page: "2" }} basePath={BASE} />);
    expect(details().open).toBe(true);
    expect(details().querySelector("summary")?.textContent).toBe("Filters (2 applied)");
    rerender(<ReportView item={ITEM} report={null} error="Bad" params={{ page: "0" }} basePath={BASE} />);
    expect(details().open).toBe(true);
  });

  it("shows a refused input above the kept form", () => {
    render(<ReportView item={ITEM} report={null} error="'From' must be on or before 'To'" params={{ from: "2026-10-05", to: "2026-10-01" }} basePath={BASE} />);
    expect(screen.getByRole("alert").textContent).toBe("'From' must be on or before 'To'");
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-05");
    expect(screen.queryByRole("table")).toBeNull();
  });
});
