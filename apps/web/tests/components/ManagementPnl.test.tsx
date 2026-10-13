import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PnlPage from "@/app/management/pnl/page";
import ManagementPnl from "@/components/ManagementPnl";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { Pnl, PnlQuery } from "@/lib/managementPnl";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/pnl" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Asha Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const QUERY: PnlQuery = { month: "2026-05", period: "month" };
const ZERO = { revenue: "0.00", expenses: "0.00", contribution: "0.00", margin: null };

function pnl(overrides: Partial<Pnl> = {}): Pnl {
  return {
    month: "2026-05", period: "month", start: "2026-05-01", end: "2026-05-31", label: "May 2026", commission_visible: true,
    rows: [
      { key: "abroad", label: "Abroad Education", revenue: "400000.00", expenses: "100000.00", contribution: "300000.00", margin: 75 },
      { key: "it", label: "IT Training", revenue: "200000.00", expenses: "50000.00", contribution: "150000.00", margin: 75 },
      { key: "recruitment", label: "Recruitment", revenue: "50000.00", expenses: "60000.00", contribution: "-10000.00", margin: -20 },
      { key: "school", label: "School projects", ...ZERO },
      { key: "other", label: "Other", ...ZERO },
      { key: "shared", label: "Shared (company-wide, not allocated)", revenue: "0.00", expenses: "240000.00", contribution: "-240000.00", margin: null },
    ],
    total: { revenue: "650000.00", expenses: "450000.00", contribution: "200000.00", margin: 30.8 },
    not_counted: [],
    ...overrides,
  }; // prettier-ignore
}

function view(props: Partial<Parameters<typeof ManagementPnl>[0]> = {}) {
  return render(<ManagementPnl data={pnl()} error="" query={QUERY} maxMonth="2026-10" {...props} />);
}

