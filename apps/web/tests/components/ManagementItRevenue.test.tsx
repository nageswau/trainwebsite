import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ItRevenuePage from "@/app/management/revenue/it/page";
import ManagementItRevenue from "@/components/ManagementItRevenue";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { ItRevenue, ItRevenuePaymentPage, ItRevenueQuery } from "@/lib/managementItRevenue";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/revenue/it" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const accountant: ManagementMe = { id: "a1", full_name: "Ravi Accountant", role: "accountant", tiers: { operational: false, finance: true, partner_only: false } };
const PYTHON = "11111111-1111-4111-8111-111111111111";
const MORNING = "22222222-2222-4222-8222-222222222222";
const QUERY: ItRevenueQuery = { month: "2026-05", period: "month", scope: null, page: 1 };

function revenue(overrides: Partial<ItRevenue> = {}): ItRevenue {
  return {
    month: "2026-05", period: "month", start: "2026-05-01", end: "2026-05-31", label: "May 2026",
    totals: { revenue: "152500.00", costs: "40000.00", contribution: "112500.00", enrolments: 5 },
    income: [{ key: "enrolment_fees", label: "Enrolment fees", amount: "150000.00" }, { key: "other_fees", label: "Other IT fees", amount: "2500.00" }, { key: "manual", label: "Manual income", amount: "0.00" }],
    costs: [{ key: "trainer", label: "Trainer", amount: "30000.00" }, { key: "marketing", label: "Marketing", amount: "10000.00" }, { key: "operational", label: "Operational", amount: "0.00" }],
    courses: [
      {
        program_id: PYTHON, title: "Python Full Stack", enrolments: 5, revenue: "150000.00", costs: "40000.00", contribution: "110000.00",
        batches: [{ batch_id: MORNING, name: "Morning", enrolments: 5, revenue: "150000.00", costs: "30000.00" }], unbatched: { revenue: "0.00", costs: "10000.00" },
      },
    ],
    unlinked: { revenue: "2500.00", costs: "0.00" }, placement: null, not_counted: [],
    ...overrides,
  }; // prettier-ignore
}

const PAYMENTS: ItRevenuePaymentPage = {
  items: [{ id: "p1", entry_date: "2026-05-10", kind: "Enrolment fee", amount: "30000.00", currency: "INR", installment_no: 2, receipt_no: "RCP-1", enrollment_code: "ENR-1", course: "Python Full Stack", batch: "Morning" }],
  total: 26, limit: 25, offset: 25,
}; // prettier-ignore

function view(props: Partial<Parameters<typeof ManagementItRevenue>[0]> = {}) {
  return render(<ManagementItRevenue data={revenue()} error="" query={QUERY} maxMonth="2026-10" payments={null} paymentsError="" {...props} />);
}

