import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateImport from "@/components/RecruiterCandidateImport";

// hrc-013 (DEC-SCOPE-391 I12): template + source + file -> check (preview, nothing written) -> import with an Idempotency-Key -> report.
const SOURCES = { items: [{ id: "s1", name: "Referral", active: true, sort_order: 1 }, { id: "s2", name: "Job fair", active: true, sort_order: 2 }], total: 2, limit: 100, offset: 0 };
const PREVIEW = {
  total_rows: 3, new_count: 1, matched_count: 1, error_count: 1,
  rows: [
    { row_number: 2, status: "new", name: "Kiran Rao", candidate: null, same_as_row: null, reason: null },
    { row_number: 3, status: "matched", name: "Asha", candidate: { id: "c9", candidate_code: "CAN-000009", name: "Asha Verma" }, same_as_row: null, reason: "Already a candidate" },
    { row_number: 4, status: "error", name: "No Contact", candidate: null, same_as_row: null, reason: "Enter a mobile number or an email" },
  ],
};
const REPORT = {
  id: "b1", file_name: "people.csv", source: { id: "s2", name: "Job fair" }, uploaded_by: { id: "u1", full_name: "Rita Recruiter" },
  total_rows: 3, created_count: 1, matched_count: 1, error_count: 1, created_at: "2026-11-04T10:00:00Z", replayed: false,
  rows: [
    { row_number: 2, status: "created", candidate: { id: "c10", candidate_code: "CAN-000010", name: "Kiran Rao" }, reason: null },
    { row_number: 3, status: "matched", candidate: { id: "c9", candidate_code: "CAN-000009", name: "Asha Verma" }, reason: null },
    { row_number: 4, status: "error", candidate: null, reason: "Enter a mobile number or an email" },
  ],
};
const EMPTY = { items: [], total: 0, limit: 50, offset: 0 };

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
let previews: { status: number; body: unknown }[];
let commits: { status: number; body: unknown }[];
let fetchMock: ReturnType<typeof vi.fn>;
let keys = 0;

