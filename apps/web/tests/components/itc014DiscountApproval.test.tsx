import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DiscountApprovalQueue from "@/components/DiscountApprovalQueue";
import FeeDiscountRequests from "@/components/FeeDiscountRequests";
import { DISCOUNT_QUEUE_URL, type DiscountRequest } from "@/lib/feeDiscounts";

// itc-014 (DEC-SCOPE-363): a counselor or accounts user asks for a discount on the student record; an approver who is not the requester
// approves or rejects it from the IT Admin Payments page. A pending request changes nothing (AC1); self-approval is refused (AC3).
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const REQUEST: DiscountRequest = {
  id: "r1", enrollment_id: "e1", enrollment_code: "ENR-1", student: { id: "s1", full_name: "Asha Rao" }, course: "Full Stack Java",
  amount: 5000, reason: "Sibling discount", status: "pending", requested_by: { id: "c1", full_name: "Kiran Counselor" },
  created_at: "2026-11-03T05:00:00Z", decided_by: null, decided_at: null, decision_note: null, own: false,
};
const REQUESTS_URL = "/api/v1/it/enrollments/e1/discount-requests";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Requesting a discount (itc-014)", () => {
  it("shows an empty history and sends a request, then lists it as waiting for approval", async () => {
    let created = false;
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        created = true;
        return json({ ...REQUEST, own: true }, 201);
      }
      return json(created ? [{ ...REQUEST, own: true }] : []);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<FeeDiscountRequests enrollmentId="e1" balance={45000} currency="INR" />);
    expect(await screen.findByText("No discount has been requested yet.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Discount amount (INR)"), { target: { value: "5000" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Sibling discount" } });
    fireEvent.click(screen.getByRole("button", { name: "Request discount" }));
    expect(await screen.findByText(/Discount requested\. It changes the fee only once an approver approves it\./)).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(post[0]).toBe(REQUESTS_URL);
    expect(JSON.parse(String(post[1]!.body))).toEqual({ amount: 5000, reason: "Sibling discount" });
    const list = await screen.findByRole("list", { name: "Discount requests" });
    expect(within(list).getByText("Waiting for approval")).toHaveClass("status", "pending");
    expect(list).toHaveTextContent("INR 5,000.00 · Sibling discount");
    expect(screen.queryByRole("button", { name: "Request discount" })).toBeNull(); // one pending request at a time
  });

  it("validates the amount against the balance before sending", async () => {
    const fetchMock = vi.fn(async () => json([]));
    vi.stubGlobal("fetch", fetchMock);
    render(<FeeDiscountRequests enrollmentId="e1" balance={1000} currency="INR" />);
    await screen.findByText("No discount has been requested yet.");
    fireEvent.change(screen.getByLabelText("Discount amount (INR)"), { target: { value: "1500" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Too much" } });
    fireEvent.click(screen.getByRole("button", { name: "Request discount" }));
    expect(await screen.findByText("Enter an amount above 0 and no more than INR 1,000.00, the balance still owed.")).toHaveAttribute("role", "alert");
    expect(fetchMock).toHaveBeenCalledTimes(1); // the history load only
  });

  it("offers no form when nothing is owed, and shows a load error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json([{ ...REQUEST, status: "approved", decided_by: { id: "a1", full_name: "Admin" }, decision_note: "OK" }])));
    render(<FeeDiscountRequests enrollmentId="e1" balance={0} currency="INR" />);
    expect(await screen.findByText("Approved")).toHaveClass("status");
    expect(screen.getByRole("list", { name: "Discount requests" })).toHaveTextContent("Decided by Admin: OK");
    expect(screen.queryByRole("button", { name: "Request discount" })).toBeNull();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "x" }, 500)));
    render(<FeeDiscountRequests enrollmentId="e1" balance={10} currency="INR" />);
    expect(await screen.findByText("Discount requests could not be loaded. Refresh the page to try again.")).toBeInTheDocument();
  });
});

describe("Discount approval queue (itc-014)", () => {
  it("approves a request and removes it from the queue", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
      init?.method === "POST" ? json({ request: { ...REQUEST, status: "approved" }, account: {} }) : json(url === DISCOUNT_QUEUE_URL ? [REQUEST] : []),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<DiscountApprovalQueue />);
    const item = await screen.findByRole("listitem");
    expect(item).toHaveTextContent("Asha Rao · ENR-1 · Full Stack Java");
    expect(item).toHaveTextContent("INR 5,000.00 off · Sibling discount · asked by Kiran Counselor");
    fireEvent.click(within(item).getByRole("button", { name: "Approve discount for Asha Rao" }));
    expect(await screen.findByText("Discount approved for Asha Rao. The fee balance is updated.")).toHaveAttribute("role", "status");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/it/discount-requests/r1/approve", expect.objectContaining({ method: "POST" }));
    expect(screen.getByText("No discount requests are waiting for approval.")).toBeInTheDocument();
  });

  it("needs a note to reject, and never offers a decision on the caller's own request", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === "POST" ? json({ request: { ...REQUEST, status: "rejected" } }) : json([REQUEST, { ...REQUEST, id: "r2", own: true, student: { id: "s2", full_name: "Ravi K" } }]),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<DiscountApprovalQueue />);
    const [theirs, mine] = await screen.findAllByRole("listitem");
    expect(within(mine).queryByRole("button")).toBeNull();
    expect(mine).toHaveTextContent("Your request — another approver must decide it.");
    fireEvent.click(within(theirs).getByRole("button", { name: "Reject discount for Asha Rao" }));
    expect(await within(theirs).findByText("Give a reason for rejecting.")).toHaveAttribute("role", "alert");
    fireEvent.change(within(theirs).getByLabelText("Note for Asha Rao"), { target: { value: "Not eligible" } });
    fireEvent.click(within(theirs).getByRole("button", { name: "Reject discount for Asha Rao" }));
    await waitFor(() => expect(screen.getByText("Discount rejected for Asha Rao.")).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({ note: "Not eligible" });
  });

  it("shows the server's refusal and keeps the request", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === "POST" ? json({ detail: "Only INR 25,000.00 is still owed now. Reject this request, or ask for a new one." }, 409) : json([REQUEST]),
    ));
    render(<DiscountApprovalQueue />);
    fireEvent.click(await screen.findByRole("button", { name: "Approve discount for Asha Rao" }));
    expect(await screen.findByText("Only INR 25,000.00 is still owed now. Reject this request, or ask for a new one.")).toHaveAttribute("role", "alert");
    expect(screen.getByRole("listitem")).toBeInTheDocument();
  });
});
