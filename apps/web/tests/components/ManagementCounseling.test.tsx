import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementCounselingPage from "@/app/management/counseling/page";
import ManagementCounseling from "@/components/ManagementCounseling";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import type { CounselingDashboard, CounselingFigures } from "@/lib/managementCounseling";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/counseling" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Priya Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Sam Admin", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const QUERY = { from: "2026-05-01", to: "2026-05-31" };

const figures = (over: Partial<CounselingFigures> = {}): CounselingFigures => ({
  leads_assigned: 0, calls: null, counseling_sessions: 0, follow_ups: 0, conversions: 0, revenue: "0.00", conversion_pct: null, ...over,
}); // prettier-ignore

function dashboard(over: Partial<CounselingDashboard> = {}): CounselingDashboard {
  const asha = { id: "c1", full_name: "Asha Rao", division: "it", active: true, ...figures({ leads_assigned: 3, counseling_sessions: 4, follow_ups: 1, conversions: 1, revenue: "150000.00", conversion_pct: 33.3 }) };
  const ben = { id: "c2", full_name: "Ben Paul", division: "overseas", active: false, ...figures({ counseling_sessions: 2 }) };
  return {
    from: "2026-05-01", to: "2026-05-31", as_of: "2026-10-13T05:00:00Z", revenue_visible: true,
    figures: [
      { key: "leads_assigned", label: "Leads assigned", definition: "Leads handed over.", tracked: true },
      { key: "calls", label: "Calls", definition: "Not tracked: calls are logged by telecallers.", tracked: false },
      { key: "counseling_sessions", label: "Counseling sessions", definition: "Completed sessions.", tracked: true },
      { key: "follow_ups", label: "Follow-ups", definition: "Repeat sessions.", tracked: true },
      { key: "conversions", label: "Conversions", definition: "Converted leads.", tracked: true },
      { key: "revenue", label: "Revenue", definition: "Rupee payments.", tracked: true },
      { key: "conversion_pct", label: "Conversion %", definition: "Share converted.", tracked: true },
    ],
    total: { division: null, label: "All counselors", counselor_count: 2, ...figures({ leads_assigned: 3, counseling_sessions: 6, follow_ups: 1, conversions: 1, revenue: "150000.00", conversion_pct: 33.3 }) },
    divisions: [
      { division: "it", label: "IT", counselor_count: 1, ...figures({ leads_assigned: 3, counseling_sessions: 4, follow_ups: 1, conversions: 1, revenue: "150000.00", conversion_pct: 33.3 }) },
      { division: "overseas", label: "Overseas", counselor_count: 1, ...figures({ counseling_sessions: 2 }) },
    ],
    counselors: [asha, ben],
    ...over,
  }; // prettier-ignore
}

function view(props: Partial<Parameters<typeof ManagementCounseling>[0]> = {}) {
  return render(<ManagementCounseling data={dashboard()} error="" query={QUERY} {...props} />);
}

const tile = (label: string) => within(screen.getByRole("list", { name: "Leads → Counseling → Conversion" })).getByText(label).closest("li")!;

