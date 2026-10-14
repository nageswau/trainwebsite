import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CapitalEntryForm from "@/components/CapitalEntryForm";
import CapitalSharesForm from "@/components/CapitalSharesForm";
import PartnerCapital from "@/components/PartnerCapital";
import type { Capital, CapitalAccount } from "@/lib/partnerCapital";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ARJUN = { id: "a1", full_name: "Arjun Partner" };
const MEERA = { id: "m2", full_name: "Meera Partner" };
const account = (person: typeof ARJUN, over: Partial<CapitalAccount> = {}): CapitalAccount => ({
  partner: { ...person, active: true }, invested: "500000.00", additional: "0.00", withdrawals: "0.00", balance: "500000.00", returns: "0.00",
  share_pct: "50.00", commitment: "1000000.00", outstanding: "500000.00", profit_share: "250000.00", ...over,
}); // prettier-ignore
const capital = (over: Partial<Capital> = {}): Capital => ({
  as_of: "2026-10-14", month: "2026-10", period: "year", label: "Financial year 2026-27 to date", net_profit: "500000.00",
  accounts: [account(ARJUN), account(MEERA)],
  totals: { invested: "1000000.00", additional: "0.00", withdrawals: "0.00", balance: "1000000.00", returns: "0.00", share_pct: "100.00", commitment: "2000000.00", outstanding: "1000000.00", profit_share: "500000.00" },
  partners: [ARJUN, MEERA],
  entries: { items: [{ id: "e1", partner: ARJUN, entry_date: "2024-04-01", kind: "initial", amount: "500000.00", note: "Opening", created_by: MEERA, created_at: "2024-04-01T10:00:00Z" }], total: 1, limit: 25, offset: 0 },
  shares: [{ id: "s1", partner: ARJUN, effective_from: "2024-04-01", share_pct: "50.00", commitment: "1000000.00", in_force: true, updated_by: MEERA, updated_at: "2024-04-01T10:00:00Z" }],
  ...over,
}); // prettier-ignore
const QUERY = { month: "", period: "year" as const, offset: 0 };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("PartnerCapital (mgmt-015 §24)", () => {
  it("shows every figure per partner and the total, and the period's net profit", () => {
    render(<PartnerCapital data={capital()} error="" query={QUERY} />);
    const table = screen.getByRole("table", { name: "Capital accounts" });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Figure", "Arjun Partner", "Meera Partner", "Total"]);
    const balance = within(table).getByRole("row", { name: /Capital balance/ });
    expect(balance.textContent).toContain("₹5,00,000.00");
    expect(balance.textContent).toContain("₹10,00,000.00");
    expect(within(table).getByRole("row", { name: /Share %/ }).textContent).toContain("100.00%");
    expect(screen.getByText(/Financial year 2026-27 to date/).textContent).toContain("₹5,00,000.00");
    expect(screen.queryByText(/not 100%/)).toBeNull();
  });

  it("warns when the shares in force do not total 100% (AC1)", () => {
    render(<PartnerCapital data={capital({ totals: { ...capital().totals, share_pct: "90.00" } })} error="" query={QUERY} />);
    expect(screen.getByText("Shares in force total 90.00%, not 100%.")).toBeTruthy();
  });

  it("shows a negative balance or profit share in red with words, and a former partner as such (CP1, CP11)", () => {
    const gone = { ...account(MEERA, { balance: "-500.00", profit_share: "-10.00" }), partner: { ...MEERA, active: false } };
    render(<PartnerCapital data={capital({ accounts: [account(ARJUN), gone] })} error="" query={QUERY} />);
    const table = screen.getByRole("table", { name: "Capital accounts" });
    expect(within(table).getByRole("columnheader", { name: /Meera Partner/ }).textContent).toContain("former partner");
    const balance = within(table).getByRole("row", { name: /Capital balance/ });
    expect(balance.querySelector(".pnl-loss")?.textContent).toBe("-₹500.00");
    expect(balance.textContent).toContain("Withdrawals exceed the capital put in");
    expect(within(table).getByRole("row", { name: /Profit share/ }).querySelector(".pnl-loss")).not.toBeNull();
  });

  it("lists the entries and the share history, and pages the entries", () => {
    render(<PartnerCapital data={capital({ entries: { ...capital().entries, total: 30 } })} error="" query={QUERY} />);
    const entries = screen.getByRole("table", { name: "Capital entries" });
    expect(within(entries).getAllByRole("row")[1].textContent).toContain("Initial capital");
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toBe("/management/capital?offset=25");
    const shares = screen.getByRole("table", { name: "Share % history" });
    expect(within(shares).getAllByRole("row")[1].textContent).toContain("In force");
  });

  it("shows the empty states and keeps the period form after an error", () => {
    render(<PartnerCapital data={capital({ accounts: [], entries: { items: [], total: 0, limit: 25, offset: 0 }, shares: [] })} error="" query={QUERY} />);
    expect(screen.getByText("No partners yet.")).toBeTruthy();
    expect(screen.getByText("No capital entries yet.")).toBeTruthy();
    expect(screen.getByText("No share % set yet.")).toBeTruthy();
    cleanup();
    render(<PartnerCapital data={null} error="Capital accounts are unavailable right now." query={QUERY} />);
    expect(screen.getByRole("alert").textContent).toBe("Capital accounts are unavailable right now.");
    expect(screen.getByRole("form", { name: "Choose a period" })).toBeTruthy();
  });
});

