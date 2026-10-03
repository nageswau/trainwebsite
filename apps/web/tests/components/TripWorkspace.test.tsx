import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TripWorkspace from "@/components/TripWorkspace";

import { json, trip } from "./tripFixtures";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

beforeEach(() => {
  refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const owner = (over = {}) => render(<TripWorkspace initialTrip={trip(over)} view="owner" today="2026-10-03" backHref="/bdm/travel" backLabel="Back to my trips" />);

describe("TripWorkspace (bdm-010 QA10-16)", () => {
  it("the owner sees actions, details, the editor while editable, costs and remarks", () => {
    owner({ can_edit: true, can_submit: true, approval_status: "rejected", rejection_reason: "Too costly" });
    expect(screen.getByRole("heading", { level: 2, name: "Hyderabad → Vijayawada" })).toHaveStyle({ overflowWrap: "anywhere" }); // review M4
    expect(screen.getByText("Too costly")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit for approval" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Edit trip" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Costs" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Remarks" })).toBeInTheDocument();
  });

  it("a save's returned trip updates the whole page without a server refresh", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(trip({ approval_status: "submitted", can_withdraw: true }))));
    owner({ can_submit: true, can_edit: true });
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByText("Approval: Submitted")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Withdraw" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Edit trip" })).toBeNull();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("two quick expense saves end with the second response, whatever order the page saw them", async () => {
    const first = trip({ can_add_expense: true, approval_status: "approved", actual_cost: "450.50",
      expenses: [{ id: "e1", category: "food", amount: "450.50", expense_date: "2026-10-03", note: null }] });
    const second = { ...first, actual_cost: "1650.50", expenses: [...first.expenses, { id: "e2", category: "stay" as const, amount: "1200.00", expense_date: "2026-10-03", note: null }] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(first, 201)).mockResolvedValueOnce(json(second, 201)));
    owner({ can_add_expense: true, approval_status: "approved" });
    for (const amount of ["450.50", "1200"]) {
      fireEvent.click(screen.getByRole("button", { name: "Add expense" }));
      fireEvent.change(screen.getByLabelText("Amount (₹)"), { target: { value: amount } });
      fireEvent.click(screen.getByRole("button", { name: "Save expense" }));
      await screen.findByRole("button", { name: "Add expense" });
    }
    expect(within(screen.getByRole("group", { name: "Costs" })).getByText("₹1,650.50")).toBeInTheDocument();
  });

  it("a 409 re-reads the trip so the page shows what changed", async () => {
    const mock = vi.fn()
      .mockResolvedValueOnce(json({ detail: "This trip is already approved and can't be withdrawn" }, 409))
      .mockResolvedValueOnce(json(trip({ approval_status: "approved", can_start: true })));
    vi.stubGlobal("fetch", mock);
    owner({ approval_status: "submitted", can_withdraw: true });
    fireEvent.click(screen.getByRole("button", { name: "Withdraw" }));
    expect(await screen.findByText("Approval: Approved")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe("/api/v1/bdm/trips/t1");
    expect(screen.getByRole("alert")).toHaveTextContent("already approved");
  });

  it("the manager view is read-only, with the decision panel and the reason it can't decide", () => {
    render(<TripWorkspace initialTrip={trip({ approval_status: "submitted", remarks: "Hotel near campus" })} view="manager" today="2026-10-03"
      backHref="/admin/bdm-travel-approvals" backLabel="Back to approvals" note="The reporting manager decides this trip." />);
    expect(screen.queryByRole("form", { name: "Edit trip" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Remarks" })).toBeNull();
    expect(screen.getByText("Hotel near campus")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("The reporting manager decides this trip.");
    expect(screen.queryByText("Expenses can be added once the trip is approved.")).toBeNull();
  });
});
