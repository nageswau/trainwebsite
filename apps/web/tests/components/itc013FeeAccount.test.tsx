import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FeePaymentPanel from "@/components/FeePaymentPanel";

// itc-013 (DEC-SCOPE-344): the IT student's Fees page leads with a fee summary per enrolment; a paid fee card names its mode and
// transaction reference (AC4). The overseas student's Payments page (same panel) never asks for IT fee accounts.
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ACCOUNT = {
  enrollment_id: "e1", enrollment_code: "ENR-1", course: "Full Stack Java", batch: "FSJ-Nov", currency: "INR",
  course_fee: 45000, discount_approved: 0, tax: 0, total_payable: 45000, paid_confirmed: 20000, credits: 0, balance: 25000, state: "partially_paid",
};
const PAID = { id: "p1", amount: 20000, currency: "INR", provider: "manual", status: "paid", due_date: null, reference_type: "enrollment_fee", is_manual: true,
  emi_schedule_id: null, installment_no: null, gross_amount: 20000, discount_amount: 0, paid_at: "2026-11-02T05:00:00Z", payment_mode: "upi", provider_reference: "UPI-123" };

function serve(accounts: unknown, status = 200) {
  const fetchMock = vi.fn(async (url: string) =>
    url === "/api/v1/it/student/fee-accounts" ? json(accounts, status) : url === "/api/v1/payments/mine" ? json([PAID]) : url === "/api/v1/payments/mode" ? json({ mode: "live" }) : json([]),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Fee summary (itc-013)", () => {
  it("shows every figure of the account and the balance", async () => {
    serve([ACCOUNT]);
    render(<FeePaymentPanel feeAccounts />);
    const card = await screen.findByLabelText("Fee account for Full Stack Java");
    expect(within(card).getByText("Partially paid")).toBeInTheDocument();
    for (const [label, value] of [["Course fee", "INR 45,000.00"], ["Paid", "INR 20,000.00"], ["Tax", "INR 0.00"], ["Balance", "INR 25,000.00"]]) {
      expect(within(card).getByText(label).nextElementSibling).toHaveTextContent(value);
    }
  });

  it("says when nothing was billed, and when the student has no enrolment", async () => {
    serve([{ ...ACCOUNT, state: "not_billed", course_fee: 0, total_payable: 0, paid_confirmed: 0, balance: 0 }]);
    render(<FeePaymentPanel feeAccounts />);
    expect(await screen.findByText("No fee has been billed for this enrolment yet.")).toBeInTheDocument();
    cleanup();
    serve([]);
    render(<FeePaymentPanel feeAccounts />);
    expect(await screen.findByText("You are not enrolled in a course yet.")).toBeInTheDocument();
  });

  it("shows a negative balance as a credit", async () => {
    serve([{ ...ACCOUNT, balance: -500, state: "fully_paid" }]);
    render(<FeePaymentPanel feeAccounts />);
    const card = await screen.findByLabelText("Fee account for Full Stack Java");
    expect(within(card).getByText("Credit").nextElementSibling).toHaveTextContent("INR 500.00");
  });

  it("explains a failed load", async () => {
    serve({ detail: "boom" }, 500);
    render(<FeePaymentPanel feeAccounts />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your fee summary could not be loaded");
  });

  it("names the paid fee's mode and transaction reference", async () => {
    serve([ACCOUNT]);
    render(<FeePaymentPanel feeAccounts />);
    expect(await screen.findByText("Paid by UPI · Ref UPI-123")).toBeInTheDocument();
  });

  it("is not loaded for the overseas student's payments", async () => {
    const fetchMock = serve([ACCOUNT]);
    render(<FeePaymentPanel />);
    await screen.findByText("Paid by UPI · Ref UPI-123");
    expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain("/api/v1/it/student/fee-accounts");
    expect(screen.queryByText("Fee summary")).toBeNull();
  });
});