describe("CapitalEntryForm (CP3, CP11)", () => {
  const open = () => {
    render(<CapitalEntryForm partners={[ARJUN, MEERA]} accounts={[account(ARJUN)]} today="2026-10-14" />);
    fireEvent.click(screen.getByRole("button", { name: "Record a capital entry" }));
    fireEvent.change(screen.getByLabelText("Partner"), { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-05-01" } });
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "withdrawal" } });
    fireEvent.change(screen.getByLabelText("Amount (₹)"), { target: { value: "600000" } });
  };

  it("asks again before a withdrawal over the balance, then sends it once", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ id: "e2" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    open();
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("more than Arjun Partner's capital balance of ₹5,00,000.00");
    const confirm = screen.getByRole("button", { name: "Record it anyway" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ partner_id: "a1", entry_date: "2026-05-01", kind: "withdrawal", amount: "600000", note: null });
    expect(screen.getByRole("status").textContent).toBe("Capital entry recorded.");
  });

  it("names a problem before sending and keeps the entry when the API refuses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ detail: "Choose an active partner" }, 422));
    vi.stubGlobal("fetch", fetchMock);
    open();
    fireEvent.change(screen.getByLabelText("Amount (₹)"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    expect(screen.getByRole("alert").textContent).toBe("Enter the amount in rupees with up to 2 decimals.");
    fireEvent.change(screen.getByLabelText("Amount (₹)"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Choose an active partner"));
    expect((screen.getByLabelText("Amount (₹)") as HTMLInputElement).value).toBe("100");
  });
});

describe("CapitalSharesForm (CP5, CP6)", () => {
  it("starts from the shares in force and sends the partners with a share", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ items: [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CapitalSharesForm partners={[ARJUN, MEERA]} accounts={[account(ARJUN, { commitment: null })]} month="2026-10" />);
    fireEvent.click(screen.getByRole("button", { name: "Set share %" }));
    expect((screen.getByLabelText("Arjun Partner share %") as HTMLInputElement).value).toBe("50.00");
    fireEvent.change(screen.getByLabelText("Meera Partner share %"), { target: { value: "40" } });
    fireEvent.change(screen.getByLabelText("Meera Partner committed capital (₹)"), { target: { value: "1000000" } });
    expect(screen.getByText("These shares total 90.00%, not 100%.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save shares" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/management/capital/shares");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      effective_from: "2026-10",
      shares: [{ partner_id: "a1", share_pct: "50.00", commitment: null }, { partner_id: "m2", share_pct: "40", commitment: "1000000" }],
    });
  });
});