describe("mgmt-018 ManagementCounseling", () => {
  afterEach(cleanup);

  it("shows the totals as the §13 KPIs in source order, with Indian grouping, rupees and one-decimal shares", () => {
    view();
    const items = within(screen.getByRole("list", { name: "Leads → Counseling → Conversion" })).getAllByRole("listitem");
    expect(items.map((li) => li.querySelector("span")!.textContent)).toEqual([
      "Leads assigned", "Calls", "Counseling sessions", "Follow-ups", "Conversions", "Revenue", "Conversion %",
    ]);
    expect(tile("Revenue")).toHaveTextContent("₹1,50,000.00");
    expect(tile("Conversion %")).toHaveTextContent("33.3%");
    expect(tile("Leads assigned")).toHaveTextContent("Leads handed over.");
  });

  it("says Not tracked for calls, never 0", () => {
    view();
    expect(within(tile("Calls")).getByText("Not tracked")).toHaveClass("metric-untracked");
    expect(tile("Calls")).not.toHaveTextContent(/\b0\b/);
  });

  it("shows the super admin that revenue is the partners', with no revenue column", () => {
    const hidden = dashboard({ revenue_visible: false });
    hidden.total.revenue = null;
    hidden.counselors = hidden.counselors.map((c) => ({ ...c, revenue: null }));
    view({ data: hidden });
    expect(within(tile("Revenue")).getByText("Partners only")).toHaveClass("metric-untracked");
    expect(screen.queryByRole("columnheader", { name: "Revenue" })).toBeNull();
  });

  it("says there were no leads to convert instead of a share", () => {
    view({ data: dashboard({ total: { ...dashboard().total, leads_assigned: 0, conversion_pct: null } }) });
    expect(within(tile("Conversion %")).getByText("No leads assigned")).toHaveClass("metric-untracked");
  });

  it("lists every counselor with their division and figures, then the division and all-counselor totals", () => {
    view();
    const table = screen.getByRole("table", { name: "Counselor-wise performance" });
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Counselor", "Division", "Leads assigned", "Counseling sessions", "Follow-ups", "Conversions", "Revenue", "Conversion %",
    ]);
    const asha = within(table).getByRole("rowheader", { name: "Asha Rao" }).closest("tr")!;
    expect(Array.from(asha.querySelectorAll("td")).map((td) => td.textContent)).toEqual(["IT", "3", "4", "1", "1", "₹1,50,000.00", "33.3%"]);
    const ben = within(table).getByRole("rowheader", { name: /Ben Paul/ }).closest("tr")!;
    expect(ben).toHaveTextContent("Inactive");
    expect(ben.querySelectorAll("td")[6]).toHaveTextContent("—");
    const footer = Array.from(table.querySelectorAll("tfoot th")).map((th) => th.textContent);
    expect(footer).toEqual(["IT total", "Overseas total", "All counselors"]);
    expect(screen.getByRole("heading", { name: "Counselor-wise performance" }).closest("section")).toHaveAttribute("id", "counselors");
  });

  it("names the period and the counselors, in a GET period form", () => {
    view();
    expect(screen.getByText(new RegExp(`^${formatCalendarDate("2026-05-01")} to ${formatCalendarDate("2026-05-31")}`))).toHaveTextContent("2 counselors");
    const form = screen.getByRole("form", { name: "Choose a period" });
    expect(form).toHaveAttribute("method", "get");
    expect(within(form).getByLabelText("From")).toHaveValue("2026-05-01");
    expect(within(form).getByLabelText("To")).toHaveValue("2026-05-31");
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("href", "/management/counseling");
  });

  it("says one counselor in the singular", () => {
    view({ data: dashboard({ total: { ...dashboard().total, counselor_count: 1 } }) });
    expect(screen.getByText(/1 counselor\./)).toBeInTheDocument();
  });

  it("says so when there are no counselors yet", () => {
    view({ data: dashboard({ counselors: [], total: { ...dashboard().total, ...figures(), counselor_count: 0 } }) });
    expect(screen.getByRole("status")).toHaveTextContent("No counselor accounts yet");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows an error without figures", () => {
    view({ data: null, error: "The period must start on or before its end" });
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    expect(screen.queryByRole("list", { name: "Leads → Counseling → Conversion" })).toBeNull();
    expect(screen.getByRole("form", { name: "Choose a period" })).toBeInTheDocument();
  });
});

describe("mgmt-018 Counseling dashboard page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(me: ManagementMe, result: CounselingDashboard | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const value = path === "/api/v1/management/me" ? me : path.startsWith("/api/v1/management/counseling") ? result : (null as never);
      if (value instanceof Error) throw value;
      return value as never;
    });
  }

  it("asks for the period in the address and renders in the Command Center sidebar", async () => {
    answer(partner, dashboard());
    const tree = await ManagementCounselingPage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/counseling?from=2026-05-01&to=2026-05-31");
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toContainEqual({ label: "Counseling", href: "/management/counseling" });
    render(tree);
    expect(screen.getByRole("heading", { name: "Counseling dashboard" })).toBeInTheDocument();
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin, dashboard());
    const tree = await ManagementCounselingPage({ searchParams: Promise.resolve({}) });
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the API's 422 message, a generic message on a server error, and the access card when refused", async () => {
    answer(partner, new ApiError("The period must start on or before its end", 422));
    render(await ManagementCounselingPage({ searchParams: Promise.resolve({ from: "2026-05-31", to: "2026-05-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    cleanup();
    answer(partner, new ApiError("Internal Server Error", 500));
    render(await ManagementCounselingPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Counseling figures are unavailable right now. Please try again.");
    cleanup();
    answer(partner, new ApiError("Operational access required", 403));
    render(await ManagementCounselingPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
  });
});
