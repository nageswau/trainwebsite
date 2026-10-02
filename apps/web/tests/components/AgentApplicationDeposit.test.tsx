import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationDetail from "@/components/AgentApplicationDetail";

// AGN-011 (DEC-SCOPE-057): the application's deposit -- record it, pay it through Razorpay Checkout (stubbed here), download the receipt,
// and say plainly when online payment is unavailable (AC6).
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const DEPOSIT = {
  id: "dep1", required: true, amount: "50000.00", currency: "INR", due_date: "2026-12-01", status: "pending", paid_at: null, paid_by: null,
  receipt_available: false, remitted_at: null, remittance_reference: null, refunded_at: null, refund_amount: null, refund_reason: null,
  checkout_in_progress: false,
};
const detail = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", university_id: "u1", university_slug: "u1",
  course: null, course_id: null, intake: "Fall 2027", status: "university_selection", application_reference: null, submitted_on: null,
  application_deadline: null, offer_deadline: null, nearest_deadline: null, next_action: null, updated_at: "", created_at: "", read_only_reason: null,
  history: [], offer: null, offer_letters: [], deposit: null, payment_available: true,
  ...over,
});

type Handler = (url: string, init?: RequestInit) => Response | undefined;
function serve(first: Record<string, unknown>, handler: Handler = () => undefined) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(url, init) ?? json({ application: detail(first) })));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
const mount = () => render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
const region = async () => screen.findByRole("region", { name: "Deposit" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentApplicationDeposit (AGN-011)", () => {
  it("shows the empty state and records a deposit", async () => {
    const fetchMock = serve({}, (url, init) =>
      init?.method === "PUT" ? json({ application: detail({ deposit: { ...DEPOSIT, due_date: null } }) }) : undefined,
    );
    mount();
    const deposit = await region();
    expect(within(deposit).getByText("No deposit recorded yet.")).toBeTruthy();
    fireEvent.click(within(deposit).getByRole("button", { name: "Record deposit" }));
    const form = screen.getByRole("form", { name: "Record deposit" });
    fireEvent.click(within(form).getByLabelText("Yes"));
    fireEvent.change(within(form).getByLabelText(/Amount/), { target: { value: "50000" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save deposit" }));
    await waitFor(() => expect(screen.getByText("Deposit saved.")).toBeTruthy());
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(put[0]).toBe("/api/v1/workflows/overseas/agent/crm/applications/a1/deposit");
    expect(JSON.parse(String(put[1]!.body))).toEqual({ required: true, amount: "50000", due_date: null });
    expect(within(await region()).getByText("₹50,000.00")).toBeTruthy();
  });

  it("puts a 422 on the amount field and keeps the entry", async () => {
    serve({}, (_url, init) =>
      init?.method === "PUT" ? json({ detail: [{ loc: ["body", "amount"], msg: "Input should be greater than 0" }] }, 422) : undefined,
    );
    mount();
    fireEvent.click(within(await region()).getByRole("button", { name: "Record deposit" }));
    const form = screen.getByRole("form", { name: "Record deposit" });
    fireEvent.click(within(form).getByLabelText("Yes"));
    fireEvent.change(within(form).getByLabelText(/Amount/), { target: { value: "0" } }); // passes the input's pattern; the server refuses it
    fireEvent.click(within(form).getByRole("button", { name: "Save deposit" }));
    const amount = await within(form).findByLabelText(/Amount/);
    await waitFor(() => expect(amount.getAttribute("aria-invalid")).toBe("true"));
    expect(within(form).getByText("Input should be greater than 0")).toBeTruthy();
    expect((amount as HTMLInputElement).value).toBe("0");
  });

  it("Escape cancels the form and returns to the button", async () => {
    serve({});
    mount();
    fireEvent.click(within(await region()).getByRole("button", { name: "Record deposit" }));
    fireEvent.keyDown(screen.getByRole("form", { name: "Record deposit" }), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("form", { name: "Record deposit" })).toBeNull());
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Record deposit"));
  });

  it("shows the pending deposit with Pay deposit", async () => {
    serve({ deposit: DEPOSIT });
    mount();
    const deposit = await region();
    expect(within(deposit).getByText("₹50,000.00")).toBeTruthy();
    expect(within(deposit).getByText("2026-12-01")).toBeTruthy();
    expect(within(deposit).getByRole("button", { name: "Pay deposit" })).toBeTruthy();
  });

  it("says payment is unavailable when Razorpay is not configured, with no Pay button", async () => {
    serve({ deposit: DEPOSIT, payment_available: false });
    mount();
    const deposit = await region();
    expect(within(deposit).getByText("Online payment is unavailable right now. Nothing has been charged.")).toBeTruthy();
    expect(within(deposit).queryByRole("button", { name: "Pay deposit" })).toBeNull();
  });

  it("sends a UUID Idempotency-Key and shows unavailable on configuration_required", async () => {
    const fetchMock = serve({ deposit: DEPOSIT }, (url, init) => (init?.method === "POST" && url.endsWith("/deposit/checkout") ? json({ status: "configuration_required" }) : undefined));
    mount();
    fireEvent.click(within(await region()).getByRole("button", { name: "Pay deposit" }));
    expect(await screen.findByText("Online payment is unavailable right now. Nothing has been charged.")).toBeTruthy();
    const post = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/deposit/checkout") && init?.method === "POST")!;
    expect((post[1]!.headers as Record<string, string>)["Idempotency-Key"]).toMatch(UUID_V4);
  });

  it("opens Razorpay Checkout and reports a closed window", async () => {
    let options: Record<string, unknown> = {};
    vi.stubGlobal(
      "Razorpay",
      class {
        constructor(o: Record<string, unknown>) {
          options = o;
        }
        open() {}
      },
    );
    serve({ deposit: DEPOSIT }, (url, init) =>
      init?.method === "POST" && url.endsWith("/deposit/checkout")
        ? json({ status: "ready", payment_id: "p1", key_id: "rzp_test_x", provider_order_id: "order_1", amount: 50000, currency: "INR" })
        : undefined,
    );
    mount();
    fireEvent.click(within(await region()).getByRole("button", { name: "Pay deposit" }));
    await waitFor(() => expect(options.order_id).toBe("order_1"));
    expect(options.amount).toBe(5000000);
    (options.modal as { ondismiss: () => void }).ondismiss();
    expect(await screen.findByText("Payment not completed. You can try again.")).toBeTruthy();
  });

  it("verifies a completed payment and reloads to the paid deposit", async () => {
    let options: Record<string, unknown> = {};
    vi.stubGlobal(
      "Razorpay",
      class {
        constructor(o: Record<string, unknown>) {
          options = o;
        }
        open() {}
      },
    );
    let paid = false;
    const fetchMock = serve({ deposit: DEPOSIT }, (url, init) => {
      if (init?.method === "POST" && url.endsWith("/deposit/checkout"))
        return json({ status: "ready", payment_id: "p1", key_id: "rzp_test_x", provider_order_id: "order_1", amount: 50000, currency: "INR" });
      if (init?.method === "POST" && url.endsWith("/payments/p1/verify")) return (paid = true), json({ id: "p1", status: "paid" });
      if (paid) return json({ application: detail({ deposit: { ...DEPOSIT, status: "paid", paid_at: "2026-10-02T10:00:00Z", paid_by: "Apps Staff", receipt_available: true } }) });
      return undefined;
    });
    mount();
    fireEvent.click(within(await region()).getByRole("button", { name: "Pay deposit" }));
    await waitFor(() => expect(options.handler).toBeTruthy());
    (options.handler as (r: unknown) => void)({ razorpay_payment_id: "pay_1", razorpay_order_id: "order_1", razorpay_signature: "sig" });
    expect(await screen.findByRole("button", { name: "Download receipt" })).toBeTruthy();
    expect(within(await region()).getByText("Apps Staff")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/payments/p1/verify")).toBe(true);
  });

  it("a 409 on checkout reloads the detail with the server's words", async () => {
    serve({ deposit: DEPOSIT }, (url, init) => (init?.method === "POST" && url.endsWith("/deposit/checkout") ? json({ detail: "This deposit is already paid" }, 409) : undefined));
    mount();
    fireEvent.click(within(await region()).getByRole("button", { name: "Pay deposit" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This deposit is already paid");
  });

  it("a paid deposit shows the payer and the receipt, and cannot be paid or edited", async () => {
    serve({ deposit: { ...DEPOSIT, status: "paid", paid_at: "2026-10-02T10:00:00Z", paid_by: "Apps Staff", receipt_available: true } });
    mount();
    const deposit = await region();
    expect(within(deposit).getByText("Apps Staff")).toBeTruthy();
    expect(within(deposit).getByRole("button", { name: "Download receipt" })).toBeTruthy();
    expect(within(deposit).queryByRole("button", { name: "Pay deposit" })).toBeNull();
    expect(within(deposit).queryByRole("button", { name: "Edit deposit" })).toBeNull();
  });

  it("a read-only application offers no deposit actions", async () => {
    serve({ deposit: DEPOSIT, read_only_reason: "withdrawn", status: "withdrawn" });
    mount();
    const deposit = await region();
    expect(within(deposit).queryByRole("button", { name: "Pay deposit" })).toBeNull();
    expect(within(deposit).queryByRole("button", { name: "Edit deposit" })).toBeNull();
  });
});
