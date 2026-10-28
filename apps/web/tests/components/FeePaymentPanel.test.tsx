import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FeePaymentPanel from "@/components/FeePaymentPanel";
import { TEST_MODE_TEXT } from "@/components/PaymentModeBanner";

// nehn-022 (DEC-SCOPE-283) AC2: the student Fee Payments card carries the test-mode banner; live mode hides it.
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ROW = { id: "p1", amount: 1000, currency: "INR", provider: "razorpay", status: "pending", due_date: null, reference_type: "service_fee", is_manual: false, emi_schedule_id: null, installment_no: null };

function serve(mode: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => (url === "/api/v1/payments/mode" ? json({ mode }) : url === "/api/v1/payments/mine" ? json([ROW]) : json([]))),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("FeePaymentPanel test-mode banner (nehn-022)", () => {
  it("shows the banner in test mode", async () => {
    serve("test");
    render(<FeePaymentPanel />);
    expect(await screen.findByText(TEST_MODE_TEXT)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pay Now" })).toBeInTheDocument();
  });

  it("hides the banner in live mode", async () => {
    serve("live");
    render(<FeePaymentPanel />);
    await screen.findByRole("button", { name: "Pay Now" });
    await waitFor(() => expect(screen.queryByText(TEST_MODE_TEXT)).toBeNull());
  });
});

// nehn-020 (DEC-SCOPE-290) AC1: the student's payment document is the receipt; no fee card offers an invoice.
describe("FeePaymentPanel documents (nehn-020)", () => {
  it("offers the receipt on a paid fee and never an invoice", async () => {
    const paid = { ...ROW, id: "p2", status: "paid" };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url === "/api/v1/payments/mine" ? json([ROW, paid]) : url === "/api/v1/payments/mode" ? json({ mode: "live" }) : json([]))));
    render(<FeePaymentPanel />);
    expect(await screen.findByRole("button", { name: "Receipt" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pay Now" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /invoice/i })).toBeNull();
  });
});

// nehn-019 (DEC-SCOPE-315) AC5/AC3: a discounted fee shows original, discount and payable; a paid fee its paid date; the EMI plan its
// paid amount and balance; rows from before nehn-019 (no ledger fields) render unchanged.
describe("FeePaymentPanel discount and balance (nehn-019)", () => {
  function serveRows(rows: unknown[], schedules: unknown[] = []) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url === "/api/v1/payments/mine" ? json(rows) : url === "/api/v1/payments/emi-schedule" ? json(schedules) : json({ mode: "live" }),
      ),
    );
  }

  it("shows the original amount, the discount and the payable amount", async () => {
    serveRows([{ ...ROW, amount: 9000, gross_amount: 10000, discount_amount: 1000, paid_at: null }]);
    render(<FeePaymentPanel />);
    expect(await screen.findByText("Original INR 10,000 · Discount INR 1,000")).toBeInTheDocument();
    expect(screen.getByText(/^Payable INR 9,000/)).toBeInTheDocument();
  });

  it("says 'Amount paid', not 'Payable', on a paid discounted fee (QA19-01)", async () => {
    serveRows([{ ...ROW, status: "paid", amount: 9000, gross_amount: 10000, discount_amount: 1000, paid_at: "2026-10-28T05:00:00Z" }]);
    render(<FeePaymentPanel />);
    expect(await screen.findByText("Amount paid INR 9,000")).toBeInTheDocument();
    expect(screen.queryByText(/Payable/)).toBeNull();
  });

  it("shows the paid date in India time", async () => {
    serveRows([{ ...ROW, status: "paid", gross_amount: 1000, discount_amount: 0, paid_at: "2026-10-27T20:00:00Z" }]);
    render(<FeePaymentPanel />);
    expect(await screen.findByText("Paid on 28 Oct 2026")).toBeInTheDocument();
    expect(screen.queryByText(/Discount/)).toBeNull();
  });

  it("renders a row without ledger fields as before", async () => {
    serveRows([ROW]);
    render(<FeePaymentPanel />);
    expect(await screen.findByText("INR 1,000")).toBeInTheDocument();
    expect(screen.queryByText(/Original|Paid on/)).toBeNull();
  });

  it("shows the EMI plan's paid amount and remaining balance", async () => {
    const schedule = {
      id: "s1", reference_type: "enrollment_fee", total_amount: 30000, currency: "INR", installment_count: 2, paid_amount: 12000, balance: 15000,
      installments: [
        { id: "i1", installment_no: 1, amount: 12000, discount_amount: 3000, due_date: null, status: "paid", paid_at: "2026-10-28T05:00:00Z" },
        { id: "i2", installment_no: 2, amount: 15000, discount_amount: 0, due_date: null, status: "pending", paid_at: null },
      ],
    };
    serveRows([], [schedule]);
    render(<FeePaymentPanel />);
    expect(await screen.findByText("Paid INR 12,000 · Remaining balance INR 15,000")).toBeInTheDocument();
    expect(screen.getByText(/Installment 1: INR 12,000 \(INR 3,000 discount applied\)/)).toBeInTheDocument();
  });
});
