import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItReportsPage from "@/components/ItReportsPage";
import ItReportsWorkspace from "@/components/ItReportsWorkspace";
import { ApiError, serverApi } from "@/lib/api";
import { itReport, itReportExportUrl, itReportHref, itReportParams, itReportUrl, type ItReportPage } from "@/lib/itReports";
import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/it-reports",
  useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

afterEach(cleanup);

const BASE = "/management/it-reports";
const TABS = [
  { key: "funnel" as const, label: "Lead funnel" }, { key: "conversions" as const, label: "Conversions" }, { key: "revenue" as const, label: "Revenue & outstanding" },
  { key: "training" as const, label: "Attendance & completion" }, { key: "placement" as const, label: "Placement outcomes" }, { key: "activity" as const, label: "Team activity" },
];
const OPTIONS = {
  courses: [{ id: "c1", title: "Java Full Stack" }, { id: "c2", title: "Python" }],
  batches: [{ id: "b1", name: "Java Oct", program_id: "c1" }, { id: "b2", name: "Python Nov", program_id: "c2" }],
  owners: [{ id: "o1", name: "Meera (counselor)" }],
  statuses: [{ value: "new", label: "New Lead" }, { value: "converted", label: "Converted" }],
};
const FILTERS = { program_id: null, batch_id: null, owner_id: null, date_from: "2026-10-01", date_to: "2026-10-31", status: null };
const funnel = (over: Partial<ItReportPage> = {}): ItReportPage => ({
  report: "funnel",
  totals: { leads: 3, open: 1, nurture: 0, converted: 1, closed: 1, by_stage: [{ stage: "new", label: "New Lead", count: 1 }, { stage: "converted", label: "Converted", count: 1 }, { stage: "lost", label: "Lost", count: 1 }] },
  groups: [{ program_id: "c1", course: "Java Full Stack", source: "Instagram", leads: 3, open: 1, nurture: 0, converted: 1, closed: 1 }],
  items: [{ lead_code: "LD-1", course: "Java Full Stack", source: "Instagram", owner: "Meera", stage: "Converted", created_on: "2026-10-03", converted_on: "2026-10-09" }],
  total: 3, limit: 50, offset: 0, filters: FILTERS as never, options: OPTIONS,
  definitions: [{ key: "leads", label: "Leads", definition: "IT leads created in the period." }], ...over,
});

describe("itReports helpers (itc-032)", () => {
  it("keeps the five filters, builds the API and export addresses and picks an allowed report", () => {
    const params = itReportParams({ program_id: "c1", owner_id: "o1", status: "new", date_from: "2026-10-01", offset: "50", junk: "x" });
    expect(params).toEqual({ program_id: "c1", owner_id: "o1", status: "new", date_from: "2026-10-01", offset: 50 });
    expect(itReportUrl("funnel", params)).toBe("/api/v1/management/it/reports/funnel?limit=50&offset=50&program_id=c1&owner_id=o1&date_from=2026-10-01&status=new");
    expect(itReportExportUrl("funnel", params)).toBe("/api/v1/management/it/reports/funnel/export?program_id=c1&owner_id=o1&date_from=2026-10-01&status=new");
    expect(itReport("activity", ["revenue"])).toBe("revenue");  // the accountant asks for a tab they may not open: their first
    expect(itReport("training", ["funnel", "training"])).toBe("training");
    expect(itReportParams({ offset: "-3" })).toEqual({});
  });

  it("carries course, batch, owner and dates across tabs, and the status only within its family", () => {
    const params = { program_id: "c1", owner_id: "o1", status: "new", offset: 50 };
    expect(itReportHref(BASE, "conversions", params, "funnel")).toBe(`${BASE}?report=conversions&program_id=c1&owner_id=o1&status=new`);
    expect(itReportHref(BASE, "revenue", params, "funnel")).toBe(`${BASE}?report=revenue&program_id=c1&owner_id=o1`);
    expect(itReportHref(BASE, "funnel", params, "funnel", 100)).toBe(`${BASE}?report=funnel&program_id=c1&owner_id=o1&status=new&offset=100`);
  });

  it("is reachable from the management, IT Admin and super admin navigation", () => {
    const hrefs = MANAGEMENT_PILLARS.flatMap((p) => p.entries.map((e) => e.href));
    expect(hrefs).toContain("/management/it-reports");
    const finance = managementNavFor({ operational: false, finance: true, partner_only: false }).map((i) => i.href);
    expect(finance.filter((h) => h === "/management/it-reports")).toHaveLength(1);  // the accountant: their Revenue tab
    const partner = managementNavFor({ operational: true, finance: true, partner_only: true }).map((i) => i.href);
    expect(partner.filter((h) => h === "/management/it-reports")).toHaveLength(1);  // once, from the pillar
    expect(PORTAL_NAV["it/admin"].some((i) => i.href === "/it/admin/management-reports")).toBe(true);
    expect(SUPER_ADMIN_NAV.some((i) => i.href === "/management/it-reports")).toBe(true);
  });
});

