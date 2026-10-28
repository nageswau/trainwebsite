import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import OverseasStudentFinance from "@/components/OverseasStudentFinance";
import type { StudentDeposit } from "@/lib/overseasStudent360";
import { studentTab, type StudentFinance } from "@/lib/overseasStudent360";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
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
      receipt: { id: "d1", name: "Deposit receipt", can_download: true }, can_upload: false,
    },
    {
      application_id: "a2", application_code: "APP-2", university: "Gamma Uni", mine: false, source: "agency", required: true, amount: "50000.00", currency: "INR",
      due_date: null, status: "refunded", status_label: "Refunded", paid_on: "2026-09-01", refund: { amount: "45000.00", refunded_on: "2026-09-30", reason: "Visa refused" }, receipt: null,
      can_upload: false,
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

// ccrm-048 (DEC-SCOPE-322): the deposit receipt is uploaded from the deposit card.
describe("deposit receipt upload on the finance tab (ccrm-048)", () => {
  const writable = (over: Partial<StudentDeposit> = {}): StudentFinance => ({ ...empty, deposits: [{ ...finance.deposits[0], receipt: null, can_upload: true, ...over }] });
  const pdf = () => new File(["%PDF-1.4"], "deposit.pdf", { type: "application/pdf" });
  const json = (body: unknown, status = 201) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

  it("offers no upload where the reader may not upload (agency, not required, another counselor's)", () => {
    render(<OverseasStudentFinance finance={finance} />);
    expect(screen.queryByLabelText(/receipt file/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload receipt|replace receipt/i })).not.toBeInTheDocument();
  });

  it("no longer calls the whole tab read-only", () => {
    render(<OverseasStudentFinance finance={empty} />);
    expect(screen.queryByText(/^Read-only\./)).not.toBeInTheDocument();
    expect(screen.getByText(/a deposit's receipt can be uploaded here/)).toBeInTheDocument();
  });

  it("uploads a receipt for a deposit without one, then refreshes", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => json({ record: {} }));
    vi.stubGlobal("fetch", fetchMock);
    render(<OverseasStudentFinance finance={writable({ application_id: "a 1" })} />);
    const button = screen.getByRole("button", { name: "Upload receipt for Alpha Uni" });
    fireEvent.change(screen.getByLabelText("Deposit receipt file for Alpha Uni"), { target: { files: [pdf()] } });
    fireEvent.click(button);
    expect(await screen.findByText("Receipt uploaded. The student can see it in their Documents.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/workflows/overseas/applications/a%201/deposit/receipt");
    expect(init?.method).toBe("POST");
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
    expect(refresh).toHaveBeenCalled();
  });

  it("says Replace when a receipt is already attached", () => {
    render(<OverseasStudentFinance finance={writable({ receipt: { id: "d1", name: "Deposit receipt", can_download: true } })} />);
    expect(screen.getByRole("button", { name: "Replace receipt for Alpha Uni" })).toBeInTheDocument();
  });

  it("asks for a file before sending anything", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<OverseasStudentFinance finance={writable()} />);
    fireEvent.click(screen.getByRole("button", { name: "Upload receipt for Alpha Uni" }));
    expect(await screen.findByText("Choose a PDF, JPEG or PNG file first.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server's refusal and does not refresh", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ detail: "Record a required deposit on the application first" }, 422)));
    render(<OverseasStudentFinance finance={writable()} />);
    fireEvent.change(screen.getByLabelText("Deposit receipt file for Alpha Uni"), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload receipt for Alpha Uni" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Record a required deposit on the application first");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("sends one request for a double click", async () => {
    let finish: (value: Response) => void = () => {};
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => (finish = resolve)));
    vi.stubGlobal("fetch", fetchMock);
    render(<OverseasStudentFinance finance={writable()} />);
    fireEvent.change(screen.getByLabelText("Deposit receipt file for Alpha Uni"), { target: { files: [pdf()] } });
    const button = screen.getByRole("button", { name: "Upload receipt for Alpha Uni" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    finish(new Response(JSON.stringify({ record: {} }), { status: 201 }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });
});
