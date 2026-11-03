import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FeeAccountSummary from "@/components/FeeAccountSummary";

// itc-018 (DEC-SCOPE-353): each fee account card names the next amount due and its date (the oldest owed bill), "Nothing due" once
// the fee is paid, and nothing at all for an unbilled enrolment. An account without the field (an older API) renders as before.
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const BASE = {
  enrollment_id: "e1", enrollment_code: "ENR-1", course: "Full Stack Java", batch: "FSJ-Nov", currency: "INR",
  course_fee: 45000, discount_approved: 0, tax: 0, total_payable: 45000, paid_confirmed: 20000, credits: 0, balance: 25000, state: "partially_paid",
};

function serve(accounts: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => json(accounts)));
}

async function card(course = "Full Stack Java") {
  render(<FeeAccountSummary />);
  return screen.findByLabelText(`Fee account for ${course}`);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Fee summary next due (itc-018)", () => {
  it("shows the balance and the next amount due with its date", async () => {
    serve([{ ...BASE, next_due: { amount: 25000, due_date: "2026-12-10" } }]);
    const found = await card();
    expect(within(found).getByText("Balance").nextElementSibling).toHaveTextContent("INR 25,000.00");
    expect(within(found).getByText("Next due").nextElementSibling).toHaveTextContent("INR 25,000.00 · 10 Dec 2026");
  });

  it("says when an owed amount has no due date yet", async () => {
    serve([{ ...BASE, next_due: { amount: 8000, due_date: null } }]);
    const found = await card();
    expect(within(found).getByText("Next due").nextElementSibling).toHaveTextContent("INR 8,000.00 · no due date set");
  });

  it("says nothing is due on a fully paid fee", async () => {
    serve([{ ...BASE, paid_confirmed: 45000, balance: 0, state: "fully_paid", next_due: null }]);
    const found = await card();
    expect(within(found).getByText("Next due").nextElementSibling).toHaveTextContent("Nothing due");
  });

  it("shows no next due on an unbilled (scholarship) enrolment", async () => {
    serve([{ ...BASE, course_fee: 0, total_payable: 0, paid_confirmed: 0, balance: 0, state: "not_billed", next_due: null }]);
    const found = await card();
    expect(within(found).getByText("No fee has been billed for this enrolment yet.")).toBeInTheDocument();
    expect(within(found).queryByText("Next due")).toBeNull();
  });

  it("renders an account without next_due as before", async () => {
    serve([BASE]);
    const found = await card();
    expect(within(found).getByText("Balance")).toBeInTheDocument();
    expect(within(found).queryByText("Next due")).toBeNull();
  });
});
