import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FeeAccountCard, type FeeAccount } from "@/components/FeeAccountSummary";
import FeePaymentPanel from "@/components/FeePaymentPanel";
import WorkflowPanel from "@/components/WorkflowPanel";
import { clearPermissions } from "@/lib/usePermissions";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams(), usePathname: () => "/it/admin/payments",
}));

// itc-015 (DEC-SCOPE-363): the fee account shows what was refunded and lists its credit notes, write-offs, refunds and corrections, each
// with its document; the IT admin's Payments page records adjustments and corrects a mistyped payment (`payments.refund`).
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ACCOUNT: FeeAccount = {
  enrollment_id: "e1", enrollment_code: "ENR-1", course: "Full Stack Java", batch: "FSJ-Nov", currency: "INR",
  course_fee: 45000, discount_approved: 0, tax: 0, total_payable: 45000, paid_confirmed: 45000, credits: 5000, refunded: 5000, balance: 0, state: "fully_paid",
  adjustments: [
    { id: "a1", kind: "credit_note", amount: 5000, reason: "Moved to the weekend batch", payment_mode: null, reference: null, document_no: "CN-2026-AB12", created_at: "2026-11-03T05:00:00Z" },
    { id: "a2", kind: "refund", amount: 5000, reason: "Moved to the weekend batch", payment_mode: "bank_transfer", reference: "NEFT-77", document_no: "RF-2026-CD34", created_at: "2026-11-03T06:00:00Z" },
    { id: "a3", kind: "reversal", amount: 2000, reason: "Typed the wrong amount", payment_mode: null, reference: null, document_no: null, created_at: "2026-11-03T07:00:00Z" },
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Fee account adjustments (itc-015)", () => {
  it("shows the refunded figure and every adjustment with its reason, mode and reference", () => {
    render(<FeeAccountCard account={ACCOUNT} />);
    const card = screen.getByLabelText("Fee account for Full Stack Java");
    expect(within(card).getByText("Refunded").nextElementSibling).toHaveTextContent("INR 5,000.00");
    const list = within(card).getByRole("list", { name: "Credits and refunds" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Credit note · INR 5,000.00");
    expect(items[0]).toHaveTextContent("Moved to the weekend batch");
    expect(items[1]).toHaveTextContent("Refund · INR 5,000.00");
    expect(items[1]).toHaveTextContent("Bank transfer · Ref NEFT-77");
    expect(items[2]).toHaveTextContent("Payment corrected · INR 2,000.00");
    expect(within(items[2]).queryByRole("button")).toBeNull(); // a correction has no document of its own
  });

  it("downloads an adjustment's document through a signed link", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const fetchMock = vi.fn(async () => json({ url: "https://files.example/RF.pdf" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<FeeAccountCard account={ACCOUNT} />);
    fireEvent.click(screen.getByRole("button", { name: "Download refund receipt RF-2026-CD34" }));
    await vi.waitFor(() => expect(open).toHaveBeenCalledWith("https://files.example/RF.pdf", "_blank", "noreferrer"));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/it/fee-adjustments/a2/document");
  });

  it("explains a failed download", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "Adjustment not found" }, 404)));
    render(<FeeAccountCard account={ACCOUNT} />);
    fireEvent.click(screen.getByRole("button", { name: "Download credit note CN-2026-AB12" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Adjustment not found");
  });

  it("renders an older account without adjustments as before", () => {
    render(<FeeAccountCard account={{ ...ACCOUNT, adjustments: undefined, refunded: undefined }} />);
    expect(screen.queryByText("Refunded")).toBeNull();
    expect(screen.queryByRole("list", { name: "Credits and refunds" })).toBeNull();
  });

  it("explains a corrected payment on the student's payment list instead of calling it paid (QA15-02)", async () => {
    const reversed = { id: "p9", amount: 32500, currency: "INR", provider: "manual", status: "reversed", due_date: null, reference_type: "enrollment_fee", is_manual: true,
      emi_schedule_id: null, installment_no: null, paid_at: "2026-11-03T05:00:00Z", payment_mode: "cash", provider_reference: "TYPO-1" };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url === "/api/v1/payments/mine" ? json([reversed]) : url === "/api/v1/payments/mode" ? json({ mode: "test" }) : json([]))));
    render(<FeePaymentPanel />);
    expect(await screen.findByText("Corrected — replaced by a new payment with its own receipt")).toBeInTheDocument();
    expect(screen.queryByText(/^Paid on/)).toBeNull();
  });

  it("gives the IT admin with payments.refund the adjustment and correction forms", async () => {
    clearPermissions();
    vi.stubGlobal("fetch", vi.fn(async () => json({ role: "it_admin", permissions: ["payments.view", "payments.add", "payments.refund"] })));
    const admin = { id: "u1", email: "a@example.local", full_name: "Ira", role: "it_admin", division: "it" } as unknown as User;
    render(<WorkflowPanel user={admin} section="payments" />);
    expect(await screen.findByRole("heading", { name: "Record fee adjustment" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Correct a recorded payment" })).toBeInTheDocument();
    const kind = screen.getByLabelText("Adjustment type");
    expect(within(kind).getByRole("option", { name: "Refund" })).toBeInTheDocument();
    expect(within(kind).queryByRole("option", { name: /reversal/i })).toBeNull();
  });

  it("hides both forms without payments.refund", async () => {
    clearPermissions();
    vi.stubGlobal("fetch", vi.fn(async () => json({ role: "it_admin", permissions: ["payments.view", "payments.add"] })));
    const admin = { id: "u1", email: "a@example.local", full_name: "Ira", role: "it_admin", division: "it" } as unknown as User;
    render(<WorkflowPanel user={admin} section="payments" />);
    expect(await screen.findByRole("heading", { name: "Record enrolment payment" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Record fee adjustment" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Correct a recorded payment" })).toBeNull();
  });
});
