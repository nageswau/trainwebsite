import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AbroadRevenuePage from "@/app/management/revenue/abroad/page";
import ManagementAbroadRevenue from "@/components/ManagementAbroadRevenue";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { AbroadRevenue } from "@/lib/managementAbroadRevenue";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/revenue/abroad" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Asha Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const money = (month: string, year: string) => ({ month, year });
const zero = money("0.00", "0.00");

function revenue(overrides: Partial<AbroadRevenue> = {}): AbroadRevenue {
  return {
    month: "2026-05",
    year_start: "2026-04-01",
    year_label: "2026-27",
    commission_visible: true,
    kinds: [
      { key: "service_fees", label: "Student service fees", ...money("25000.00", "50000.00") },
      { key: "other_payments", label: "Application-related & other student payments", ...money("15000.00", "15000.00") },
      { key: "university_commission", label: "University commission", ...money("0.00", "200000.00") },
      { key: "manual", label: "Recorded in the ledger", ...zero },
    ],
    revenue: money("40000.00", "265000.00"),
    agent_generated: money("15000.00", "15000.00"),
    breakdowns: [
      { key: "country", label: "Country-wise", rows: [{ label: "United Kingdom", ...money("15000.00", "215000.00") }], unattributed: money("25000.00", "50000.00") },
      { key: "university", label: "University-wise", rows: [{ label: "Coventry University", ...money("15000.00", "215000.00") }], unattributed: money("25000.00", "50000.00") },
      { key: "intake", label: "Intake-wise", rows: [{ label: "Sep 2026", ...money("15000.00", "15000.00") }], unattributed: money("25000.00", "250000.00") },
      { key: "agency", label: "Agency-wise", rows: [{ label: "Global Pathways", ...money("15000.00", "15000.00") }], unattributed: money("25000.00", "250000.00") },
    ],
    expenses: [{ label: "Agent commissions", ...money("4000.00", "12000.00") }, { label: "Travel", ...money("1500.00", "3000.00") }],
    expense_total: money("5500.00", "15000.00"),
    shared_expenses: money("120000.00", "240000.00"),
    contribution: money("34500.00", "250000.00"),
    not_counted: [],
    ...overrides,
  };
}

const render_ = (data: AbroadRevenue | null, error = "") => render(<ManagementAbroadRevenue data={data} error={error} month="2026-05" maxMonth="2026-10" />);

