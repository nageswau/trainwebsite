import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ItAccountsPage from "@/components/ItAccountsPage";
import ItAccountsWorkspace from "@/components/ItAccountsWorkspace";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { accountsHref, accountsParams, accountsReport, accountsUrl, day, exportUrl, inr, type AccountsPage } from "@/lib/itAccounts";
import { managementNavFor } from "@/lib/management";
import { PORTAL_NAV, navForPermissions } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/it/admin/accounts" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

afterEach(cleanup);

const BASE = "/it/admin/accounts";
const CHOICES = {
  courses: [{ id: "c1", title: "Java Full Stack" }, { id: "c2", title: "Python" }],
  batches: [{ id: "b1", name: "Java Oct", program_id: "c1" }, { id: "b2", name: "Python Nov", program_id: "c2" }],
};
const FILTERS = { program_id: null, batch_id: null, date_from: "2026-10-01", date_to: "2026-10-31", group: "day", mode: null, kind: null, state: null };
const page = (over: Partial<AccountsPage> = {}): AccountsPage => ({
  report: "collections", items: [{ key: "2026-10-15", label: "15 Oct 2026", payments: 2, amount: 3000 }], total: 1, limit: 50, offset: 0,
  totals: { payments: 2, amount: 3000 }, filters: FILTERS as never, ...CHOICES, ...over,
});
const OWING = {
  enrollment_id: "e1", enrollment_code: "ENR-1", student_id: "s1", student_name: "Asha Rao", student_code: "IT0001", course: "Java Full Stack", batch: "Java Oct",
  total_payable: 45000, paid_confirmed: 15000, balance: 30000, overdue_amount: 30000, next_due_date: "2026-01-10", state: "partially_paid",
};

describe("itAccounts helpers (itc-017)", () => {
  it("keeps only the filters the report takes and builds API, export and tab addresses", () => {
    const search = { report: "outstanding", program_id: "c1", date_from: "2026-10-01", state: "overdue", mode: "cash", offset: "50", junk: "x" };
    expect(accountsReport("nope")).toBe("collections");
    const params = accountsParams("outstanding", search);
    expect(params).toEqual({ program_id: "c1", state: "overdue", offset: 50 });  // no dates or mode on Outstanding
    expect(accountsUrl("outstanding", params)).toBe("/api/v1/it/accounts/reports/outstanding?limit=50&offset=50&program_id=c1&state=overdue");
    expect(exportUrl("outstanding", params)).toBe("/api/v1/it/accounts/reports/outstanding/export?program_id=c1&state=overdue");
    expect(exportUrl("overdue", {})).toBe("/api/v1/it/accounts/reports/overdue/export");
    // a tab keeps the course; the next report's own filters only
    expect(accountsHref(BASE, "receipts", { program_id: "c1", state: "overdue" })).toBe(`${BASE}?report=receipts&program_id=c1`);
    expect(accountsHref(BASE, "collections", { date_from: "2026-10-01" }, 50)).toBe(`${BASE}?report=collections&date_from=2026-10-01&offset=50`);
    expect(accountsParams("collections", { offset: "-3" })).toEqual({});
  });

  it("formats rupees and calendar days without a time-zone shift", () => {
    expect(inr(30000)).toBe("₹30,000.00");
    expect(inr(null)).toBe("—");
    expect(day("2026-01-10")).toBe("10 Jan 2026");
    expect(day(null)).toBe("—");
  });
});

