import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementRevenue from "@/components/RecruiterRequirementRevenue";
import type { Invoice, RequirementRevenue } from "@/lib/recruiterRevenue";

// rec-031 (spec §4; RV1-RV10): the requirement's Revenue section -- the §23 figures, the fee source, add an invoice, record a payment
// (the over-payment 422 lands on Amount), cancel, the manager-only fee override, the coded 409, and the loading / error states.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const PERSON = { id: "U1", full_name: "Priya Recruiter", active: true };

function invoice(over: Partial<Invoice> = {}): Invoice {
  return {
    id: "I1", invoice_number: "INV-001", invoice_date: "2026-10-01", due_date: "2026-10-31", amount: "150000.00", note: null, received: "100000.00",
    outstanding: "50000.00", payment_status: "part_paid", payment_status_label: "Part paid", overdue: false, cancelled_at: null, cancel_reason: null,
    requirement: { id: "R1", code: "REQ-000001", title: "Java Developer" }, company: { id: "C1", code: "COM-0001", name: "Acme" }, created_by: PERSON,
    payments: [{ id: "P1", received_on: "2026-10-05", amount: "100000.00", reference: "UTR 123", created_by: PERSON, created_at: "2026-10-05T05:30:00Z" }],
    permissions: { can_pay: true, can_cancel: false }, created_at: "2026-10-01T05:30:00Z", ...over,
  };
}

function revenue(over: Partial<RequirementRevenue> = {}): RequirementRevenue {
  return {
    requirement: { id: "R1", code: "REQ-000001", title: "Java Developer" }, company: { id: "C1", code: "COM-0001", name: "Acme" }, selected: 4, joined: 3,
    fee: { basis: "fixed", value: "50000.00", source: "contract", contract_status_label: "Signed", override: null },
    hires: [{ application_id: "A1", candidate: { id: "K1", code: "CAN-1", name: "Rahul" }, joined_on: "2026-10-01", fee: "50000.00" }],
    expected_revenue: "150000.00", unpriced_hires: 0, invoiced: "150000.00", received: "100000.00", outstanding: "50000.00", over_invoiced: false,
    invoices: [invoice()], permissions: { can_invoice: true, can_set_fee: false }, ...over,
  };
}

let read: () => Response;
let write: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  read = () => res(revenue());
  write = () => res({ invoice: invoice() }, 201);
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" || init?.method === "PUT") return Promise.resolve(write());
    if (url === "/api/v1/recruiter/requirements/R1/revenue") return Promise.resolve(read());
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sent = (method: string) => {
  const call = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === method)!;
  return { url: String(call[0]), body: JSON.parse(String((call[1] as RequestInit).body)) };
};

