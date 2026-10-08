import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UniversityImportPanel from "@/components/UniversityImportPanel";

// upc-005 (IM10, IM12, spec §4): download the template, upload, the per-row report and the history.
const REPORT = {
  id: "b1", uploaded_by: { id: "u1", full_name: "Hema Head" }, total_rows: 3, created_count: 1, duplicate_count: 1, invalid_count: 1,
  created_at: "2026-10-08T10:00:00Z",
  rows: [
    { row_number: 2, status: "created", name: "ABC University", country: "GB", university_id: "x1", university_code: "UNV-000101", matches: [], reason: null },
    { row_number: 3, status: "duplicate", name: "Old College", country: "GB", university_id: null, university_code: null, matches: ["UNV-000007"], reason: "Already in the University Master: UNV-000007" },
    { row_number: 4, status: "invalid", name: "Nowhere U", country: "Atlantis", university_id: null, university_code: null, matches: [], reason: "Unknown country: Atlantis" },
  ],
};
const HISTORY = { items: [{ ...REPORT, rows: undefined }], total: 1, limit: 50, offset: 0 };
const EMPTY = { items: [], total: 0, limit: 50, offset: 0 };

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
let uploads: { status: number; body: unknown }[];
let history: { status: number; body: unknown }[];
let fetchMock: ReturnType<typeof vi.fn>;
let keys = 0;

beforeEach(() => {
  keys = 0;
  uploads = [];
  history = [];
  vi.stubGlobal("crypto", { ...crypto, randomUUID: () => `key-${++keys}` });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const next = uploads.shift() ?? { status: 201, body: REPORT };
      return next.status === 0 ? Promise.reject(new TypeError("Failed to fetch")) : json(next.status, next.body);
    }
    if (url.startsWith("/api/v1/partnership/universities/imports?")) {
      const next = history.shift() ?? { status: 200, body: EMPTY };
      return json(next.status, next.body);
    }
    return json(404, {});
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const posts = () => fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "POST");
const keyOf = (i: number) => ((posts()[i][1] as RequestInit).headers as Record<string, string>)["Idempotency-Key"];
function choose(name = "universities.csv", size = 10) {
  fireEvent.change(screen.getByLabelText(/Filled-in universities file/), { target: { files: [new File(["x".repeat(size)], name, { type: "text/csv" })] } });
}
const submit = () => fireEvent.click(screen.getByRole("button", { name: /Import universities|Importing/ }));

describe("UniversityImportPanel", () => {
  it("offers the template and the column reference", async () => {
    render(<UniversityImportPanel />);
    expect(screen.getByRole("link", { name: /Download the template/ })).toHaveAttribute("href", "/api/v1/partnership/universities/imports/template");
    expect(screen.getByText("institution_type")).toBeInTheDocument();
    expect(await screen.findByText("No imports yet.")).toBeInTheDocument();
  });

  it("checks the file before uploading", async () => {
    render(<UniversityImportPanel />);
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a filled-in CSV file first.");
    choose("list.xlsx");
    submit();
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a .csv file.");
    choose("big.csv", 1024 * 1024 + 1);
    submit();
    expect(screen.getByRole("alert")).toHaveTextContent("The file is larger than 1 MB.");
    expect(posts()).toHaveLength(0);
  });

  it("uploads with an Idempotency-Key and shows the counts, the rows not created and the report download", async () => {
    history.push({ status: 200, body: EMPTY }, { status: 200, body: HISTORY });
    render(<UniversityImportPanel />);
    choose();
    submit();
    const heading = await screen.findByRole("heading", { name: "Import result" });
    expect(posts()).toHaveLength(1);
    expect(posts()[0][0]).toBe("/api/v1/partnership/universities/import");
    expect(keyOf(0)).toBe("key-1");
    expect(((posts()[0][1] as RequestInit).body as FormData).get("file")).toBeInstanceOf(File);
    expect(heading).toHaveFocus();
    expect(screen.getByText(/1 created, 1 duplicate, 1 invalid/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Rows not created" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3); // header + duplicate + invalid; the created row is only in the download
    expect(within(table).getByText("Already in the University Master: UNV-000007")).toBeInTheDocument();
    expect(within(table).getByText("Unknown country: Atlantis")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download the full report/ })).toHaveAttribute("href", "/api/v1/partnership/universities/imports/b1/report.csv");
    expect(await screen.findByText("Hema Head")).toBeInTheDocument(); // the history reloads after an import
  });

  it("says when every row was created and when nothing was", async () => {
    uploads.push({ status: 201, body: { ...REPORT, total_rows: 1, duplicate_count: 0, invalid_count: 0, rows: [REPORT.rows[0]] } });
    render(<UniversityImportPanel />);
    choose();
    submit();
    expect(await screen.findByText("1 created, 0 duplicates, 0 invalid.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Rows not created" })).not.toBeInTheDocument();
    uploads.push({ status: 201, body: { ...REPORT, total_rows: 1, created_count: 0, duplicate_count: 1, invalid_count: 0, rows: [REPORT.rows[1]] } });
    choose("again.csv");
    submit();
    expect(await screen.findByText(/No universities were added/)).toBeInTheDocument();
  });

  it("shows a file-level error and keeps the key for a retry after a dropped connection", async () => {
    uploads.push({ status: 422, body: { detail: "Missing required column: city" } }, { status: 0, body: null }, { status: 201, body: REPORT });
    render(<UniversityImportPanel />);
    choose();
    submit();
    expect(await screen.findByText("Missing required column: city")).toBeInTheDocument();
    choose("fixed.csv");
    submit();
    expect(await screen.findByText(/connection dropped/)).toBeInTheDocument();
    submit();
    await screen.findByRole("heading", { name: "Import result" });
    expect(keyOf(1)).toBe(keyOf(2)); // the same file retried replays instead of importing twice
    expect(keyOf(0)).not.toBe(keyOf(1));
  });

  it("uploads once on a double click", async () => {
    render(<UniversityImportPanel />);
    choose();
    submit();
    submit();
    await screen.findByRole("heading", { name: "Import result" });
    expect(posts()).toHaveLength(1);
  });

  it("offers a retry when the history cannot be loaded", async () => {
    history.push({ status: 500, body: {} }, { status: 200, body: HISTORY });
    render(<UniversityImportPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    const row = await screen.findByText("Hema Head");
    expect(within(row.closest("tr") as HTMLElement).getByRole("link", { name: /Report/ })).toHaveAttribute("href", "/api/v1/partnership/universities/imports/b1/report.csv");
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
});