describe("ItAccountsWorkspace (itc-017)", () => {
  it("shows the five reports as links with the current one marked", () => {
    render(<ItAccountsWorkspace report="collections" page={page()} error="" params={{}} basePath={BASE} />);
    const links = within(screen.getByRole("navigation", { name: "Accounts reports" })).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["Collections", "Outstanding", "Overdue installments", "Receipts register", "Refunds & adjustments"]);
    expect(links[0]).toHaveAttribute("aria-current", "page");
  });

  it("shows the totals, the rows and a CSV download for the collections report", () => {
    render(<ItAccountsWorkspace report="collections" page={page()} error="" params={{}} basePath={BASE} />);
    expect(screen.getByText("₹3,000.00", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("Collected", { selector: "dt" })).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Period or course", "Payments", "Amount"]);
    expect(within(table).getByRole("rowheader", { name: "15 Oct 2026" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
    // the date range defaults to what the API applied, and the collections filters are offered
    expect(screen.getByLabelText("From")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("Group by")).toBeInTheDocument();
    expect(screen.getByLabelText("Payment mode")).toBeInTheDocument();
    expect(screen.queryByLabelText("Status")).toBeNull();
  });

  it("lists outstanding enrolments with a per-course summary and links students for the IT Admin", () => {
    const data = page({ report: "outstanding", items: [OWING], totals: { enrolments: 1, balance: 30000, overdue_amount: 30000 },
      by_course: [{ program_id: "c1", title: "Java Full Stack", enrolments: 1, balance: 30000 }] });  // prettier-ignore
    render(<ItAccountsWorkspace report="outstanding" page={data} error="" params={{ program_id: "c1" }} basePath={BASE} studentLinks />);
    expect(screen.getByRole("table", { name: "Outstanding by course" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Asha Rao" })).toHaveAttribute("href", "/it/admin/students/s1/profile");
    expect(screen.getByRole("cell", { name: "Partly paid" })).toBeInTheDocument();
    expect(screen.queryByLabelText("From")).toBeNull();  // Outstanding is as of today
    // with a course applied, only its batches are offered
    const batch = screen.getByLabelText("Batch");
    expect(within(batch).getAllByRole("option").map((o) => o.textContent)).toEqual(["All batches", "Java Oct"]);
  });

  it("does not link students without studentLinks (the accountant)", () => {
    render(<ItAccountsWorkspace report="outstanding" page={page({ report: "outstanding", items: [OWING], totals: { enrolments: 1, balance: 30000, overdue_amount: 0 } })} error="" params={{}} basePath="/management/it-accounts" />);
    expect(screen.queryByRole("link", { name: "Asha Rao" })).toBeNull();
    expect(screen.getByRole("rowheader", { name: "Asha Rao" })).toBeInTheDocument();
  });

  it("says when nothing matches and shows a refused filter above the form", () => {
    render(<ItAccountsWorkspace report="receipts" page={page({ report: "receipts", items: [], total: 0, totals: { receipts: 0, amount: 0 } })} error="" params={{}} basePath={BASE} />);
    expect(screen.getByRole("status")).toHaveTextContent("Nothing matches these filters.");
    expect(screen.queryByRole("button", { name: "Download CSV" })).toBeNull();
    cleanup();
    render(<ItAccountsWorkspace report="collections" page={null} error="Choose a date range of at most 366 days" params={{ date_from: "2025-01-01" }} basePath={BASE} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a date range of at most 366 days");
    expect(screen.getByLabelText("From")).toHaveValue("2025-01-01");
  });

  it("pages through a long list", () => {
    render(<ItAccountsWorkspace report="collections" page={page({ total: 120, offset: 50 })} error="" params={{}} basePath={BASE} />);
    const pager = screen.getByRole("navigation", { name: "Collections pages" });
    expect(within(pager).getByRole("link", { name: "Previous" })).toHaveAttribute("href", `${BASE}?report=collections`);
    expect(within(pager).getByRole("link", { name: "Next" })).toHaveAttribute("href", `${BASE}?report=collections&offset=100`);
  });
});

describe("itc-017 navigation", () => {
  it("adds Accounts to the IT Admin's menu behind payments.view, and IT fee accounts to the finance tier's", () => {
    const accounts = PORTAL_NAV["it/admin"].find((i) => i.href === "/it/admin/accounts");
    expect(accounts).toMatchObject({ label: "Accounts", resource: "payments" });
    expect(navForPermissions(PORTAL_NAV["it/admin"], []).some((i) => i.href === "/it/admin/accounts")).toBe(false);
    const finance = managementNavFor({ operational: false, finance: true, partner_only: false });
    expect(finance.find((i) => i.href === "/management/it-accounts")).toMatchObject({ label: "IT fee accounts", resource: "payments" });
    expect(managementNavFor({ operational: true, finance: false, partner_only: false }).some((i) => i.href === "/management/it-accounts")).toBe(false);
  });
});

describe("ItAccountsPage (itc-017)", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  const accountantMe = { id: "a1", full_name: "Ravi Accountant", role: "accountant", tiers: { operational: false, finance: true, partner_only: false } };

  it("puts the accountant's workspace in the management sidebar and reads the chosen report", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return { id: "a1", full_name: "Ravi Accountant", role: "accountant", division: "global" } as never;
      if (path === "/api/v1/management/me") return accountantMe as never;
      return page({ report: "overdue", items: [], total: 0, totals: { installments: 0, amount: 0 } }) as never;
    });
    const tree = await ItAccountsPage({ shell: "management", searchParams: Promise.resolve({ report: "overdue", program_id: "c1" }) });
    expect(vi.mocked(serverApi)).toHaveBeenCalledWith("/api/v1/it/accounts/reports/overdue?limit=50&offset=0&program_id=c1");
    const shell = elements(tree).find((el) => el.type === PortalShell)!.props as { nav: unknown; roleLabel: string };
    expect(shell.nav).toEqual(managementNavFor(accountantMe.tiers));
    expect(shell.roleLabel).toBe("Accountant");
  });

  it("shows the access card when the API refuses (a counselor)", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return { id: "c1", full_name: "Kiran", role: "counselor", division: "it" } as never;
      throw new ApiError("You do not have access to IT accounts", 403);
    });
    const tree = await ItAccountsPage({ shell: "it", searchParams: Promise.resolve({}) });
    expect(elements(tree).some((el) => el.type === PortalShell)).toBe(false);
  });
});