describe("mgmt-007 ManagementItRevenue", () => {
  afterEach(cleanup);

  it("shows the four figures and each course with its batches, the unlinked row and the total", () => {
    view();
    const tiles = screen.getByRole("list", { name: "IT Training figures" });
    expect(tiles).toHaveTextContent("₹1,52,500.00");
    expect(tiles).toHaveTextContent("₹1,12,500.00");
    const table = screen.getByRole("table", { name: "Revenue per course" });
    expect(within(table).getAllByRole("rowheader").map((th) => th.textContent)).toEqual(["Python Full Stack", "Morning", "Course-wide entries", "Not linked to a course", "Total"]);
    expect(within(table).getByRole("row", { name: /^Python Full Stack/ })).toHaveTextContent("₹1,10,000.00");
    expect(within(table).getByRole("row", { name: /^Total/ })).toHaveTextContent("₹1,52,500.00");
    expect(screen.getByRole("link", { name: "Payments: Python Full Stack · Morning" })).toHaveAttribute("href", `/management/revenue/it?month=2026-05&period=month&batch=${MORNING}#payments`);
    expect(screen.getByRole("link", { name: "Payments: Not linked to a course" })).toHaveAttribute("href", "/management/revenue/it?month=2026-05&period=month&unlinked=1#payments");
  });

  it("links the revenue to its drill-down for the same period (mgmt-033)", () => {
    view({ query: { ...QUERY, period: "year" }, data: revenue({ period: "year" }) });
    expect(screen.getByRole("link", { name: "Drill down into this revenue" })).toHaveAttribute("href", "/management/drill/it?month=2026-05&period=year");
  });

  it("splits income and costs by kind and says placement revenue is not tracked", () => {
    view();
    expect(within(screen.getByRole("table", { name: "Income by kind" })).getByRole("row", { name: /Other IT fees/ })).toHaveTextContent("₹2,500.00");
    expect(within(screen.getByRole("table", { name: "Costs by kind" })).getByRole("row", { name: /Trainer/ })).toHaveTextContent("₹30,000.00");
    expect(screen.getByText(/Placement revenue:/).closest("p")).toHaveTextContent("not tracked");
  });

  it("keeps the month and period in a GET form and names the period", () => {
    view({ data: revenue({ period: "year", start: "2026-04-01", label: "Financial year 2026-27 to date" }), query: { ...QUERY, period: "year" } });
    expect((screen.getByLabelText("Month", { exact: true }) as HTMLInputElement).value).toBe("2026-05");
    expect((screen.getByLabelText("Show") as HTMLSelectElement).value).toBe("year");
    expect(screen.getByLabelText("Month", { exact: true }).closest("form")).toHaveAttribute("method", "get");
    expect(screen.getByText(/^Financial year 2026-27 to date: .*2026 to .*2026\./)).toBeInTheDocument();
  });

  it("shows an empty state, the other-currency note and a period error", () => {
    view({ data: revenue({ courses: [], unlinked: { revenue: "0.00", costs: "0.00" }, not_counted: [{ currency: "USD", amount: "300.00", count: 1 }] }) });
    expect(screen.getByRole("status")).toHaveTextContent("No IT Training revenue, costs or enrolments in May 2026");
    expect(screen.queryByRole("table", { name: "Revenue per course" })).toBeNull();
    expect(screen.getByText(/another currency/)).toHaveTextContent("$300.00 (1 payment)");
    cleanup();
    view({ data: null, error: "Choose this month or an earlier one" });
    expect(screen.getByRole("alert")).toHaveTextContent("Choose this month or an earlier one");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("lists the chosen batch's payments without names, with paging", () => {
    view({ query: { ...QUERY, scope: { batch: MORNING }, page: 2 }, payments: PAYMENTS });
    const section = screen.getByRole("region", { name: "Payments: Python Full Stack · Morning" });
    const row = within(section).getByRole("row", { name: /ENR-1/ });
    expect(row).toHaveTextContent("Enrolment fee · instalment 2");
    expect(row).toHaveTextContent("₹30,000.00");
    expect(section).toHaveTextContent("Showing 26–26 of 26");
    expect(within(section).getByRole("link", { name: "Previous" })).toHaveAttribute("href", `/management/revenue/it?month=2026-05&period=month&batch=${MORNING}#payments`);
    expect(within(section).queryByRole("link", { name: "Next" })).toBeNull();
  });

  it("says when the chosen course has no payments, and shows a payments error", () => {
    view({ query: { ...QUERY, scope: { program: PYTHON } }, payments: { items: [], total: 0, limit: 25, offset: 0 } });
    expect(screen.getByRole("heading", { name: "Payments: Python Full Stack" })).toBeInTheDocument();
    expect(screen.getByText("No counted payments in this period.")).toBeInTheDocument();
    cleanup();
    view({ query: { ...QUERY, scope: { program: "33333333-3333-4333-8333-333333333333" } }, paymentsError: "Choose a course from the list" });
    expect(screen.getByRole("heading", { name: "Payments: the chosen course" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a course from the list");
  });
});

describe("mgmt-007 IT revenue page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(figures: ItRevenue | Error, payments: ItRevenuePaymentPage | Error = PAYMENTS) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const result = path === "/api/v1/management/me" ? accountant : path.startsWith("/api/v1/management/revenue/it/payments") ? payments : path.startsWith("/api/v1/management/revenue/it") ? figures : (null as never);
      if (result instanceof Error) throw result;
      return result as never;
    });
  }

  it("asks for the period in the address and renders the dashboard", async () => {
    answer(revenue());
    render(await ItRevenuePage({ searchParams: Promise.resolve({ month: "2026-05", period: "year" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/revenue/it?month=2026-05&period=year");
    expect(serverApi).not.toHaveBeenCalledWith(expect.stringContaining("/payments"));
    expect(screen.getByRole("heading", { name: "IT Training revenue" })).toBeInTheDocument();
  });

  it("loads the chosen course's payments", async () => {
    answer(revenue());
    render(await ItRevenuePage({ searchParams: Promise.resolve({ month: "2026-05", program: PYTHON }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/management/revenue/it/payments?month=2026-05&period=month&program_id=${PYTHON}&limit=25&offset=0`);
    expect(screen.getByRole("region", { name: "Payments: Python Full Stack" })).toBeInTheDocument();
  });

  it("shows the API's 422 message and keeps a failed payment list apart from the dashboard", async () => {
    answer(new ApiError("Choose this month or an earlier one", 422), new Error("boom"));
    render(await ItRevenuePage({ searchParams: Promise.resolve({ month: "2099-01", unlinked: "1" }) }));
    const alerts = screen.getAllByRole("alert").map((a) => a.textContent);
    expect(alerts).toEqual(["Choose this month or an earlier one", "The payments are unavailable right now. Please try again."]);
  });

  it("shows the access card when the API refuses the caller", async () => {
    answer(new ApiError("Finance access required", 403));
    render(await ItRevenuePage({ searchParams: Promise.resolve({}) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/revenue/it");
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Finance access required")).toBeTruthy();
  });

  it("puts the page in the management shell with the caller's finance sidebar", async () => {
    answer(revenue());
    const shell = elements(await ItRevenuePage({ searchParams: Promise.resolve({}) })).find((el) => el.type === PortalShell)!;
    expect(shell.props.roleLabel).toBe("Accountant");
    expect(shell.props.nav).toContainEqual({ label: "IT Training revenue", href: "/management/revenue/it" });
  });
});
