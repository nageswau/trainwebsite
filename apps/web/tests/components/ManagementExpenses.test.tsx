import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ExpensesPage from "@/app/management/expenses/page";
import ManagementExpenses from "@/components/ManagementExpenses";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { ExpenseDashboard } from "@/lib/managementExpenses";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/expenses" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const accountant: ManagementMe = { id: "a1", full_name: "Ravi Accountant", role: "accountant", tiers: { operational: false, finance: true, partner_only: false } };
const HEADS = [["rent", "Rent"], ["salaries", "Salaries"], ["marketing", "Marketing"], ["travel", "Travel"], ["trainers", "Trainers"], ["commissions", "Commissions"], ["technology", "Technology"], ["other", "Other"]] as const; // prettier-ignore

function dashboard(overrides: Partial<ExpenseDashboard> = {}): ExpenseDashboard {
  return {
    month: "2026-05",
    year_start: "2026-04-01",
    year_label: "2026-27",
    groups: HEADS.map(([key, label]) => ({ key, label, month: key === "rent" ? "120000.00" : "0.00", year: key === "rent" ? "240000.00" : key === "travel" ? "60000.00" : "0.00", share: key === "rent" ? 80 : key === "travel" ? 20 : 0 })),
    categories: [{ label: "Office rent", group: "rent", month: "120000.00", year: "240000.00" }, { label: "Travel", group: "travel", month: "0.00", year: "60000.00" }],
    months: [{ month: "2026-04", total: "180000.00" }, { month: "2026-05", total: "120000.00" }],
    totals: { month: "120000.00", year: "300000.00" },
    not_counted: [],
    ...overrides,
  };
}

describe("mgmt-010 ManagementExpenses", () => {
  afterEach(cleanup);

  it("lists the eight §8 heads with monthly and annual figures, a share bar each and the total", () => {
    render(<ManagementExpenses data={dashboard()} error="" month="2026-05" maxMonth="2026-10" />);
    const table = screen.getByRole("table", { name: /expenses by head/i });
    expect(within(table).getAllByRole("rowheader").map((th) => th.textContent)).toEqual([...HEADS.map(([, label]) => label), "Total"]);
    const rent = within(table).getByRole("row", { name: /^Rent/ });
    expect(rent).toHaveTextContent("₹1,20,000.00");
    expect(rent).toHaveTextContent("₹2,40,000.00");
    expect(rent).toHaveTextContent("80%");
    const total = within(table).getByRole("row", { name: /^Total/ });
    expect(total).toHaveTextContent("₹1,20,000.00");
    expect(total).toHaveTextContent("₹3,00,000.00");
  });

  it("names the month and the financial year to date, and keeps the month in a GET form", () => {
    render(<ManagementExpenses data={dashboard()} error="" month="2026-05" maxMonth="2026-10" />);
    expect(screen.getByText(/May 2026/, { selector: "p" })).toHaveTextContent("financial year 2026-27");
    const input = screen.getByLabelText("Month") as HTMLInputElement;
    expect(input.value).toBe("2026-05");
    expect(input.max).toBe("2026-10");
    expect(input.closest("form")).toHaveAttribute("method", "get");
  });

  it("lists the categories and the months that add up to the year", () => {
    render(<ManagementExpenses data={dashboard()} error="" month="2026-05" maxMonth="2026-10" />);
    const categories = screen.getByRole("table", { name: /by category/i });
    expect(within(categories).getByRole("row", { name: /Office rent/ })).toHaveTextContent("Rent");
    const months = screen.getByRole("table", { name: /month by month/i });
    expect(within(months).getByRole("row", { name: /April 2026/ })).toHaveTextContent("₹1,80,000.00");
    expect(within(months).getByRole("row", { name: /financial year to date/i })).toHaveTextContent("₹3,00,000.00");
  });

  it("titles the category and month tables with left-aligned headings outside their scroll areas (browser QA-02)", () => {
    render(<ManagementExpenses data={dashboard()} error="" month="2026-05" maxMonth="2026-10" />);
    for (const name of ["By category", "Month by month"]) {
      const heading = screen.getByRole("heading", { level: 3, name });
      expect(heading.closest(".table-wrap")).toBeNull();
      expect(screen.getByRole("region", { name })).toHaveAttribute("aria-labelledby", heading.id);
    }
    expect(screen.getByRole("table", { name: /month by month/i }).style.minWidth).toBe("0");
  });

  it("links to the month's expense lines in the ledger", () => {
    render(<ManagementExpenses data={dashboard()} error="" month="2026-05" maxMonth="2026-10" />);
    expect(screen.getByRole("link", { name: /expense lines in the ledger/i })).toHaveAttribute("href", "/management/ledger?month=2026-05&kind=expense&include=auto");
  });

  it("says when nothing is recorded in the year, and skips the category table", () => {
    const empty = dashboard({ month: "2026-04", groups: HEADS.map(([key, label]) => ({ key, label, month: "0.00", year: "0.00", share: 0 })), categories: [], months: [{ month: "2026-04", total: "0.00" }], totals: { month: "0.00", year: "0.00" } });
    render(<ManagementExpenses data={empty} error="" month="2026-04" maxMonth="2026-10" />);
    expect(screen.getByRole("status")).toHaveTextContent("No expenses are recorded in the financial year 2026-27 up to April 2026 yet.");
    expect(screen.queryByRole("table", { name: /by category/i })).toBeNull();
    expect(screen.getByRole("table", { name: /expenses by head/i })).toBeInTheDocument();
  });

  it("notes automatic expenses in another currency that are not counted", () => {
    render(<ManagementExpenses data={dashboard({ not_counted: [{ currency: "GBP", amount: "300.00", count: 2 }] })} error="" month="2026-05" maxMonth="2026-10" />);
    expect(screen.getByText(/not counted/i)).toHaveTextContent("£300.00 (2 lines)");
  });

  it("shows the error and no figures when the dashboard could not be read", () => {
    render(<ManagementExpenses data={null} error="Choose this month or an earlier one" month="2027-01" maxMonth="2026-10" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Choose this month or an earlier one");
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("mgmt-010 expenses page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(figures: ExpenseDashboard | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const result = path === "/api/v1/management/me" ? accountant : path.startsWith("/api/v1/management/expenses") ? figures : ({ id: "a1", role: "accountant", division: "global", full_name: "Ravi" } as never);
      if (result instanceof Error) throw result;
      return result as never;
    });
  }

  it("asks for the month in the address and renders the dashboard", async () => {
    answer(dashboard());
    render(await ExpensesPage({ searchParams: Promise.resolve({ month: "2026-05" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/expenses?month=2026-05");
    expect(screen.getByRole("heading", { name: "Expense dashboard" })).toBeInTheDocument();
  });

  it("drops a malformed month and shows the API's 422 message for a future one", async () => {
    answer(new ApiError("Choose this month or an earlier one", 422));
    render(await ExpensesPage({ searchParams: Promise.resolve({ month: "2099-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose this month or an earlier one");
  });

  it("shows the access card when the API refuses the caller", async () => {
    answer(new ApiError("Finance access required", 403));
    render(await ExpensesPage({ searchParams: Promise.resolve({ month: "20-1" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/expenses");
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Finance access required")).toBeTruthy();
  });

  it("puts the page in the management shell with the caller's finance sidebar", async () => {
    answer(dashboard());
    const shell = elements(await ExpensesPage({ searchParams: Promise.resolve({}) })).find((el) => el.type === PortalShell)!;
    expect(shell.props.roleLabel).toBe("Accountant");
    expect(shell.props.nav).toContainEqual({ label: "Expenses & rent", href: "/management/expenses" });
  });
});
