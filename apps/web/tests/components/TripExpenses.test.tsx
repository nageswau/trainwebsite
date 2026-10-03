import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TripExpenses from "@/components/TripExpenses";

import { json, trip } from "./tripFixtures";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const line = { id: "e1", category: "food" as const, amount: "450.50", expense_date: "2026-10-10", note: "Lunch" };

beforeEach(() => {
  refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TripExpenses (bdm-010)", () => {
  it("shows the empty state and no add button before approval", () => {
    render(<TripExpenses trip={trip()} />);
    expect(screen.getByText("No expenses yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add expense" })).toBeNull();
    expect(screen.getByText("Expenses can be added once the trip is approved.")).toBeInTheDocument();
  });

  it("summarises estimated, actual and the difference", () => {
    render(<TripExpenses trip={trip({ estimated_cost: "2500.00", actual_cost: "2650.50", expenses: [line] })} />);
    const summary = screen.getByRole("group", { name: "Costs" });
    expect(within(summary).getByText("₹2,500.00")).toBeInTheDocument();
    expect(within(summary).getByText("₹2,650.50")).toBeInTheDocument();
    expect(within(summary).getByText("₹150.50 over the estimate")).toBeInTheDocument();
  });

  it("adds a line and refreshes", async () => {
    const mock = vi.fn().mockResolvedValue(json({ id: "t1" }, 201));
    vi.stubGlobal("fetch", mock);
    render(<TripExpenses trip={trip({ can_add_expense: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Add expense" }));
    expect(screen.getByLabelText("Category")).toHaveFocus();
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "stay" } });
    fireEvent.change(screen.getByLabelText("Amount (₹)"), { target: { value: "1200" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-10-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save expense" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = mock.mock.calls[0];
    expect([url, init.method, JSON.parse(init.body)]).toEqual([
      "/api/v1/bdm/trips/t1/expenses", "POST", { category: "stay", amount: "1200", expense_date: "2026-10-10", note: null },
    ]);
  });

  it("refuses a zero amount before sending", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    render(<TripExpenses trip={trip({ can_add_expense: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Add expense" }));
    fireEvent.change(screen.getByLabelText("Amount (₹)"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-10-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save expense" }));
    expect(mock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Amount (₹)")).toHaveAttribute("aria-invalid", "true");
  });

  it("deletes only after an inline confirm", async () => {
    const mock = vi.fn().mockResolvedValue(json({ id: "t1" }));
    vi.stubGlobal("fetch", mock);
    render(<TripExpenses trip={trip({ can_add_expense: true, expenses: [line] })} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete Food expense of ₹450.50" }));
    expect(mock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Delete expense" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect([mock.mock.calls[0][0], mock.mock.calls[0][1].method]).toEqual(["/api/v1/bdm/trips/t1/expenses/e1", "DELETE"]);
  });
});
