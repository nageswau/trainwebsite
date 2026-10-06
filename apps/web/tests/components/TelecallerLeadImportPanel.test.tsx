import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TelecallerLeadImportPanel from "@/components/TelecallerLeadImportPanel";

// tel-006 (IM1, spec §4): pick a campaign, download the template, upload; the per-row report.
const product = (group: string) => ({ id: `p-${group}`, name: group === "other" ? "Career Guidance" : "Cyber Security", group, active: true });
const campaign = (id: string, group = "it") => ({ id, name: `Camp ${id}`, source: "facebook", product: product(group), start_date: "2026-09-01", end_date: null, active: true });
const CAMPAIGNS = { items: [campaign("c1"), campaign("c2", "other")], total: 2, limit: 100, offset: 0 };
const REPORT = {
  id: "b1", campaign: { id: "c1", name: "Camp c1" }, division: "it", total_rows: 3, created_count: 1, attached_count: 1, rejected_count: 1,
  created_at: "2026-10-06T10:00:00Z",
  rows: [
    { row_number: 2, status: "created", lead_id: "l1", lead_code: "LD-000101", error: null },
    { row_number: 3, status: "attached", lead_id: "l0", lead_code: "LD-000007", error: null },
    { row_number: 4, status: "rejected", lead_id: null, lead_code: null, error: "phone Enter a valid mobile number" },
  ],
};

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
let uploads: { status: number; body: unknown }[];
let fetchMock: ReturnType<typeof vi.fn>;
let keys = 0;

beforeEach(() => {
  keys = 0;
  uploads = [];
  vi.stubGlobal("crypto", { ...crypto, randomUUID: () => `key-${++keys}` });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/telecaller/campaigns")) return json(200, CAMPAIGNS);
    if (init?.method === "POST") {
      const next = uploads.shift() ?? { status: 201, body: REPORT };
      return next.status === 0 ? Promise.reject(new TypeError("Failed to fetch")) : json(next.status, next.body);
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
const formOf = (i: number) => (posts()[i][1] as RequestInit).body as FormData;
async function ready() {
  render(<TelecallerLeadImportPanel />);
  await screen.findByRole("option", { name: /Camp c1/ });
}
const pick = (id: string) => fireEvent.change(screen.getByLabelText(/^Campaign/), { target: { value: id } });
function choose(name = "leads.csv", size = 10) {
  fireEvent.change(screen.getByLabelText(/Filled-in leads file/), { target: { files: [new File(["x".repeat(size)], name, { type: "text/csv" })] } });
}
const submit = () => fireEvent.click(screen.getByRole("button", { name: /Import leads|Importing/ }));

describe("TelecallerLeadImportPanel", () => {
  it("lists the active campaigns and links the template", async () => {
    await ready();
    expect(fetchMock.mock.calls[0][0]).toContain("active=true");
    expect(screen.getByRole("link", { name: /Download the template/ }).getAttribute("href")).toBe("/api/v1/telecaller/imports/template");
    expect(screen.queryByLabelText(/Division/)).toBeNull();
  });

  it("asks for a division only for a campaign whose product is in the Other group", async () => {
    await ready();
    pick("c2");
    expect(screen.getByLabelText(/Division/)).toBeTruthy();
    pick("c1");
    expect(screen.queryByLabelText(/Division/)).toBeNull();
  });

  it.each([
    ["no campaign", () => choose(), "Choose a campaign first."],
    ["no file", () => pick("c1"), "Choose a filled-in CSV file first."],
    ["not a csv", () => { pick("c1"); choose("leads.xlsx"); }, "Choose a .csv file."],
    ["too large", () => { pick("c1"); choose("leads.csv", 1024 * 1024 + 1); }, "The file is larger than 1 MB."],
  ])("checks %s before uploading", async (_, act, message) => {
    await ready();
    act();
    submit();
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(posts()).toHaveLength(0);
  });

  it("uploads the file, campaign and division with an Idempotency-Key and shows the per-row report", async () => {
    const onImported = vi.fn();
    render(<TelecallerLeadImportPanel onImported={onImported} />);
    await screen.findByRole("option", { name: /Camp c2/ });
    pick("c2");
    fireEvent.change(screen.getByLabelText(/Division/), { target: { value: "overseas" } });
    choose();
    submit();
    const heading = await screen.findByRole("heading", { name: "Import result" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(keyOf(0)).toBe("key-1");
    expect([formOf(0).get("campaign_id"), formOf(0).get("division"), (formOf(0).get("file") as File).name]).toEqual(["c2", "overseas", "leads.csv"]);
    expect(screen.getByText("1 created, 1 added to existing leads, 1 rejected. Fix the rejected rows and upload just those.")).toBeTruthy();
    const table = screen.getAllByRole("table").at(-1) as HTMLElement;
    const rows = within(table).getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual(["2CreatedLD-000101-", "3Added to existing leadLD-000007-", "4Rejected-phone Enter a valid mobile number"]);
    expect(onImported).toHaveBeenCalledTimes(1);
  });

  it("retries the same file with the same key, and a new campaign or file gets a new key", async () => {
    uploads = [{ status: 0, body: null }, { status: 0, body: null }, { status: 0, body: null }];
    await ready();
    pick("c1");
    choose();
    submit();
    expect((await screen.findByRole("alert")).textContent).toMatch(/connection dropped/);
    submit();
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(keyOf(1)).toBe(keyOf(0));
    pick("c2");
    submit();
    await waitFor(() => expect(posts()).toHaveLength(3));
    expect(keyOf(2)).not.toBe(keyOf(0));
  });

  it("sends one request for a double click", async () => {
    await ready();
    pick("c1");
    choose();
    submit();
    submit();
    await screen.findByRole("heading", { name: "Import result" });
    expect(posts()).toHaveLength(1);
  });

  it("shows the server's reason for a rejected file", async () => {
    uploads = [{ status: 422, body: { detail: "Missing required column: phone" } }];
    await ready();
    pick("c1");
    choose();
    submit();
    expect((await screen.findByRole("alert")).textContent).toBe("Missing required column: phone");
    expect(screen.queryByRole("heading", { name: "Import result" })).toBeNull();
  });

  it("offers Retry when the campaigns fail to load", async () => {
    fetchMock.mockImplementationOnce(() => json(500, {}));
    render(<TelecallerLeadImportPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await screen.findByRole("option", { name: /Camp c1/ });
  });
});