beforeEach(() => {
  keys = 0;
  previews = [];
  commits = [];
  vi.stubGlobal("crypto", { ...crypto, randomUUID: () => `key-${++keys}` });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const reply = (queue: { status: number; body: unknown }[], fallback: unknown, status: number) => {
      const next = queue.shift() ?? { status, body: fallback };
      return next.status === 0 ? Promise.reject(new TypeError("Failed to fetch")) : json(next.status, next.body);
    };
    if (url === "/api/v1/recruiter/candidate-imports/preview") return reply(previews, PREVIEW, 200);
    if (url === "/api/v1/recruiter/candidate-imports" && init?.method === "POST") return reply(commits, REPORT, 201);
    if (url.startsWith("/api/v1/recruiter/candidate-imports?")) return json(200, EMPTY);
    if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) return json(200, SOURCES);
    return json(404, {});
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const calls = (url: string) => fetchMock.mock.calls.filter(([u, init]) => u === url && (init as RequestInit | undefined)?.method === "POST");
const keyOf = (call: unknown[]) => ((call[1] as RequestInit).headers as Record<string, string>)["Idempotency-Key"];
async function ready() {
  render(<RecruiterCandidateImport />);
  await screen.findByRole("option", { name: "Job fair" });
}
function choose(name = "people.csv", size = 10) {
  fireEvent.change(screen.getByLabelText("Candidate source"), { target: { value: "s2" } });
  fireEvent.change(screen.getByLabelText(/Filled-in candidates file/), { target: { files: [new File(["x".repeat(size)], name, { type: "text/csv" })] } });
}
const check = () => fireEvent.click(screen.getByRole("button", { name: /Check file|Checking/ }));

describe("RecruiterCandidateImport", () => {
  it("offers the template, the column reference and the active sources", async () => {
    await ready();
    expect(screen.getByRole("link", { name: /Download the template/ })).toHaveAttribute("href", "/api/v1/recruiter/candidate-imports/template");
    expect(screen.getByText("preferred_locations")).toBeInTheDocument();
    expect(await screen.findByText("No imports yet.")).toBeInTheDocument();
  });

  it("checks the file locally before sending anything", async () => {
    await ready();
    check();
    expect(await screen.findByText("Choose the candidate source and a filled-in .csv or .xlsx file first.")).toBeInTheDocument();
    choose("people.txt");
    check();
    expect(await screen.findByText("Choose a .csv or .xlsx file.")).toBeInTheDocument();
    choose("people.csv", 1024 * 1024 + 1);
    check();
    expect(await screen.findByText("The file is larger than 1 MB.")).toBeInTheDocument();
    expect(calls("/api/v1/recruiter/candidate-imports/preview")).toHaveLength(0);
  });

  it("previews every row, then imports the same file once with a key and shows the report", async () => {
    await ready();
    choose();
    check();
    const table = await screen.findByRole("table", { name: "Rows in this file" });
    expect(screen.getByText(/1 new candidate, 1 already a candidate, 1 row with an error/)).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "CAN-000009" })).toHaveAttribute("href", "/recruiter/candidates/c9");
    expect(within(table).getByText("Enter a mobile number or an email")).toBeInTheDocument();
    const sent = calls("/api/v1/recruiter/candidate-imports/preview")[0][1] as RequestInit;
    expect((sent.body as FormData).get("source_id")).toBe("s2");
    fireEvent.click(screen.getByRole("button", { name: "Import 1 new candidate" }));
    expect(await screen.findByRole("heading", { name: "Import result" })).toBeInTheDocument();
    expect(screen.getByText(/1 added, 1 already a candidate, 1 error/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download the full report/ })).toHaveAttribute("href", "/api/v1/recruiter/candidate-imports/b1/report.csv");
    expect(screen.getByRole("link", { name: "CAN-000010" })).toHaveAttribute("href", "/recruiter/candidates/c10");
    const commit = calls("/api/v1/recruiter/candidate-imports");
    expect(commit).toHaveLength(1);
    expect(keyOf(commit[0])).toBe("key-2"); // a new key whenever the source (key-1) or the file (key-2) changes
    expect(((commit[0][1] as RequestInit).body as FormData).get("source_id")).toBe("s2");
  });

  it("retries a dropped import with the same key and a double click sends once", async () => {
    commits = [{ status: 0, body: null }];
    await ready();
    choose();
    check();
    const button = await screen.findByRole("button", { name: "Import 1 new candidate" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(await screen.findByText(/The connection dropped/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Import 1 new candidate" }));
    await screen.findByRole("heading", { name: "Import result" });
    const commit = calls("/api/v1/recruiter/candidate-imports");
    expect(commit).toHaveLength(2);
    expect(keyOf(commit[0])).toBe(keyOf(commit[1]));
  });

  it("shows the server's refusal and lets the recruiter choose another file", async () => {
    previews = [{ status: 422, body: { detail: "Unknown column: phone_number; Missing required column: name" } }];
    await ready();
    choose();
    check();
    expect(await screen.findByText("Unknown column: phone_number; Missing required column: name")).toBeInTheDocument();
    check();
    await screen.findByRole("table", { name: "Rows in this file" });
    fireEvent.click(screen.getByRole("button", { name: "Choose another file" }));
    await waitFor(() => expect(screen.queryByRole("table", { name: "Rows in this file" })).not.toBeInTheDocument());
  });

  it("has nothing to import when no row is new", async () => {
    previews = [{ status: 200, body: { ...PREVIEW, new_count: 0, total_rows: 2, rows: PREVIEW.rows.slice(1) } }];
    await ready();
    choose();
    check();
    expect(await screen.findByText(/Nothing new to add/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Import \d/ })).not.toBeInTheDocument();
  });
});
