import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminSchoolBulkOnboardPanel from "@/components/AdminSchoolBulkOnboardPanel";
import { SCHOOL_ONBOARDING } from "@/lib/bulkEntry";

// ENH-029 -- bulk school onboarding panel (docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md §9, AC11).
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

type Row = Record<string, unknown>;
const accepted = (n: number, email_status: string | null = "sent"): Row => ({
  row_number: n, status: "accepted", error_message: null, created_record_id: `s${n}`, school_code: `CODE000${n}`, school_name: `School ${n}`,
  coordinator_id: `u${n}`, coordinator_email: `c${n}@x.in`, email_status,
});
const rejected = (n: number, error_message: string): Row => ({
  row_number: n, status: "rejected", error_message, created_record_id: null, school_code: null, school_name: null,
  coordinator_id: null, coordinator_email: null, email_status: null,
});
const report = (rows: Row[]) => {
  const ok = rows.filter((r) => r.status === "accepted").length;
  return { id: "b1", target_type: "school_onboarding", status: "completed", total_rows: rows.length, accepted_count: ok, rejected_count: rows.length - ok, rows };
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

const fileInput = () => screen.getByLabelText(/Filled-in schools file/) as HTMLInputElement;
function choose(name = "schools.csv", size = 10) {
  fireEvent.change(fileInput(), { target: { files: [new File(["x".repeat(size)], name, { type: "text/csv" })] } });
}
const submit = () => fireEvent.click(screen.getByRole("button", { name: /Upload schools|Uploading/ }));
const respond = (status: number, body: object) => vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });
const keyOf = (mock: ReturnType<typeof vi.fn>, i: number) => ((mock.mock.calls[i][1] as RequestInit).headers as Record<string, string>)["Idempotency-Key"];
const resultTable = () => screen.getAllByRole("table").at(-1) as HTMLElement; // the result table, not the column reference