describe("ItReportsWorkspace (itc-032)", () => {
  it("shows the tabs, the five filters, the totals, the definitions, the groups with a drill-down link and the rows", () => {
    render(<ItReportsWorkspace report="funnel" tabs={TABS} page={funnel()} error="" params={{}} basePath={BASE} />);
    const tabs = within(screen.getByRole("navigation", { name: "IT reports" })).getAllByRole("link");
    expect(tabs.map((t) => t.textContent)).toEqual(TABS.map((t) => t.label));
    expect(tabs[0]).toHaveAttribute("aria-current", "page");
    for (const label of ["Course", "Batch", "Owner", "Status", "From", "To"]) expect(screen.getByLabelText(label)).toBeInTheDocument();
    const totals = within(screen.getByLabelText("Lead funnel totals"));
    expect(totals.getByText("Leads").nextSibling).toHaveTextContent("3");
    expect(screen.getByText("What these figures mean")).toBeInTheDocument();
    expect(screen.getByText("IT leads created in the period.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Show rows for Java Full Stack/ })).toHaveAttribute("href", `${BASE}?report=funnel&program_id=c1`);
    expect(screen.getByRole("region", { name: "Leads by stage" })).toBeInTheDocument();
    expect(screen.getByText("LD-1")).toBeInTheDocument();
    expect(screen.getByText("03 Oct 2026")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
  });

  it("drills activity down by staff member and offers only a course's batches once applied", () => {
    const page = funnel({
      report: "activity", totals: { events: 2, calls: 2, connected_calls: 1, follow_ups: 0, conversions: 0 },
      groups: [{ owner_id: "o1", staff: "Meera", calls: 2, connected_calls: 1, follow_ups: 0, conversions: 0 }],
      items: [{ at: "2026-10-04 10:00", kind: "Call", connected: "Yes", staff: "Meera", lead_code: "LD-1", course: "Java Full Stack", stage: "Contacted" }], total: 1,
    });
    render(<ItReportsWorkspace report="activity" tabs={TABS} page={page} error="" params={{ program_id: "c1" }} basePath={BASE} />);
    expect(screen.getByRole("link", { name: /Show rows for Meera/ })).toHaveAttribute("href", `${BASE}?report=activity&program_id=c1&owner_id=o1`);
    expect(screen.getByLabelText("Staff member")).toBeInTheDocument();
    const batch = screen.getByLabelText("Batch");
    expect(within(batch).getAllByRole("option").map((o) => o.textContent)).toEqual(["All batches", "Java Oct"]);
  });

  it("says when nothing matches, and shows a refusal above the form", () => {
    render(<ItReportsWorkspace report="revenue" tabs={TABS} page={null} error="Choose a status from the list" params={{ status: "qualified" }} basePath={BASE} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a status from the list");
    expect(within(screen.getByLabelText("Status")).getByRole("option", { name: "qualified" })).toBeInTheDocument();
    cleanup();
    render(<ItReportsWorkspace report="funnel" tabs={TABS} page={funnel({ items: [], groups: [], total: 0 })} error="" params={{}} basePath={BASE} />);
    expect(screen.getByRole("status")).toHaveTextContent("Nothing matches these filters.");
  });
});

describe("ItReportsPage (itc-032)", () => {
  const api = vi.mocked(serverApi);

  it("opens the accountant's only report and shows a 422 above the form", async () => {
    api.mockReset();
    api.mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return { id: "u1", role: "accountant", full_name: "Asha" } as never;
      if (path === "/api/v1/management/me") return { id: "u1", role: "accountant", full_name: "Asha", tiers: { operational: false, finance: true, partner_only: false } } as never;
      if (path === "/api/v1/management/it/reports") return { reports: [{ key: "revenue", label: "Revenue & outstanding" }] } as never;
      throw new ApiError("Choose a status from the list", 422);
    });
    render(await ItReportsPage({ shell: "management", searchParams: Promise.resolve({ report: "funnel", status: "x" }) }));
    expect(api).toHaveBeenCalledWith("/api/v1/management/it/reports/revenue?limit=50&offset=0&status=x");
    expect(within(screen.getByRole("navigation", { name: "IT reports" })).getAllByRole("link")).toHaveLength(1);
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a status from the list");
  });
});
