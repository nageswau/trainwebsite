import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyRevenue from "@/components/RecruiterCompanyRevenue";
import RecruiterReceivablesPanel from "@/components/RecruiterReceivablesPanel";
import type { CompanyRevenue, Invoice, InvoicePage } from "@/lib/recruiterRevenue";

// rec-031 (spec §4): the company's Revenue section (totals + one row per requirement) and the Receivables list (tabs with counts in the
// URL, the outstanding total, Overdue flagged, empty and error states).
const push = vi.fn();
let params = new URLSearchParams();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/recruiter/receivables", useSearchParams: () => params }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const PERSON = { id: "U1", full_name: "Priya Recruiter", active: true };
const FEE = { basis: "fixed" as const, value: "50000.00", source: "contract" as const, contract_status_label: "Signed", override: null };
const invoice = (over: Partial<Invoice> = {}): Invoice => ({
  id: "I1", invoice_number: "INV-001", invoice_date: "2026-09-01", due_date: "2026-09-30", amount: "150000.00", note: null, received: "0.00", outstanding: "150000.00",
  payment_status: "unpaid", payment_status_label: "Unpaid", overdue: true, cancelled_at: null, cancel_reason: null,
  requirement: { id: "R1", code: "REQ-000001", title: "Java Developer" }, company: { id: "C1", code: "COM-0001", name: "Acme" }, created_by: PERSON, payments: [],
  permissions: { can_pay: true, can_cancel: true }, created_at: "2026-09-01T05:30:00Z", ...over,
});
const page = (over: Partial<InvoicePage> = {}): InvoicePage => ({
  items: [invoice()], total: 1, limit: 50, offset: 0, counts: { outstanding: 2, overdue: 1, paid: 3, cancelled: 0 }, outstanding_total: "200000.00", ...over,
});
const company: CompanyRevenue = {
  requirements: [
    { requirement: { id: "R1", code: "REQ-000001", title: "Java Developer" }, status_label: "Open", selected: 3, joined: 2, fee: FEE, expected_revenue: "100000.00", invoiced: "100000.00", received: "40000.00", outstanding: "60000.00" },
  ],
  totals: { selected: 3, joined: 2, expected_revenue: "100000.00", invoiced: "100000.00", received: "40000.00", outstanding: "60000.00" },
};

let reply: (url: string) => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  params = new URLSearchParams();
  push.mockClear();
  reply = (url) => (url.includes("/companies/") ? res(company) : res(page()));
  fetchMock = vi.fn((url: string) => Promise.resolve(reply(url)));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterCompanyRevenue (rec-031)", () => {
  it("shows the totals and links each requirement", async () => {
    render(<RecruiterCompanyRevenue companyId="C1" />);
    const section = await screen.findByRole("region", { name: "Revenue" });
    expect(within(section).getByText("Outstanding amount").nextSibling?.textContent).toBe("₹60,000.00");
    const link = within(section).getByRole("link", { name: "Java Developer (REQ-000001)" });
    expect(link.getAttribute("href")).toBe("/recruiter/requirements/R1#requirement-revenue");
    expect(within(section).getByRole("link", { name: "Receivables for this company" }).getAttribute("href")).toBe("/recruiter/receivables?company_id=C1");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/recruiter/companies/C1/revenue", expect.anything());
  });

  it("shows an empty state and an error with Try again", async () => {
    reply = () => res({}, 500);
    render(<RecruiterCompanyRevenue companyId="C1" />);
    expect(await screen.findByText("Unable to load revenue.")).toBeTruthy();
    reply = () => res({ requirements: [], totals: { ...company.totals, selected: 0, joined: 0 } });
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No job requirements for this company yet.")).toBeTruthy();
  });
});

describe("RecruiterReceivablesPanel (rec-031)", () => {
  it("lists outstanding invoices with counts, the total and Overdue, and keeps the tab in the URL", async () => {
    render(<RecruiterReceivablesPanel />);
    const list = await screen.findByRole("list", { name: "Invoices" });
    expect(within(list).getByText("Overdue")).toBeTruthy();
    expect(within(list).getByRole("link", { name: "Java Developer (REQ-000001)" })).toBeTruthy();
    expect(screen.getByText("Outstanding in total: ₹2,00,000.00")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/recruiter/invoices?view=outstanding&limit=50&offset=0");
    fireEvent.click(screen.getByRole("button", { name: "Paid (3)" }));
    expect(push).toHaveBeenCalledWith("/recruiter/receivables?view=paid", { scroll: false });
  });

  it("filters by company from the URL, and shows the empty and error states", async () => {
    params = new URLSearchParams({ view: "cancelled", company_id: "C1" });
    reply = () => res(page({ items: [], total: 0 }));
    render(<RecruiterReceivablesPanel />);
    expect(await screen.findByText("No cancelled invoices.")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/recruiter/invoices?view=cancelled&limit=50&offset=0&company_id=C1");
    cleanup();
    reply = () => res({}, 500);
    render(<RecruiterReceivablesPanel />);
    expect(await screen.findByText("Unable to load invoices.")).toBeTruthy();
    reply = () => res(page());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("list", { name: "Invoices" })).toBeTruthy());
  });
});