describe("AdminSchoolBulkOnboardPanel", () => {
  it("is an action card like its sibling admin panels, with the template link first", () => {
    const { container } = render(<AdminSchoolBulkOnboardPanel />);
    expect((container.firstElementChild as HTMLElement).classList.contains("action-card")).toBe(true);
    expect(screen.getByRole("heading", { level: 3, name: "Onboard several schools (CSV)" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download the template/ }).getAttribute("href")).toBe("/api/v1/overseas-admin/schools/bulk-template");
  });

  it("documents the columns in the server template's order", () => {
    expect(SCHOOL_ONBOARDING.columns.map((c) => c.name)).toEqual([
      "name", "city", "state", "tier", "tier_valid_until", "coordinator_full_name", "coordinator_email", "branch", "address", "contact_number",
      "email", "website", "grades_available", "board", "partnership_date", "mou_reference", "edusphere_bdm", "monthly_visit_schedule", "vice_principal_name",
    ]);
    expect(SCHOOL_ONBOARDING.columns.filter((c) => c.required).map((c) => c.name)).toEqual(["name", "coordinator_full_name", "coordinator_email"]);
  });

  it.each([
    ["no file", () => undefined, "Choose a filled-in CSV file first."],
    ["a file over 1 MB", () => choose("big.csv", 1024 * 1024 + 1), "The file is larger than 1 MB."],
    ["a non-CSV file", () => choose("schools.xlsx"), "Choose a .csv file."],
  ])("pre-checks %s without calling the server", async (_label, act, message) => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminSchoolBulkOnboardPanel />);
    act();
    submit();
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uploads from a plain-HTTP page, where crypto.randomUUID does not exist (QA-029-01)", async () => {
    vi.stubGlobal("crypto", { getRandomValues: (a: Uint8Array) => a.fill(7) });
    const fetchMock = respond(201, report([accepted(2)]));
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    await screen.findByRole("heading", { name: "Upload result" });
    expect(screen.queryByText("Choose a filled-in CSV file first.")).toBeNull();
    expect(keyOf(fetchMock, 0)).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });

  it("disables the form while uploading and announces honest progress", async () => {
    let resolve: (value: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise((r) => { resolve = r; })));
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    const busy = screen.getByRole("button", { name: "Uploading…" });
    expect(busy.hasAttribute("disabled")).toBe(true);
    expect(fileInput().disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toMatch(/creating schools and sending set-password emails/);
    resolve({ ok: true, status: 201, json: async () => report([accepted(2)]) });
    await screen.findByRole("heading", { name: "Upload result" });
    expect(screen.getByRole("button", { name: "Upload schools" }).hasAttribute("disabled")).toBe(false);
  });

  it("shows the server's file-level error and retries the same file with the same key", async () => {
    const fetchMock = respond(422, { detail: "Unknown column: role" });
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    expect((await screen.findByRole("alert")).textContent).toBe("Unknown column: role");
    submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect([keyOf(fetchMock, 0), keyOf(fetchMock, 1)]).toEqual(["key-1", "key-1"]);
  });

  it("explains a dropped connection, retries with the same key, and gives a new file a new key", async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("network")).mockResolvedValue({ ok: true, status: 201, json: async () => report([accepted(2)]) });
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    expect((await screen.findByRole("alert")).textContent).toMatch(/The connection dropped/);
    submit();
    await screen.findByRole("heading", { name: "Upload result" });
    expect([keyOf(fetchMock, 0), keyOf(fetchMock, 1)]).toEqual(["key-1", "key-1"]);
    choose("next.csv");
    submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(keyOf(fetchMock, 2)).toBe("key-2");
  });

  it.each([
    ["all accepted", [accepted(2), accepted(3)], "form-message", /^2 schools onboarded\.$/],
    ["some rejected", [accepted(2), rejected(3, "Email already exists")], "form-warning", /^1 of 2 schools onboarded, 1 rejected\. Schools that succeeded are kept/],
    ["all rejected", [rejected(2, "Email already exists")], "form-error", /^No schools were onboarded\. Fix the rows below and upload again\.$/],
  ])("summarises %s with the matching tone, focuses the result and refreshes the page", async (_label, rows, cls, text) => {
    vi.stubGlobal("fetch", respond(201, report(rows)));
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    const heading = await screen.findByRole("heading", { name: "Upload result" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getByText(text).className).toBe(cls);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(fileInput().value).toBe("");
  });

  it("describes each row: rejected reason, emailed, not delivered, replayed", async () => {
    vi.stubGlobal("fetch", respond(201, report([rejected(2, "Email already exists"), accepted(3, "sent"), accepted(4, "not_configured"), accepted(5, null)])));
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    await screen.findByRole("heading", { name: "Upload result" });
    const rows = within(resultTable()).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("Rejected")).toBeTruthy();
    expect(within(rows[0]).getByText("Email already exists")).toBeTruthy();
    expect(within(rows[1]).getByText("Added")).toBeTruthy();
    expect(within(rows[1]).getByText("CODE0003")).toBeTruthy();
    expect(within(rows[1]).getByText("c3@x.in")).toBeTruthy();
    expect(within(rows[1]).getByText("Set-password link emailed")).toBeTruthy();
    expect(within(rows[2]).getByText("Email not delivered — re-send from the Users page")).toBeTruthy();
    expect(within(rows[3]).getByText("Check the Users page for set-password status")).toBeTruthy();
    expect(screen.getByText(/1 welcome email was not delivered — re-send from the Users page\./)).toBeTruthy();
  });

  it("spans the full action grid and marks its result table for the stacked layout (QA-029-02/03)", async () => {
    vi.stubGlobal("fetch", respond(201, report([accepted(2)])));
    const { container } = render(<AdminSchoolBulkOnboardPanel />);
    expect((container.firstElementChild as HTMLElement).classList.contains("bulk-onboarding")).toBe(true);
    choose();
    submit();
    await screen.findByRole("heading", { name: "Upload result" });
    expect(resultTable().className).toBe("table bulk-report");
  });

  it("labels every result cell for the stacked mobile layout", async () => {
    vi.stubGlobal("fetch", respond(201, report([accepted(2)])));
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    await screen.findByRole("heading", { name: "Upload result" });
    const cells = within(resultTable()).getAllByRole("cell");
    expect(cells.map((c) => c.getAttribute("data-label"))).toEqual(["Row", "Result", "School ID", "School", "Coordinator", "Detail"]);
  });
});
