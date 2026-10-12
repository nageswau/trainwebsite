import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AccountsDashboard from "@/components/AccountsDashboard";
import BalancesForm from "@/components/BalancesForm";
import type { AccountsMonth } from "@/lib/accounts";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const heads = (keys: [string, string, string][]) => keys.map(([key, label, amount]) => ({ key, label, amount, parts: amount === "0.00" ? [] : [{ label, amount }] }));
const data = (over: Partial<AccountsMonth> = {}): AccountsMonth => ({
  month: "2026-09", current_month: "2026-10", as_of: "2026-10-12",
  income: {
    heads: heads([["abroad", "Abroad education", "500000.00"], ["it", "IT training", "300000.00"], ["recruitment", "Recruitment", "0.00"], ["school", "School projects", "0.00"], ["other", "Other", "0.00"]]),
    total: "800000.00",
  },
  expenses: {
    heads: [
      ...heads([["salaries", "Salaries", "220000.00"], ["rent", "Rent", "60000.00"], ["marketing", "Marketing", "0.00"], ["travel", "Travel", "0.00"], ["trainers", "Trainers", "0.00"], ["commissions", "Commissions", "0.00"], ["operations", "Operations", "0.00"]]),
      { key: "technology", label: "Technology", amount: "6500.00", parts: [{ label: "Internet", amount: "1500.00" }, { label: "Software", amount: "5000.00" }] },
    ],
    total: "286500.00",
  },
  profit: "513500.00",
  not_counted: [{ currency: "USD", kind: "income", amount: "300.00", count: 1 }],
  receivables: { total: "118500.00", overdue: "43500.00", fees: "13500.00", recruitment: "60000.00", university: "45000.00", not_counted: [] },
  pending_invoices: { count: 2, amount: "24000.00" },
  balances: { cash_bank: "-2500.50", payables: "18000.00", tax_liabilities: null, updated_at: "2026-10-01T10:00:00Z", updated_by: { id: "u", full_name: "Asha Accountant" } },
  ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("AccountsDashboard (mgmt-013 §22)", () => {
  it("lists the five income heads and the eight expense heads with their totals", () => {
    render(<AccountsDashboard data={data()} />);
    const income = screen.getByRole("table", { name: "Income by head, September 2026" });
    expect(within(income).getAllByRole("row").map((r) => r.querySelector("th")?.textContent)).toEqual(
      ["Head", "Abroad education", "IT training", "Recruitment", "School projects", "Other", "Total income"],
    );
    expect(within(income).getByText("₹8,00,000.00")).toBeTruthy();
    const expenses = screen.getByRole("table", { name: "Expenses by head, September 2026" });
    expect(within(expenses).getAllByRole("row")).toHaveLength(10);
    expect(within(expenses).getByText("Internet ₹1,500.00 · Software ₹5,000.00")).toBeTruthy(); // the mapping is visible
  });

  it("shows the six position figures, the overdue part and 'Not entered' for a figure never typed", () => {
    render(<AccountsDashboard data={data()} />);
    const position = screen.getByRole("list", { name: "Financial position" }).textContent ?? "";
    for (const text of ["Receivables", "₹1,18,500.00", "₹43,500.00 overdue", "Payables", "₹18,000.00", "Cash/bank", "-₹2,500.50", "Profit", "₹5,13,500.00",
      "Tax liabilities", "Not entered", "Pending invoices", "2 · ₹24,000.00"]) {
      expect(position).toContain(text);
    }
    const parts = screen.getByRole("list", { name: "Receivables by source" }).textContent ?? "";
    expect(parts).toContain("Student fees₹13,500.00");
    expect(parts).toContain("University commission₹45,000.00");
  });

  it("says which money is not converted", () => {
    render(<AccountsDashboard data={data()} />);
    expect(screen.getByText(/USD 300\.00 income \(1 line\)/)).toBeTruthy();
  });
});

describe("BalancesForm (mgmt-013 AD8)", () => {
  it("starts from the saved figures, saves blanks as null and refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(data()));
    vi.stubGlobal("fetch", fetchMock);
    render(<BalancesForm data={data()} />);
    expect((screen.getByLabelText("Cash/bank (₹)") as HTMLInputElement).value).toBe("-2500.50");
    expect((screen.getByLabelText("Tax liabilities (₹)") as HTMLInputElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("Payables (₹)"), { target: { value: "20000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save September 2026 balances" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/management/accounts/balances?month=2026-09");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ cash_bank: "-2500.50", payables: "20000", tax_liabilities: null });
    expect(screen.getByRole("status").textContent).toBe("Balances for September 2026 saved.");
  });

  it("puts a 422 on its field and keeps what was typed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: [{ loc: ["body", "payables"], msg: "An amount can't be negative", type: "salary_money" }] }, 422)));
    render(<BalancesForm data={data()} />);
    fireEvent.change(screen.getByLabelText("Payables (₹)"), { target: { value: "-5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save September 2026 balances" }));
    const input = screen.getByLabelText("Payables (₹)") as HTMLInputElement;
    await waitFor(() => expect(input.getAttribute("aria-invalid")).toBe("true"));
    expect(input.value).toBe("-5");
    expect(document.getElementById(input.getAttribute("aria-describedby") ?? "")?.textContent).toBe("An amount can't be negative");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("sends one request for a double click", async () => {
    let finish: (r: Response) => void = () => {};
    const fetchMock = vi.fn().mockReturnValue(new Promise<Response>((resolve) => (finish = resolve)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BalancesForm data={data()} />);
    const save = screen.getByRole("button", { name: "Save September 2026 balances" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    finish(res(data()));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });
});
