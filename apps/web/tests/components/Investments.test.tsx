import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InvestmentForm from "@/components/InvestmentForm";
import InvestmentRegister from "@/components/InvestmentRegister";
import type { Investment, InvestmentPage } from "@/lib/investments";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const MEERA = { id: "22222222-2222-2222-2222-222222222222", full_name: "Meera Partner" };
const investment = (over: Partial<Investment> = {}): Investment => ({
  id: "11111111-1111-1111-1111-111111111111", code: "INV-000001", invested_on: "2026-04-01", investor_kind: "company", investor: null,
  amount: "500000.00", purpose: "Marketing Campaign", vertical: "shared", expected_return: "1500000.00", actual_return: "1800000.00", roi: "260.00",
  status: "completed", notes: null, created_by: MEERA, updated_by: MEERA, created_at: "2026-04-01T10:00:00Z", updated_at: "2026-04-01T10:00:00Z", ...over,
});
const page = (over: Partial<InvestmentPage> = {}): InvestmentPage => ({
  items: [investment(), investment({ id: "33333333-3333-3333-3333-333333333333", code: "INV-000002", actual_return: null, roi: null, status: "active", investor_kind: "partner", investor: MEERA })],
  total: 2, limit: 25, offset: 0, totals: { count: 2, invested: "1000000.00", actual_return: "1800000.00", roi: "260.00" }, investors: [MEERA], ...over,
});
const NO_FILTERS = { date_from: "", date_to: "", vertical: "", status: "", offset: 0 };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockReset();
  refresh.mockReset();
});

describe("InvestmentRegister (mgmt-014 §23)", () => {
  it("shows the totals and every investment with its ROI, linking each to its detail", () => {
    render(<InvestmentRegister data={page()} error="" filters={NO_FILTERS} />);
    const totals = screen.getByRole("list", { name: "Investment totals" });
    expect(totals.textContent).toContain("₹10,00,000.00");
    expect(totals.textContent).toContain("260.00%");
    const table = screen.getByRole("table", { name: "Investments" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(rows[1].textContent).toContain("Company");
    expect(rows[1].textContent).toContain("260.00%");
    expect(rows[2].textContent).toContain("Meera Partner");
    expect(rows[2].textContent).toContain("—"); // ROI unknown
    expect(within(table).getByRole("link", { name: "INV-000001" }).getAttribute("href")).toBe("/management/investments/11111111-1111-1111-1111-111111111111");
  });

  it("says when nothing matches, keeps the filter form, and shows an error above it", () => {
    render(<InvestmentRegister data={page({ items: [], total: 0, totals: { count: 0, invested: "0.00", actual_return: "0.00", roi: null } })} error="" filters={{ ...NO_FILTERS, vertical: "it" }} />);
    expect(screen.getByRole("status").textContent).toMatch(/No investments match/);
    expect((screen.getByLabelText("Vertical") as HTMLSelectElement).value).toBe("it");
    cleanup();
    render(<InvestmentRegister data={null} error="Investments are unavailable right now." filters={NO_FILTERS} />);
    expect(screen.getByRole("alert").textContent).toBe("Investments are unavailable right now.");
    expect(screen.getByRole("form", { name: "Investment filters" })).toBeTruthy();
  });

  it("pages with links that keep the filters", () => {
    render(<InvestmentRegister data={page({ total: 60, offset: 25 })} error="" filters={{ ...NO_FILTERS, status: "active", offset: 25 }} />);
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe("/management/investments?status=active");
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toBe("/management/investments?status=active&offset=50");
  });
});

describe("InvestmentForm (mgmt-014 add / edit)", () => {
  const open = (name: RegExp) => fireEvent.click(screen.getByRole("button", { name }));
  const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

  it("checks the entry before sending, and names the field", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<InvestmentForm investors={[MEERA]} />);
    open(/Add investment/);
    type("Date", "2026-04-01");
    type("Investor", "partner");
    fireEvent.click(screen.getByRole("button", { name: "Save investment" }));
    expect(screen.getByRole("alert").textContent).toBe("Choose the partner who invested.");
    expect(screen.getByLabelText("Partner").getAttribute("aria-invalid")).toBe("true");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("adds an investment once, then opens it", async () => {
    let resolve: (r: Response) => void = () => {};
    const fetchMock = vi.fn(() => new Promise<Response>((r) => { resolve = r; }));
    vi.stubGlobal("fetch", fetchMock);
    render(<InvestmentForm investors={[MEERA]} />);
    open(/Add investment/);
    type("Date", "2026-04-01");
    type("Amount (₹)", "500000");
    type("Purpose", "Marketing Campaign");
    type("Business vertical", "shared");
    type("Expected return (₹)", "1500000");
    const save = screen.getByRole("button", { name: "Save investment" });
    fireEvent.click(save);
    fireEvent.click(save); // a double click sends once
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/management/investments");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({ amount: "500000", expected_return: "1500000", actual_return: null, investor_user_id: null });
    resolve(res(investment(), 201));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/management/investments/11111111-1111-1111-1111-111111111111"));
  });

  it("edits with PATCH, keeps a former partner in the list, and refreshes", async () => {
    const fetchMock = vi.fn(async () => res(investment()));
    vi.stubGlobal("fetch", fetchMock);
    const gone = { id: "44444444-4444-4444-4444-444444444444", full_name: "Old Partner" };
    render(<InvestmentForm investors={[MEERA]} investment={investment({ investor_kind: "partner", investor: gone, actual_return: null, roi: null })} />);
    open(/Edit investment/);
    expect((screen.getByLabelText("Partner") as HTMLSelectElement).value).toBe(gone.id);
    type("Actual return (₹)", "1800000");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/management/investments/11111111-1111-1111-1111-111111111111");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toMatchObject({ actual_return: "1800000", investor_user_id: gone.id });
    expect(screen.getByRole("status").textContent).toBe("Investment saved.");
  });

  it("shows the API's reason and keeps the entry", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => res({ detail: "Choose an active partner as the investor" }, 422)));
    render(<InvestmentForm investors={[MEERA]} investment={investment()} />);
    open(/Edit investment/);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Choose an active partner as the investor"));
    expect((screen.getByLabelText("Purpose") as HTMLInputElement).value).toBe("Marketing Campaign");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("cancel closes the form without sending", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<InvestmentForm investors={[MEERA]} />);
    open(/Add investment/);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Save investment" })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
