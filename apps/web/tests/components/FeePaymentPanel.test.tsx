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