describe("mgmt-009 ManagementPnl", () => {
  afterEach(cleanup);

  it("shows the four headline figures and one row per vertical, the shared row and the total", () => {
    view();
    const tiles = screen.getByRole("list", { name: "Company figures" });
    expect(tiles).toHaveTextContent("₹6,50,000.00");
    expect(tiles).toHaveTextContent("₹4,50,000.00");
    expect(tiles).toHaveTextContent("₹2,00,000.00");
    expect(tiles).toHaveTextContent("30.8%");
    const table = screen.getByRole("table", { name: "Profit and loss by business vertical" });
    expect(within(table).getAllByRole("rowheader").map((th) => th.textContent)).toEqual([
      "Abroad Education", "IT Training", "Recruitment", "School projects", "Other", "Shared (company-wide, not allocated)", "Total",
    ]); // prettier-ignore
    expect(within(table).getByRole("row", { name: /^IT Training/ })).toHaveTextContent("₹1,50,000.00");
    expect(within(table).getByRole("row", { name: /^Total/ })).toHaveTextContent("₹6,50,000.00");
    expect(within(table).getByRole("row", { name: /^School projects/ })).toHaveTextContent("—");
  });

  it("shows a negative contribution in red with its minus sign, a profit not", () => {
    view();
    const table = screen.getByRole("table", { name: "Profit and loss by business vertical" });
    const loss = within(within(table).getByRole("row", { name: /^Recruitment/ })).getByText("-₹10,000.00");
    expect(loss).toHaveClass("pnl-loss");
    expect(within(within(table).getByRole("row", { name: /^Abroad Education/ })).getByText("₹3,00,000.00")).not.toHaveClass("pnl-loss");
    expect(within(screen.getByRole("list", { name: "Company figures" })).getByText("₹2,00,000.00")).not.toHaveClass("pnl-loss");
  });

  it("QA-01: shows the net profit as the tile's own figure, red when it is a loss", () => {
    view({ data: pnl({ total: { revenue: "100.00", expenses: "250.00", contribution: "-150.00", margin: -150 } }) });
    const figure = within(screen.getByRole("list", { name: "Company figures" })).getByText("-₹150.00");
    expect(figure.tagName).toBe("STRONG"); // a <span> inside the tile would take `.metric span`'s small caption style
    expect(figure).toHaveClass("pnl-loss");
  });

  it("keeps the month and period in a GET form with the quarter choice", () => {
    view({ data: pnl({ period: "quarter", label: "Q1 (April–June) of 2026-27 to date", start: "2026-04-01" }), query: { month: "2026-05", period: "quarter" } });
    const form = screen.getByRole("form", { name: "Choose a period" });
    expect(form).toHaveAttribute("action", "/management/pnl");
    expect(within(form).getByLabelText("Month", { exact: true })).toHaveValue("2026-05");
    expect(within(form).getByLabelText("Show")).toHaveValue("quarter");
    expect(within(form).getAllByRole("option").map((o) => o.textContent)).toEqual(["That month", "Quarter to date", "Financial year to date"]);
    expect(screen.getByText(/Q1 \(April–June\) of 2026-27 to date/)).toBeInTheDocument();
  });

  it("explains the shared row and the accountant's missing university commission", () => {
    view({ data: pnl({ commission_visible: false }) });
    expect(screen.getByText(/not split across the verticals/)).toBeInTheDocument();
    expect(screen.getByText(/University commission is not included/)).toBeInTheDocument();
    cleanup();
    view();
    expect(screen.queryByText(/University commission is not included/)).toBeNull();
  });

  it("says when nothing was recorded, notes other currencies, and shows an error", () => {
    view({ data: pnl({ rows: pnl().rows.map((r) => ({ ...r, ...ZERO })), total: ZERO, not_counted: [{ currency: "USD", kind: "income", amount: "700.00", count: 1 }] }) });
    expect(screen.getByRole("status")).toHaveTextContent("No revenue or expenses recorded in May 2026.");
    expect(screen.getByText(/in another currency are not counted: (US)?\$700.00 income \(1 line\)/)).toBeInTheDocument();
    cleanup();
    view({ data: null, error: "Choose this month or an earlier one" });
    expect(screen.getByRole("alert")).toHaveTextContent("Choose this month or an earlier one");
    expect(screen.getByRole("form", { name: "Choose a period" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("mgmt-009 P&L page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(figures: Pnl | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const result = path === "/api/v1/management/me" ? partner : path.startsWith("/api/v1/management/pnl") ? figures : (null as never);
      if (result instanceof Error) throw result;
      return result as never;
    });
  }

  it("asks for the period in the address and renders the P&L", async () => {
    answer(pnl());
    render(await PnlPage({ searchParams: Promise.resolve({ month: "2026-05", period: "year" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/pnl?month=2026-05&period=year");
    expect(screen.getByRole("heading", { name: "Profit & loss" })).toBeInTheDocument();
  });

  it("shows the API's 422 message, or a generic one for anything else", async () => {
    answer(new ApiError("Choose this month or an earlier one", 422));
    render(await PnlPage({ searchParams: Promise.resolve({ month: "2099-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose this month or an earlier one");
    cleanup();
    answer(new Error("boom"));
    render(await PnlPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Profit & loss is unavailable right now. Please try again.");
  });

  it("shows the access card when the API refuses the caller", async () => {
    answer(new ApiError("Finance access required", 403));
    render(await PnlPage({ searchParams: Promise.resolve({}) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/pnl");
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Finance access required")).toBeTruthy();
  });

  it("puts the page in the management shell with the caller's sidebar", async () => {
    answer(pnl());
    const shell = elements(await PnlPage({ searchParams: Promise.resolve({}) })).find((el) => el.type === PortalShell)!;
    expect(shell.props.roleLabel).toBe("Partner");
    expect(shell.props.nav).toContainEqual({ label: "Profit & loss", href: "/management/pnl" });
  });
});
