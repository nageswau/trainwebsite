import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import OverseasStudentFinance from "@/components/OverseasStudentFinance";
import { studentTab, type StudentFinance } from "@/lib/overseasStudent360";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const empty: StudentFinance = { payments: [], deposits: [], refunds: [] };
const finance: StudentFinance = {
  payments: [
    {
      id: "p1", description: "Service fee", amount: "25000.00", currency: "INR", status: "paid", status_label: "Paid", due_date: null,
      created_at: "2026-10-01T10:00:00Z", installment_no: null, invoice_no: "INV-1", receipt_no: "RCT-1", can_download: false,
    },
    {
      id: "p2", description: "Service fee (instalment 2)", amount: "1200.50", currency: "INR", status: "pending", status_label: "Pending", due_date: "2027-01-15",
      created_at: "2026-10-02T10:00:00Z", installment_no: 2, invoice_no: null, receipt_no: null, can_download: false,
    },
  ],
  deposits: [
    {
      application_id: "a1", application_code: "APP-1", university: "Alpha Uni", mine: true, source: "counselor", required: true, amount: "3000.00", currency: "GBP",
      due_date: "2026-12-01", status: "paid_to_university", status_label: "Paid directly to the university", paid_on: "2026-10-01", refund: null,
      receipt: { id: "d1", name: "Deposit receipt", can_download: true },
    },
    {
      application_id: "a2", application_code: "APP-2", university: "Gamma Uni", mine: false, source: "agency", required: true, amount: "50000.00", currency: "INR",
      due_date: null, status: "refunded", status_label: "Refunded", paid_on: "2026-09-01", refund: { amount: "45000.00", refunded_on: "2026-09-30", reason: "Visa refused" }, receipt: null,
    },
  ],
  refunds: [{ kind: "deposit", description: "University deposit — Gamma Uni", amount: "45000.00", currency: "INR", refunded_on: "2026-09-30", application_code: "APP-2" }],
};

describe("student 360 finance tab (ccrm-039)", () => {
  it("is a link tab", () => {
    expect(studentTab("finance")).toBe("finance");
  });

  it("says each section is empty in words", () => {
    render(<OverseasStudentFinance finance={empty} />);
    expect(screen.getByText("No fees or payments recorded for this student.")).toBeInTheDocument();
    expect(screen.getByText("No university deposit recorded on any application.")).toBeInTheDocument();
    expect(screen.getByText("No refunds.")).toBeInTheDocument();
  });

  it("lists fees with status, invoice and receipt numbers, and no download for the counselor", () => {
    render(<OverseasStudentFinance finance={finance} />);
    const fees = screen.getByRole("region", { name: "Fees and payments" });
    expect(within(fees).getByText("Service fee")).toBeInTheDocument();
    expect(within(fees).getByText("INR 25,000.00")).toBeInTheDocument();
    expect(within(fees).getByText(/Invoice INV-1/)).toBeInTheDocument();
    expect(within(fees).getByText(/Receipt RCT-1/)).toBeInTheDocument();
    expect(within(fees).getByText("Pending")).toBeInTheDocument();
    expect(within(fees).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows each application's deposit, its refund and the refunds list", () => {
    render(<OverseasStudentFinance finance={finance} />);
    const deposits = screen.getByRole("region", { name: "University deposits" });
    expect(within(deposits).getByText("Paid directly to the university")).toBeInTheDocument();
    expect(within(deposits).getByText(/GBP 3,000.00 · Due 01 Dec 2026 · Paid 01 Oct 2026/)).toBeInTheDocument();
    expect(within(deposits).getByText("APP-2 · Paid by the agency")).toBeInTheDocument();
    expect(within(deposits).getByRole("button", { name: "Download Deposit receipt" })).toBeInTheDocument();
    expect(within(deposits).getByText(/Refunded INR 45,000.00/)).toBeInTheDocument();
    const refunds = screen.getByRole("region", { name: "Refunds" });
    expect(within(refunds).getByText("University deposit — Gamma Uni")).toBeInTheDocument();
  });

  it("QA-02: colours a status by meaning -- paid green, pending amber, refunded muted (always with the word)", () => {
    render(<OverseasStudentFinance finance={finance} />);
    const fees = screen.getByRole("region", { name: "Fees and payments" });
    expect(within(fees).getByText("Paid")).toHaveClass("status");
    expect(within(fees).getByText("Paid")).not.toHaveClass("pending");
    expect(within(fees).getByText("Pending")).toHaveClass("status", "pending");
    expect(within(screen.getByRole("region", { name: "University deposits" })).getByText("Refunded")).toHaveClass("status", "closed");
  });

  it("QA-01: the admin's two buttons say which file they download", () => {
    const admin = { ...finance, payments: [{ ...finance.payments[0], can_download: true }] };
    render(<OverseasStudentFinance finance={admin} />);
    expect(screen.getByRole("button", { name: "Download invoice INV-1" })).toHaveTextContent("Invoice");
    expect(screen.getByRole("button", { name: "Download receipt RCT-1" })).toHaveTextContent("Receipt");
  });

  it("offers the Overseas Admin the invoice and receipt downloads from the payments route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ url: "https://files.example/r", expires_in: 900 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("open", vi.fn());
    const admin = { ...finance, payments: finance.payments.map((p) => ({ ...p, can_download: true })) };
    render(<OverseasStudentFinance finance={admin} />);
    expect(screen.getAllByRole("button", { name: /Download invoice/ })).toHaveLength(1); // the second fee has no invoice yet
    fireEvent.click(screen.getByRole("button", { name: "Download receipt RCT-1" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/payments/p1/receipt");
  });
});
