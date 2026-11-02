import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadCounseling from "@/components/LeadCounseling";
import { counselingBody, counselingValues, type CounselingRecord } from "@/lib/leadCounseling";

// itc-010 (DEC-SCOPE-343): the counseling section -- list, record, edit, read-only, and the load / empty / error states.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const person = { id: "u1", full_name: "Asha Counselor" };
const record = (over: Partial<CounselingRecord> = {}): CounselingRecord => ({
  id: "c1", recommended_product: { id: "p1", name: "Python Full Stack" }, objections: [{ id: "o1", name: "Fee too high" }], objection_notes: "Weekend only",
  fee_quoted: "45000.00", expected_joining_date: "2026-12-15", decision_maker: "parent", outcome: "interested", next_follow_up: "2026-11-10",
  notes: "Parent will pay", author: person, updated_by: person, created_at: "2026-11-02T05:00:00Z", updated_at: "2026-11-02T05:00:00Z", ...over,
});
const products = [{ id: "p1", group: "it", name: "Python Full Stack", team: "it", program: null, active: true, sort_order: 1 },
  { id: "p2", group: "overseas", name: "UK Masters", team: "overseas", program: null, active: true, sort_order: 2 }];
const objections = [{ id: "o1", name: "Fee too high", active: true, sort_order: 1 }, { id: "o2", name: "Needs time to decide", active: true, sort_order: 2 }];

let records: CounselingRecord[];
let fetchMock: ReturnType<typeof vi.fn>;
let listStatus: number;
beforeEach(() => {
  records = [record()];
  listStatus = 200;
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" || init?.method === "PATCH") return Promise.resolve(res(record({ id: "c2", outcome: "needs_time" }), init.method === "POST" ? 201 : 200));
    if (url.includes("/telecaller/products")) return Promise.resolve(res({ items: products, total: 2, limit: 100, offset: 0 }));
    if (url.includes("/counseling-objections")) return Promise.resolve(res({ items: objections, total: 2, limit: 100, offset: 0 }));
    return Promise.resolve(listStatus === 200 ? res(page(records)) : res({ detail: "x" }, listStatus));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LeadCounseling (itc-010)", () => {
  it("lists a session with every field", async () => {
    render(<LeadCounseling listUrl="/api/v1/counselor/leads/l1/counseling" writeUrl={null} />);
    const item = await screen.findByRole("listitem");
    for (const text of ["Interested", "Python Full Stack", "₹45,000.00", "Fee too high", "Weekend only", "Parent will pay"]) {
      expect(within(item).getByText(text, { exact: false })).toBeTruthy();
    }
    expect(within(item).getByText("Parent")).toBeTruthy(); // the decision-maker, exactly
    expect(screen.queryByRole("button", { name: /Record counseling/ })).toBeNull(); // read only
  });

  it("shows the empty and the error state", async () => {
    records = [];
    render(<LeadCounseling listUrl="/x" writeUrl={null} />);
    expect(await screen.findByText("No counseling recorded yet.")).toBeTruthy();
    cleanup();
    listStatus = 500;
    render(<LeadCounseling listUrl="/x" writeUrl={null} />);
    expect(await screen.findByText("Unable to load the counseling sessions.")).toBeTruthy();
  });

  it("records a session with IT courses only, and needs an outcome", async () => {
    const onChanged = vi.fn();
    render(<LeadCounseling listUrl="/api/v1/counselor/leads/l1/counseling" writeUrl={(id) => `/api/v1/counselor/leads/l1/counseling${id ? `/${id}` : ""}`} onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record counseling" }));
    const form = await screen.findByRole("form", { name: "Record counseling" });
    await waitFor(() => expect(within(form).getByRole("option", { name: "Python Full Stack" })).toBeTruthy());
    expect(within(form).queryByRole("option", { name: "UK Masters" })).toBeNull();
    fireEvent.click(within(form).getByRole("button", { name: "Save counseling" }));
    expect(await within(form).findByText("Choose the counseling outcome")).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "needs_time" } });
    fireEvent.click(within(form).getByLabelText("Needs time to decide"));
    fireEvent.change(within(form).getByLabelText("Course fee quoted (₹)"), { target: { value: "45000" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save counseling" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ outcome: "needs_time", objection_ids: ["o2"], fee_quoted: "45000", notes: null });
    expect(await screen.findByText("Counseling recorded.")).toBeTruthy();
  });

  it("edits a session with PATCH", async () => {
    render(<LeadCounseling listUrl="/l" writeUrl={(id) => `/w${id ? `/${id}` : ""}`} />);
    fireEvent.click(await screen.findByRole("button", { name: /Edit counseling/ }));
    const form = await screen.findByRole("form", { name: "Edit counseling" });
    expect((within(form).getByLabelText("Course fee quoted (₹)") as HTMLInputElement).value).toBe("45000.00");
    fireEvent.click(within(form).getByRole("button", { name: "Save counseling" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === "/w/c1" && init?.method === "PATCH")).toBe(true));
  });

  it("maps blanks to null and back", () => {
    expect(counselingBody(counselingValues())).toMatchObject({ recommended_product_id: null, fee_quoted: null, objection_ids: [], outcome: "" });
    expect(counselingValues(record()).fee_quoted).toBe("45000.00");
  });
});
