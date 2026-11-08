import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterVendorCommercials from "@/components/RecruiterVendorCommercials";

const person = { id: "u", full_name: "Asha Rao", active: true };
const totals = (outstanding: string) => ({ billed: outstanding, paid: "0.00", outstanding, last_paid_on: null });
const bill = {
  id: "b1", kind: "payable", kind_label: "We owe the vendor", bill_number: "VB-1", bill_date: "2026-11-01", due_date: "2026-11-05", amount: "10000.00",
  milestone: "On joining", note: null, paid: "0.00", outstanding: "10000.00", payment_status: "unpaid", payment_status_label: "Unpaid", overdue: true,
  cancelled_at: null, cancel_reason: null, requirement: null, created_by: person, payments: [], permissions: { can_pay: true, can_cancel: true }, created_at: "2026-11-01T05:00:00Z",
};

function respond(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })));
}

// pob-012 (DEC-SCOPE-433 W9)
describe("pob-012 vendor commercials section", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("lists bills with status as text and offers the actions the server allows", async () => {
    respond(200, { items: [bill], totals: { payable: totals("10000.00"), receivable: totals("0.00") }, can_edit: true });
    render(<RecruiterVendorCommercials companyId="c1" />);
    expect(await screen.findByText("VB-1")).toBeTruthy();
    expect(screen.getByText("Overdue")).toBeTruthy();
    expect(screen.getByText("Unpaid")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Record payment for VB-1" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Record bill" }));
    expect(screen.getByRole("form", { name: "Record bill" })).toBeTruthy();
  });

  it("hides the writes from a reader and shows the empty state", async () => {
    respond(200, { items: [], totals: { payable: totals("0.00"), receivable: totals("0.00") }, can_edit: false });
    render(<RecruiterVendorCommercials companyId="c1" />);
    expect(await screen.findByText("No bills yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Record bill" })).toBeNull();
  });

  it("offers a retry when the read fails", async () => {
    respond(500, { detail: "boom" });
    render(<RecruiterVendorCommercials companyId="c1" />);
    expect(await screen.findByText("Unable to load vendor bills.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
