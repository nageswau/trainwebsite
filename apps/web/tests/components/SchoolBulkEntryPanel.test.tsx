import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SchoolBulkEntryPanel from "@/components/SchoolBulkEntryPanel";
import { BULK_RESULTS } from "@/lib/bulkEntry";

// ENH-028 -- bulk entry panel (spec §9): template-first, one upload, a row-by-row report; a retry of the same file reuses its
// Idempotency-Key so a dropped connection can never add the rows twice.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const REPORT = {
  id: "b1", target_type: "academic_result", status: "completed", total_rows: 2, accepted_count: 1, rejected_count: 1,
  rows: [
    { row_number: 2, status: "accepted", error_message: null, student_code: "AAAA1111", created_record_id: "r1" },
    { row_number: 3, status: "rejected", error_message: "marks_obtained must not exceed max_marks", student_code: "BBBB2222", created_record_id: null },
  ],
};

let keys = 0;
beforeEach(() => {
  keys = 0;
  refresh.mockClear();
  vi.stubGlobal("crypto", { ...crypto, randomUUID: () => `key-${++keys}` });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function open() {
  render(<SchoolBulkEntryPanel target={BULK_RESULTS} hasStudents />);
  fireEvent.click(screen.getByText(BULK_RESULTS.title));
}

function choose(name = "marks.csv") {
  fireEvent.change(screen.getByLabelText(/Filled-in results file/), { target: { files: [new File(["student_code\n"], name, { type: "text/csv" })] } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Upload results" }));
}

function headerOf(call: unknown[]): string {
  return ((call[1] as RequestInit).headers as Record<string, string>)["Idempotency-Key"];
}

describe("SchoolBulkEntryPanel", () => {
  it("explains the empty portfolio instead of offering a form", () => {
    render(<SchoolBulkEntryPanel target={BULK_RESULTS} hasStudents={false} />);
    fireEvent.click(screen.getByText(BULK_RESULTS.title));
    expect(screen.getByText(/No students in your portfolio yet/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Upload results" })).toBeNull();
  });

  it("offers the pre-filled template as a download link and documents every column", () => {
    open();
    const link = screen.getByRole("link", { name: /Download the pre-filled template/ });
    expect(link.getAttribute("href")).toBe("/api/v1/school/academic-team/results/bulk-template");
    expect(link.hasAttribute("download")).toBe(true);
    for (const column of BULK_RESULTS.columns) expect(screen.getByRole("cell", { name: column.name })).toBeTruthy();
  });

  it("asks for a file before uploading", async () => {
    vi.stubGlobal("fetch", vi.fn());
    open();
    submit();
    expect((await screen.findByRole("alert")).textContent).toBe("Choose a filled-in CSV file first.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("disables the form while uploading", async () => {
    let finish: (r: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    open();
    choose();
    submit();
    const button = screen.getByRole("button", { name: "Uploading…" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.closest("form")?.getAttribute("aria-busy")).toBe("true");
    finish(new Response(JSON.stringify(REPORT), { status: 201 }));
    await screen.findByRole("heading", { name: "Upload result" });
  });

  it("shows the report in file order, focuses it and refreshes the page data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(REPORT), { status: 201 })));
    open();
    choose();
    submit();
    const heading = await screen.findByRole("heading", { name: "Upload result" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getByText(/1 of 2 rows added, 1 rejected/)).toBeTruthy();
    const rows = within(heading.parentElement!).getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows[0]).toContain("AAAA1111");
    expect(rows[0]).toContain("Added");
    expect(rows[1]).toContain("Rejected");
    expect(rows[1]).toContain("marks_obtained must not exceed max_marks");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("shows the API's message for a refused file", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Missing required column: subject" }), { status: 422 })));
    open();
    choose();
    submit();
    expect((await screen.findByRole("alert")).textContent).toBe("Missing required column: subject");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("retries the same file with the same key after a dropped connection, and uses a new key for a new file", async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(new Response(JSON.stringify(REPORT), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(REPORT), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    open();
    choose();
    submit();
    expect((await screen.findByRole("alert")).textContent).toMatch(/connection dropped/);
    expect((screen.getByRole("button", { name: "Upload results" }) as HTMLButtonElement).disabled).toBe(false);
    submit();
    await screen.findByRole("heading", { name: "Upload result" });
    choose("second.csv");
    submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(headerOf(fetchMock.mock.calls[0])).toBe(headerOf(fetchMock.mock.calls[1]));
    expect(headerOf(fetchMock.mock.calls[2])).not.toBe(headerOf(fetchMock.mock.calls[0]));
  });
});