describe("mgmt-006 ManagementAbroadRevenue", () => {
  afterEach(cleanup);

  it("summarises revenue, expenses and the gross contribution for the month and the year", () => {
    render_(revenue());
    const summary = within(screen.getByRole("list", { name: /abroad education summary/i })).getAllByRole("listitem");
    expect(summary.map((tile) => tile.querySelector("dt")?.textContent)).toEqual(["Abroad Education revenue (year to date)", "Expenses (year to date)", "Gross contribution (year to date)"]);
    expect(summary[2].querySelector("dd")).toHaveTextContent("₹2,50,000.00");
    expect(summary[2]).toHaveTextContent("This month: ₹34,500.00");
  });

  it("lists revenue by kind with the total, and agent-generated revenue as part of it", () => {
    render_(revenue());
    const kinds = screen.getByRole("table", { name: /revenue by kind/i });
    expect(within(kinds).getAllByRole("rowheader").map((th) => th.textContent)).toEqual([
      "Student service fees", "Application-related & other student payments", "University commission", "Recorded in the ledger", "Total revenue",
    ]); // prettier-ignore
    expect(within(kinds).getByRole("row", { name: /Total revenue/ })).toHaveTextContent("₹2,65,000.00");
    expect(screen.getByText(/agent-generated revenue/i)).toHaveTextContent("₹15,000.00");
  });

  it("shows each breakdown with its Unattributed row, a share bar, and the total revenue", () => {
    render_(revenue());
    for (const [name, first, header] of [["Country-wise revenue", "United Kingdom", "Country"], ["University-wise revenue", "Coventry University", "University"], ["Intake-wise revenue", "Sep 2026", "Intake"], ["Agency-wise revenue", "Global Pathways", "Agency"]]) {
      const heading = screen.getByRole("heading", { level: 3, name });
      expect(heading.closest(".table-wrap")).toBeNull();
      const table = within(screen.getByRole("region", { name })).getByRole("table");
      expect(within(table).getAllByRole("columnheader")[0]).toHaveTextContent(header);
      expect(within(table).getAllByRole("rowheader").map((th) => th.textContent)).toEqual([first, "Unattributed", "Total"]);
    }
    const country = within(screen.getByRole("region", { name: "Country-wise revenue" })).getByRole("row", { name: /United Kingdom/ });
    expect(country).toHaveTextContent("81.1%");
  });

  it("lists the Abroad expenses and notes the shared costs that are not allocated here", () => {
    render_(revenue());
    const expenses = within(screen.getByRole("region", { name: "Abroad expenses" })).getByRole("table");
    expect(within(expenses).getByRole("row", { name: /Agent commissions/ })).toHaveTextContent("₹12,000.00");
    expect(within(expenses).getByRole("row", { name: /Total expenses/ })).toHaveTextContent("₹15,000.00");
    expect(screen.getByText(/shared/i, { selector: "p" })).toHaveTextContent("₹1,20,000.00");
  });

  it("shows the summary as tiles and lets the expense table fit a phone without scrolling (browser QA-01)", () => {
    render_(revenue());
    expect(screen.queryByRole("table", { name: /abroad education summary/i })).toBeNull(); // tiles, which stack on a phone
    expect(within(screen.getByRole("region", { name: "Abroad expenses" })).getByRole("table").style.minWidth).toBe("0");
  });

  it("tells the accountant the figures leave university commission out", () => {
    const kinds = revenue().kinds.filter((k) => k.key !== "university_commission");
    render_(revenue({ commission_visible: false, kinds }));
    expect(screen.getByText(/university commission is shown to partners only/i)).toBeInTheDocument();
    expect(screen.queryByRole("rowheader", { name: "University commission" })).toBeNull();
  });

  it("does not show the commission note to a partner", () => {
    render_(revenue());
    expect(screen.queryByText(/shown to partners only/i)).toBeNull();
  });

  it("names the month and the financial year to date, keeps the month in a GET form and links to the ledger", () => {
    render_(revenue());
    expect(screen.getByText(/May 2026/, { selector: "p" })).toHaveTextContent("financial year 2026-27");
    const input = screen.getByLabelText("Month") as HTMLInputElement;
    expect(input.value).toBe("2026-05");
    expect(input.max).toBe("2026-10");
    expect(input.closest("form")).toHaveAttribute("method", "get");
    expect(screen.getByRole("link", { name: /abroad lines in the ledger/i })).toHaveAttribute("href", "/management/ledger?month=2026-05&vertical=abroad&include=auto");
  });

  it("says when nothing is recorded in the year", () => {
    const empty = revenue({
      kinds: revenue().kinds.map((k) => ({ ...k, ...zero })), revenue: zero, agent_generated: zero, expenses: [], expense_total: zero, shared_expenses: zero, contribution: zero,
      breakdowns: revenue().breakdowns.map((b) => ({ ...b, rows: [], unattributed: zero })),
    }); // prettier-ignore
    render_(empty);
    expect(screen.getByRole("status")).toHaveTextContent("No Abroad Education revenue or expenses are recorded in the financial year 2026-27 up to May 2026 yet.");
    expect(screen.getByText(/no abroad expenses/i)).toBeInTheDocument();
  });

  it("notes automatic lines in another currency that are not counted", () => {
    render_(revenue({ not_counted: [{ currency: "GBP", kind: "income", amount: "300.00", count: 2 }] }));
    expect(screen.getByText(/not counted/i)).toHaveTextContent("£300.00 income (2 lines)");
  });

  it("shows the error and no figures when the dashboard could not be read", () => {
    render_(null, "Choose this month or an earlier one");
    expect(screen.getByRole("alert")).toHaveTextContent("Choose this month or an earlier one");
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("mgmt-006 Abroad revenue page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(figures: AbroadRevenue | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const result = path === "/api/v1/management/me" ? partner : path.startsWith("/api/v1/management/revenue/abroad") ? figures : ({ id: "p1", role: "partner", division: "global", full_name: "Asha" } as never);
      if (result instanceof Error) throw result;
      return result as never;
    });
  }

  it("asks for the month in the address and renders the dashboard", async () => {
    answer(revenue());
    render(await AbroadRevenuePage({ searchParams: Promise.resolve({ month: "2026-05" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/revenue/abroad?month=2026-05");
    expect(screen.getByRole("heading", { level: 2, name: "Abroad Education revenue" })).toBeInTheDocument();
  });

  it("shows the API's 422 message", async () => {
    answer(new ApiError("Choose this month or an earlier one", 422));
    render(await AbroadRevenuePage({ searchParams: Promise.resolve({ month: "2099-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose this month or an earlier one");
  });

  it("shows a generic message when the API fails", async () => {
    answer(new ApiError("boom", 500));
    render(await AbroadRevenuePage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("The Abroad revenue dashboard is unavailable right now. Please try again.");
  });

  it("drops a malformed month and shows the access card when the API refuses the caller", async () => {
    answer(new ApiError("Finance access required", 403));
    render(await AbroadRevenuePage({ searchParams: Promise.resolve({ month: "20-1" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/revenue/abroad");
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Finance access required")).toBeTruthy();
  });

  it("puts the page in the management shell with the caller's sidebar", async () => {
    answer(revenue());
    const shell = elements(await AbroadRevenuePage({ searchParams: Promise.resolve({}) })).find((el) => el.type === PortalShell)!;
    expect(shell.props.roleLabel).toBe("Partner");
    expect(shell.props.nav).toContainEqual({ label: "Abroad Education revenue", href: "/management/revenue/abroad" });
  });
});
