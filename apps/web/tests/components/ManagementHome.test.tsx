import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementPage from "@/app/management/page";
import ManagementHome from "@/components/ManagementHome";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { ManagementHome as Home } from "@/lib/managementHome";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Arjun Kumar", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const accountant: ManagementMe = { id: "a1", full_name: "Ravi Accountant", role: "accountant", tiers: { operational: false, finance: true, partner_only: false } };
const PANELS = ["Urgent issues", "Pending decisions", "Today's meetings", "Target vs actual", "Financial position", "Business growth", "My tasks", "Recent discussions", "Next month plan"];
const person = { id: "u1", full_name: "Meera Shah", role: "partner" };

function business(over: Partial<Home> = {}): Home {
  return {
    as_of: "2026-10-14", month: "2026-10", label: "October 2026", scope: "business",
    snapshot: { students: 1240, applications: 37, enrollments: 6, revenue: "1250000.00", expenses: "400000.00", profit: "850000.00", cash: { amount: "900000.00", month: "2026-09" } },
    urgent: [{ key: "overdue_tasks", label: "Overdue tasks", count: 2 }, { key: "overdue_receivables", label: "Overdue receivables", count: 1, amount: "45000.00" }],
    pending_decisions: { items: [{ id: "d1", topic: "Renew office lease", discussion_date: "2026-10-01", decision: "Renew for two years", responsible: person, deadline: "2026-10-10", status: "open" }], total: 3 },
    meetings: { items: [{ id: "m1", title: "Partner sync", kind: "partner", starts_at: "2026-10-14T05:30:00Z", status: "scheduled" }], total: 7 },
    targets: { month: "2026-10", label: "October 2026", rows: [{ item_id: "i1", text: "100+ applicants", kpi_label: "Applications", unit: "count", target: "100", actual: "37", achievement: 37 }], row_total: 1, free_text: { total: 4, done: 1 } },
    financial_position: { receivables: "300000.00", receivables_overdue: "45000.00", pending_invoices: { count: 4, amount: "120000.00" }, balance_month: "2026-09", cash_bank: "900000.00", payables: "50000.00", tax_liabilities: null },
    growth: { month: "2026-09", score: 64, rag: "amber", factors: [{ key: "revenue", label: "Revenue", change: 12.5, rag: "green" }, { key: "profit", label: "Profit", change: null, rag: "amber" }, { key: "expenses", label: "Expenses", change: -4, rag: "red" }] },
    my_tasks: { items: [{ id: "t1", title: "Sign the lease", priority: "high", deadline: "2026-10-12", status: "open", band: "overdue" }], counts: { overdue: 1, today: 0, week: 2, later: 0, completed: 0 } },
    recent_discussions: { items: [{ id: "d2", topic: "Japan partnership", discussion_date: "2026-10-12", decision: null, responsible: null, deadline: null, status: "in_progress" }], total: 9 },
    next_plan: { month: "2026-11", label: "November 2026", plan: { status: "draft", item_count: 5, kpi_count: 3 } },
    ...over,
  }; // prettier-ignore
}

function operational(): Home {
  const home = business({ scope: "operational", urgent: [{ key: "red_health", label: "Health factors in Red", count: 1 }], growth: { month: "2026-09", score: 50, rag: "amber", factors: [{ key: "enrollment", label: "Enrollment", change: null, rag: "amber" }] } });
  delete home.financial_position; // HM2: the API leaves the key out
  return { ...home, snapshot: { students: 1240, applications: 37, enrollments: 6 } };
}

function empty(): Home {
  return business({
    snapshot: { students: 0, applications: 0, enrollments: 0, revenue: "0.00", expenses: "0.00", profit: "0.00", cash: { amount: null, month: null } },
    urgent: [], pending_decisions: { items: [], total: 0 }, meetings: { items: [], total: 0 }, targets: null,
    financial_position: { receivables: "0.00", receivables_overdue: "0.00", pending_invoices: { count: 0, amount: "0.00" }, balance_month: null, cash_bank: null, payables: null, tax_liabilities: null },
    growth: { month: "2026-09", score: null, rag: null, factors: [] }, my_tasks: { items: [], counts: { overdue: 0, today: 0, week: 0, later: 0, completed: 0 } },
    recent_discussions: { items: [], total: 0 }, next_plan: { month: "2026-11", label: "November 2026", plan: null },
  }); // prettier-ignore
}

const morning = new Date("2026-10-14T03:00:00Z"); // 08:30 IST
afterEach(cleanup);

