import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruitmentRevenuePage from "@/app/management/revenue/recruitment/page";
import ManagementRecruitmentRevenue from "@/components/ManagementRecruitmentRevenue";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import type { RecruitmentRevenue } from "@/lib/managementRecruitmentRevenue";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/revenue/recruitment" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const accountant: ManagementMe = { id: "a1", full_name: "Ravi Accountant", role: "accountant", tiers: { operational: false, finance: true, partner_only: false } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Sam Admin", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const QUERY = { month: "2026-05", period: "month" as const };

function figures(overrides: Partial<RecruitmentRevenue> = {}): RecruitmentRevenue {
  return {
    month: "2026-05", period: "month", start: "2026-05-01", end: "2026-05-31", label: "May 2026", kpi_end: "2026-05-31", revenue_visible: true,
    revenue: {
      total: "160000.00",
      kinds: [{ key: "recruiter_invoices", label: "Recruiter invoice payments", amount: "150000.00" }, { key: "ledger:Internship programs", label: "Internship programs", amount: "10000.00" }],
    },
    kpis: {
      recruiters: 4, partner_companies: 12, open_positions: 9, candidates: 40, interviews: 18, selections: 6, joining: 4,
      placement_pct: 10.0, revenue_per_placement: "40000.00",
    },
    ...overrides,
  }; // prettier-ignore
}

function view(props: Partial<Parameters<typeof ManagementRecruitmentRevenue>[0]> = {}) {
  return render(<ManagementRecruitmentRevenue data={figures()} error="" query={QUERY} maxMonth="2026-10" {...props} />);
}

describe("mgmt-008 ManagementRecruitmentRevenue", () => {
  afterEach(cleanup);

  it("shows the nine KPIs in source order", () => {
    view();
    const tiles = within(screen.getByRole("list", { name: "Recruitment KPIs" })).getAllByRole("listitem").map((li) => li.textContent);
    expect(tiles).toEqual([
      "Recruiters4", "Partner companies12", "Open positions9", "Candidates40", "Interviews18", "Selections6", "Joining4",
      "Placement percentage10.0%", "Revenue per placement₹40,000.00",
    ]);
  });

  it("lists the revenue kinds and the total, and says how to record the other kinds", () => {
    view();
    const table = screen.getByRole("table", { name: "Revenue by kind" });
    expect(within(table).getByRole("row", { name: /Recruiter invoice payments/ })).toHaveTextContent("₹1,50,000.00");
    expect(within(table).getByRole("row", { name: /Internship programs/ })).toHaveTextContent("₹10,000.00");
    expect(within(table).getByRole("row", { name: /^Total/ })).toHaveTextContent("₹1,60,000.00");
    expect(screen.getByText(/corporate training/i)).toHaveTextContent("Recruitment");
  });

  it("shows — for a ratio with nothing to divide by, and an empty revenue state", () => {
    view({ data: figures({ revenue: { total: "0.00", kinds: [{ key: "recruiter_invoices", label: "Recruiter invoice payments", amount: "0.00" }] }, kpis: { ...figures().kpis, candidates: 0, joining: 0, placement_pct: null, revenue_per_placement: null } }) });
    const tiles = screen.getByRole("list", { name: "Recruitment KPIs" });
    expect(within(tiles).getByText("Placement percentage").parentElement).toHaveTextContent("—");
    expect(within(tiles).getByText("Revenue per placement").parentElement).toHaveTextContent("—");
    expect(screen.getByRole("status")).toHaveTextContent("No recruitment revenue in May 2026");
  });

  it("shows the super admin the KPIs only, with no money anywhere", () => {
    view({ data: figures({ revenue_visible: false, revenue: null, kpis: { ...figures().kpis, revenue_per_placement: null } }) });
    expect(within(screen.getByRole("list", { name: "Recruitment KPIs" })).getAllByRole("listitem")).toHaveLength(8);
    expect(screen.queryByText("Revenue per placement")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText(/₹/)).toBeNull();
    expect(screen.queryByRole("link", { name: "Drill down into this revenue" })).toBeNull(); // mgmt-033: money chains are finance-only
  });

  it("links the revenue to its drill-down for the same period (mgmt-033)", () => {
    view();
    expect(screen.getByRole("link", { name: "Drill down into this revenue" })).toHaveAttribute("href", "/management/drill/recruitment?month=2026-05&period=month");
  });

  it("keeps the month and period in a GET form and names the period and the KPI range", () => {
    view({ data: figures({ period: "year", start: "2026-04-01", end: "2026-10-31", kpi_end: "2026-10-13", label: "Financial year 2026-27 to date" }), query: { month: "2026-10", period: "year" } });
    expect((screen.getByLabelText("Show") as HTMLSelectElement).value).toBe("year");
    expect(screen.getByLabelText("Month", { exact: true }).closest("form")).toHaveAttribute("method", "get");
    expect(screen.getByText(/^Financial year 2026-27 to date:/)).toHaveTextContent(`counted to ${formatCalendarDate("2026-10-13")}`);
  });

  it("shows a period error without figures", () => {
    view({ data: null, error: "Choose this month or an earlier one" });
    expect(screen.getByRole("alert")).toHaveTextContent("Choose this month or an earlier one");
    expect(screen.queryByRole("list", { name: "Recruitment KPIs" })).toBeNull();
  });
});

describe("mgmt-008 Recruitment revenue page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(me: ManagementMe, result: RecruitmentRevenue | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const value = path === "/api/v1/management/me" ? me : path.startsWith("/api/v1/management/revenue/recruitment") ? result : (null as never);
      if (value instanceof Error) throw value;
      return value as never;
    });
  }

  it("asks for the period in the address and renders the dashboard in the finance sidebar", async () => {
    answer(accountant, figures());
    const tree = await RecruitmentRevenuePage({ searchParams: Promise.resolve({ month: "2026-05", period: "year" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/revenue/recruitment?month=2026-05&period=year");
    const shell = elements(tree).find((el) => el.type === PortalShell)!;
    expect(shell.props.nav).toContainEqual({ label: "Recruitment revenue", href: "/management/revenue/recruitment" });
    render(tree);
    expect(screen.getByRole("heading", { name: "Recruitment & Placement revenue" })).toBeInTheDocument();
  });

  it("names the page for the KPIs and keeps the super admin's own sidebar", async () => {
    answer(superAdmin, figures({ revenue_visible: false, revenue: null }));
    const tree = await RecruitmentRevenuePage({ searchParams: Promise.resolve({}) });
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
    render(tree);
    expect(screen.getByRole("heading", { name: "Recruitment & Placement KPIs" })).toBeInTheDocument();
  });

  it("shows the API's 422 message, and the access card when refused", async () => {
    answer(accountant, new ApiError("Choose this month or an earlier one", 422));
    render(await RecruitmentRevenuePage({ searchParams: Promise.resolve({ month: "2099-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose this month or an earlier one");
    cleanup();
    answer(accountant, new ApiError("Management access required", 403));
    render(await RecruitmentRevenuePage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
  });
});
