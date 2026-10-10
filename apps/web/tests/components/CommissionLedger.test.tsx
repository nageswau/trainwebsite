import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CommissionLedger from "@/components/CommissionLedger";
import { amountsText, applicationLabel, type CommissionLedger as Ledger, type CommissionReceipt, type LedgerApplication, moneyText, receiptsUrl } from "@/lib/commissionLedger";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const U1 = "11111111-2222-4333-8444-555555555555";
const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });
const person = { id: "p1", full_name: "Hema Head", active: true };
const app = (over: Partial<LedgerApplication> = {}): LedgerApplication => ({
  id: "aaaaaaaa-0000-4000-8000-000000000001", course: "MSc Data Science", intake: "Jan 2026", reference: null, enrolled_on: "2026-01-15",
  status: "counted", status_label: "Counted", term_id: "t1", currency: "GBP", amount: "2700.00", ...over,
});
const receipt = (over: Partial<CommissionReceipt> = {}): CommissionReceipt => ({
  id: "r1", amount: "1000.50", currency: "GBP", received_on: "2026-02-01", reference: "SWIFT-JAN-26", note: "Jan intake", application_ids: [app().id],
  created_by: person, created_at: "2026-02-01T05:00:00Z", ...over,
});
const ledger = (over: Partial<Ledger> = {}): Ledger => ({
  university: { id: U1, name: "ABC University", university_code: "UNV-000001" },
  totals: [{ currency: "GBP", expected: "2700.00", received: "1000.50", outstanding: "1699.50" }],
  applications: [app(), app({ id: "aaaaaaaa-0000-4000-8000-000000000002", status: "awaiting_visa", status_label: "Awaiting visa approval", currency: null, amount: null })],
  applications_total: 2, receipts: [receipt()], receipts_total: 1, permissions: { can_record: true }, ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("commissionLedger lib (upc-019)", () => {
  it("words money per currency, keeps a negative sign, and never names a student", () => {
    expect(moneyText("GBP", "2700.00")).toBe("GBP 2,700.00");
    expect(moneyText("GBP", "-300.00")).toBe("-GBP 300.00");
    expect(amountsText([])).toBe("—");
    expect(amountsText([{ currency: "GBP", amount: "5400.00" }, { currency: "USD", amount: "50.00" }])).toBe("GBP 5,400.00 · USD 50.00");
    expect(applicationLabel(app())).toBe("#aaaaaaaa · MSc Data Science · Jan 2026");
    expect(applicationLabel(app({ reference: "UNI-77", course: null }))).toBe("UNI-77 · No programme · Jan 2026");
    expect(receiptsUrl(U1, "r1")).toBe(`/api/v1/partnership/universities/${U1}/commission/receipts/r1`);
  });
});

describe("CommissionLedger (upc-019)", () => {
  it("shows the per-currency totals, the enrolled applications with their status, and the receipts", () => {
    render(<CommissionLedger ledger={ledger()} today="2026-10-10" />);
    const section = screen.getByRole("region", { name: /Commission \(restricted\)/i });
    const totals = within(section).getByRole("table", { name: "Commission by currency" });
    expect(within(totals).getByRole("row", { name: /GBP/ }).textContent).toContain("GBP 1,699.50");
    const apps = within(section).getByRole("table", { name: "Enrolled applications and their expected commission" });
    expect(within(apps).getAllByRole("row")).toHaveLength(3);
    expect(apps.textContent).toContain("Awaiting visa approval");
    expect(apps.textContent).toContain("GBP 2,700.00");
    const receipts = within(section).getByRole("table", { name: "Commission received" });
    expect(receipts.textContent).toContain("SWIFT-JAN-26");
    expect(receipts.textContent).toContain("Hema Head");
  });

  it("has empty states and no record controls for a reader who may not record (a manager)", () => {
    render(<CommissionLedger ledger={ledger({ totals: [], applications: [], applications_total: 0, receipts: [], receipts_total: 0, permissions: { can_record: false } })} today="2026-10-10" />);
    expect(screen.getByText("No commission expected or received yet.")).toBeInTheDocument();
    expect(screen.getByText("No enrolled applications yet.")).toBeInTheDocument();
    expect(screen.getByText("No receipts recorded yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /record a receipt/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
  });

  it("says when only the latest applications are listed", () => {
    render(<CommissionLedger ledger={ledger({ applications_total: 250 })} today="2026-10-10" />);
    expect(screen.getByText(/latest 2 of 250 enrolled applications/i)).toBeInTheDocument();
  });

  it("checks the form before sending: amount, decimals, currency, reference and a future date", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<CommissionLedger ledger={ledger()} today="2026-10-10" />);
    fireEvent.click(screen.getByRole("button", { name: "Record a receipt" }));
    const form = screen.getByRole("form", { name: "Record a commission receipt" });
    const save = within(form).getByRole("button", { name: "Save receipt" });
    const error = () => within(form).getByRole("alert").textContent;
    fireEvent.click(save);
    expect(error()).toBe("Enter the amount received.");
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "-5" } });
    fireEvent.click(save);
    expect(error()).toBe("The amount must be more than 0.");
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "10.001" } });
    fireEvent.click(save);
    expect(error()).toBe("Use at most two decimal places.");
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "2700" } });
    fireEvent.click(save);
    expect(error()).toBe("Choose the currency.");
    fireEvent.change(within(form).getByLabelText("Currency"), { target: { value: "GBP" } });
    fireEvent.click(save);
    expect(error()).toBe("Enter the payment reference.");
    fireEvent.change(within(form).getByLabelText("Reference"), { target: { value: "REM-1" } });
    fireEvent.change(within(form).getByLabelText("Date received"), { target: { value: "2026-10-11" } });
    fireEvent.click(save);
    expect(error()).toBe("The date received can't be in the future.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("records a lump sum with linked applications once, then refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ receipt: receipt() }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<CommissionLedger ledger={ledger()} today="2026-10-10" />);
    fireEvent.click(screen.getByRole("button", { name: "Record a receipt" }));
    const form = screen.getByRole("form", { name: "Record a commission receipt" });
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "2700" } });
    fireEvent.change(within(form).getByLabelText("Currency"), { target: { value: "GBP" } });
    fireEvent.change(within(form).getByLabelText("Reference"), { target: { value: " SWIFT-JAN-26 " } });
    fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Jan intake" } });
    fireEvent.click(within(form).getByRole("checkbox", { name: /#aaaaaaaa · MSc Data Science · Jan 2026 · GBP 2,700.00/ }));
    fireEvent.click(within(form).getByRole("button", { name: "Save receipt" }));
    fireEvent.click(within(form).getByRole("button", { name: /Sav/ }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(receiptsUrl(U1));
    expect(JSON.parse(init.body)).toEqual({ amount: "2700", currency: "GBP", received_on: "2026-10-10", reference: "SWIFT-JAN-26", note: "Jan intake", application_ids: [app().id] });
    expect(await screen.findByRole("status")).toHaveTextContent("Receipt recorded.");
  });

  it("shows the API's message (e.g. a duplicate reference) and keeps the entry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "This reference is already recorded for this university" }, 409)));
    render(<CommissionLedger ledger={ledger()} today="2026-10-10" />);
    fireEvent.click(screen.getByRole("button", { name: "Record a receipt" }));
    const form = screen.getByRole("form", { name: "Record a commission receipt" });
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "2700" } });
    fireEvent.change(within(form).getByLabelText("Currency"), { target: { value: "GBP" } });
    fireEvent.change(within(form).getByLabelText("Reference"), { target: { value: "SWIFT-JAN-26" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save receipt" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("This reference is already recorded for this university");
    expect(within(form).getByLabelText("Reference")).toHaveValue("SWIFT-JAN-26");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("removes a receipt after an inline confirm, and Cancel keeps it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(null, 204));
    vi.stubGlobal("fetch", fetchMock);
    render(<CommissionLedger ledger={ledger()} today="2026-10-10" />);
    fireEvent.click(screen.getByRole("button", { name: "Remove receipt SWIFT-JAN-26" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Remove receipt SWIFT-JAN-26?" })).getByRole("button", { name: "Cancel" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove receipt SWIFT-JAN-26" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Remove receipt SWIFT-JAN-26?" })).getByRole("button", { name: "Yes, remove" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(receiptsUrl(U1, "r1"), expect.objectContaining({ method: "DELETE" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Receipt removed.");
  });
});