describe("mgmt-031 ManagementHome", () => {
  it("greets the partner by first name with the month, then the seven snapshot figures", () => {
    render(<ManagementHome data={business()} userName="Arjun Kumar" now={morning} />);
    expect(screen.getByRole("heading", { level: 2, name: "Good morning, Arjun" })).toBeTruthy();
    expect(screen.getByText("October 2026")).toBeTruthy();
    const tiles = within(screen.getByRole("list", { name: "Today's business snapshot" })).getAllByRole("listitem");
    expect(tiles.map((t) => t.querySelector("span")?.textContent)).toEqual(["Revenue", "Expenses", "Profit", "Cash", "Students", "Applications", "Enrollments"]);
    expect(tiles[0].textContent).toContain("₹12,50,000.00");
    expect(tiles[3].textContent).toContain("as of September 2026");
    expect(tiles[4].textContent).toContain("1,240");
  });

  it("shows all nine panels, each linking to its page", () => {
    render(<ManagementHome data={business()} userName="Arjun Kumar" now={morning} />);
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(PANELS);
    const href = (panel: string, name: string | RegExp) => within(screen.getByRole("region", { name: panel })).getByRole("link", { name }).getAttribute("href");
    expect(href("Urgent issues", /Overdue tasks/)).toBe("/management/tasks?view=everyone");
    expect(href("Pending decisions", "All 3 pending decisions")).toBe("/management/discussions#pending-decisions");
    expect(href("Pending decisions", "Renew office lease")).toBe("/management/discussions/d1");
    expect(href("Today's meetings", "Partner sync")).toBe("/management/meetings/m1");
    expect(href("Today's meetings", "All 7 meetings today")).toBe("/management/meetings"); // QA31-01: bounded, with the day's total
    expect(href("Target vs actual", "Open the October 2026 plan")).toBe("/management/plans/2026-10");
    expect(href("Financial position", "Open accounts")).toBe("/management/accounts?month=2026-09");
    expect(href("Business growth", "Open the health score")).toBe("/management/health");
    expect(href("My tasks", "Sign the lease")).toBe("/management/tasks/t1");
    expect(href("Recent discussions", "All 9 discussions")).toBe("/management/discussions");
    expect(href("Next month plan", "Open the November 2026 plan")).toBe("/management/plans/2026-11");
  });

  it("shows the urgent amounts, the target row and the growth changes", () => {
    render(<ManagementHome data={business()} userName="Arjun Kumar" now={morning} />);
    expect(within(screen.getByRole("region", { name: "Urgent issues" })).getByRole("link", { name: /Overdue receivables/ }).textContent).toContain("₹45,000.00");
    expect(within(screen.getByRole("region", { name: "Target vs actual" })).getByText("37%")).toBeTruthy();
    const growth = screen.getByRole("region", { name: "Business growth" });
    expect(within(growth).getByText("64/100")).toBeTruthy();
    expect(within(growth).getByText("+12.5%")).toBeTruthy();
    expect(within(growth).getByText("−4%")).toBeTruthy();
    // QA31-02: only the factors that changed are listed; the rest are counted, not shown as "—"
    expect(within(growth).getAllByRole("listitem").map((li) => li.textContent?.split(":")[0])).toEqual(["Revenue", "Expenses"]);
    expect(within(growth).getByText("1 factor has no month-on-month comparison yet.")).toBeTruthy();
  });

  it("speaks of money in the snapshot note only to the partner (QA31-03)", () => {
    render(<ManagementHome data={business()} userName="Arjun Kumar" now={morning} />);
    expect(screen.getByText("Money, applications and enrollments are for October 2026 to date (India time); cash is the latest balance entered.")).toBeTruthy();
    cleanup();
    render(<ManagementHome data={operational()} userName="Root Admin" now={morning} />);
    expect(screen.getByText("Applications and enrollments are for October 2026 to date (India time).")).toBeTruthy();
  });

  it("gives the super admin the operational home: no money anywhere (AC)", () => {
    const { container } = render(<ManagementHome data={operational()} userName="Root Admin" now={morning} />);
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(PANELS.filter((p) => p !== "Financial position"));
    const tiles = within(screen.getByRole("list", { name: "Today's business snapshot" })).getAllByRole("listitem");
    expect(tiles.map((t) => t.querySelector("span")?.textContent)).toEqual(["Students", "Applications", "Enrollments"]);
    expect(container.textContent).not.toContain("₹");
  });

  it("says so in every panel in the first month with no data", () => {
    render(<ManagementHome data={empty()} userName="Arjun Kumar" now={morning} />);
    expect(screen.getByText("No urgent issues.")).toBeTruthy();
    expect(screen.getByText("No pending decisions.")).toBeTruthy();
    expect(screen.getByText("No meetings today.")).toBeTruthy();
    expect(screen.getByText("No plan for October 2026 yet.")).toBeTruthy();
    expect(screen.getByText("Not enough data to score September 2026.")).toBeTruthy();
    expect(screen.getByText("No open tasks for you.")).toBeTruthy();
    expect(screen.getByText("No discussions yet.")).toBeTruthy();
    expect(screen.getByText("No plan for November 2026 yet.")).toBeTruthy();
    const tiles = within(screen.getByRole("list", { name: "Today's business snapshot" })).getAllByRole("listitem");
    expect(tiles[3].textContent).toContain("Not entered");
    expect(within(screen.getByRole("region", { name: "Next month plan" })).getByRole("link", { name: "Plan November 2026" }).getAttribute("href")).toBe("/management/plans");
  });
});

describe("mgmt-031 Command Center page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  const shellOf = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === PortalShell)!;

  it("reads /management/home for the operational tier and shows it above the pillars", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/management/home" ? business() : partner) as never);
    const shell = shellOf(elements(await ManagementPage()));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/home");
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("region", { name: "Pending decisions" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Management Command Center" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Students" })).toBeTruthy();
  });

  it("never asks the accountant's page for the home", async () => {
    vi.mocked(serverApi).mockResolvedValue(accountant as never);
    const shell = shellOf(elements(await ManagementPage()));
    expect(serverApi).not.toHaveBeenCalledWith("/api/v1/management/home");
    render(<>{shell.props.children}</>);
    expect(screen.queryByRole("region", { name: "Pending decisions" })).toBeNull();
  });

  it("keeps the Command Center when the home fails, with an alert", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/home") throw new ApiError("boom", 500);
      return partner as never;
    });
    const shell = shellOf(elements(await ManagementPage()));
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("Today's figures are unavailable right now. Please try again.");
    expect(screen.getByRole("region", { name: "Students" })).toBeTruthy();
  });
});