describe("RecruiterRequirementRevenue (rec-031)", () => {
  it("shows the section 23 figures with the fee source and the invoice with its payment", async () => {
    render(<RecruiterRequirementRevenue requirementId="R1" />);
    const figures = await screen.findByRole("region", { name: "Revenue" });
    expect(within(figures).getByText("Candidates selected").nextSibling?.textContent).toBe("4");
    expect(within(figures).getByText("Candidates joined").nextSibling?.textContent).toBe("3");
    expect(within(figures).getByText("₹50,000 per hire · from the company contract (Signed)")).toBeTruthy();
    expect(within(figures).getByText("Outstanding amount").nextSibling?.textContent).toBe("₹50,000.00");
    const card = within(screen.getByRole("list", { name: "Invoices" })).getAllByRole("listitem")[0];
    expect(within(card).getByText("INV-001")).toBeTruthy();
    expect(within(card).getByText("Part paid")).toBeTruthy();
    expect(within(card).getByText(/UTR 123/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Set fee for this requirement" })).toBeNull(); // RV10: the manager's
    expect(within(card).queryByRole("button", { name: /Cancel invoice/ })).toBeNull();
  });

  it("adds an invoice and re-reads the figures", async () => {
    render(<RecruiterRequirementRevenue requirementId="R1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add invoice" }));
    const form = screen.getByRole("form", { name: "Add invoice" });
    fireEvent.change(within(form).getByLabelText("Invoice number"), { target: { value: "INV-002" } });
    fireEvent.change(within(form).getByLabelText("Invoice date"), { target: { value: "2026-10-02" } });
    fireEvent.change(within(form).getByLabelText("Payment due"), { target: { value: "2026-11-01" } });
    fireEvent.change(within(form).getByLabelText("Amount (₹)"), { target: { value: "50000" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save invoice" }));
    expect(await screen.findByText("Invoice saved.")).toBeTruthy();
    expect(sent("POST")).toEqual({
      url: "/api/v1/recruiter/invoices",
      body: { requirement_id: "R1", invoice_number: "INV-002", invoice_date: "2026-10-02", due_date: "2026-11-01", amount: "50000", note: null },
    });
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/v1/recruiter/requirements/R1/revenue")).toHaveLength(2);
  });

  it("puts the over-payment 422 on Amount (AC2)", async () => {
    write = () => res({ detail: [{ loc: ["body", "amount"], msg: "This payment is more than the ₹50,000.00 outstanding", type: "value_error" }] }, 422);
    render(<RecruiterRequirementRevenue requirementId="R1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Record payment for INV-001" }));
    const form = screen.getByRole("form", { name: "Record payment for INV-001" });
    fireEvent.change(within(form).getByLabelText("Received date"), { target: { value: "2026-10-06" } });
    fireEvent.change(within(form).getByLabelText("Amount (₹)"), { target: { value: "60000" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save payment" }));
    expect(await within(form).findByText("This payment is more than the ₹50,000.00 outstanding")).toBeTruthy();
    expect(within(form).getByLabelText("Amount (₹)").getAttribute("aria-invalid")).toBe("true");
    expect(sent("POST").url).toBe("/api/v1/recruiter/invoices/I1/payments");
  });

  it("cancels an unpaid invoice with a reason, and shows a coded 409 as its message", async () => {
    read = () => res(revenue({ invoices: [invoice({ received: "0.00", outstanding: "150000.00", payment_status: "unpaid", payment_status_label: "Unpaid", payments: [], permissions: { can_pay: true, can_cancel: true } })] }));
    write = () => res({ detail: { message: "An invoice with payments can't be cancelled", code: "invoice_has_payments" } }, 409);
    render(<RecruiterRequirementRevenue requirementId="R1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel invoice INV-001" }));
    const form = screen.getByRole("form", { name: "Cancel invoice INV-001" });
    fireEvent.change(within(form).getByLabelText("Reason"), { target: { value: "Wrong amount" } });
    fireEvent.click(within(form).getByRole("button", { name: "Cancel invoice" }));
    expect(await screen.findByText("An invoice with payments can't be cancelled")).toBeTruthy();
    expect(sent("POST")).toEqual({ url: "/api/v1/recruiter/invoices/I1/cancel", body: { reason: "Wrong amount" } });
  });

  it("lets the manager set the fee override, and flags over-invoicing and unpriced hires", async () => {
    read = () => res(revenue({ permissions: { can_invoice: true, can_set_fee: true }, over_invoiced: true, unpriced_hires: 1 }));
    const saved = revenue({ fee: { basis: "fixed", value: "60000.00", source: "requirement", contract_status_label: null, override: { basis: "fixed", value: "60000.00" } } });
    write = () => {
      read = () => res(saved); // the re-read after the write sees the new fee
      return res(saved);
    };
    render(<RecruiterRequirementRevenue requirementId="R1" />);
    expect(await screen.findByText("Invoiced more than the expected revenue from joined candidates. Check for a candidate who did not join.")).toBeTruthy();
    expect(screen.getByText(/1 joined candidate has no CTC in INR/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Set fee for this requirement" }));
    const form = screen.getByRole("form", { name: "Fee for this requirement" });
    fireEvent.change(within(form).getByLabelText(/^Fee basis/), { target: { value: "fixed" } });
    fireEvent.change(within(form).getByLabelText(/^Fee per hire/), { target: { value: "60000" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save fee" }));
    expect(await screen.findByText("₹60,000 per hire · set for this requirement")).toBeTruthy();
    expect(sent("PUT")).toEqual({ url: "/api/v1/recruiter/requirements/R1/fee", body: { fee_basis: "fixed", fee_value: "60000" } });
  });

  it("shows the empty state, and an error with Try again", async () => {
    read = () => res({ detail: "boom" }, 500);
    render(<RecruiterRequirementRevenue requirementId="R1" />);
    expect(await screen.findByText("Unable to load revenue.")).toBeTruthy();
    read = () => res(revenue({ invoices: [], invoiced: "0.00", received: "0.00", outstanding: "0.00" }));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No invoices yet.")).toBeTruthy();
  });
});
