import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { redirect } from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminCounselorReportPage from "@/app/overseas/admin/counselor-performance/[id]/page";
import AdminCounselorPerformancePage from "@/app/overseas/admin/counselor-performance/page";
import CounselorReportsPage from "@/app/overseas/counselor/reports/page";
import CounselorPerformance from "@/components/CounselorPerformance";
import CounselorTeamPerformance from "@/components/CounselorTeamPerformance";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { performanceQuery, type CounselorPerformanceReport, type TeamPerformance, type TeamRow } from "@/lib/counselorPerformance";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/overseas/admin/counselor-performance" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const ID = "11111111-2222-3333-4444-555555555555";
const QUERY = { from: "2026-05-01", to: "2026-05-31", intake: "Sep 2027", division: "" };
const admin = { id: "a1", full_name: "Olu Admin", role: "overseas_admin", division: "overseas" } as User;
const counselor = { id: "c1", full_name: "Asha Rao", role: "counselor", division: "overseas" } as User;

const figures = { leads: 3, leads_overseas: 2, leads_it: 1, leads_assigned: 4, calls: 1250, counseling_sessions: 2, conversions: 1, conversion_pct: 25,
  students: 2, applications: 3, visas_pending: 0, visas_approved: 1, visas_refused: 0, enrollments: 0 }; // prettier-ignore
const row = (over: Partial<TeamRow> = {}): TeamRow => ({ id: ID, full_name: "Asha Rao", active: true, ...figures, ...over });
const COLUMNS = [["full_name", "Counselor"], ["leads", "Leads"], ["leads_overseas", "Overseas leads"], ["leads_it", "IT leads"], ["conversion_pct", "Conversion %"], ["visas_approved", "Visas approved"]] as const;

function team(over: Partial<TeamPerformance> = {}): TeamPerformance {
  return {
    from: "2026-05-01", to: "2026-05-31", as_of: "2026-05-20T05:00:00Z", intake: "Sep 2027", division: null,
    columns: COLUMNS.map(([key, label]) => ({ key, label, definition: `D:${key}` })),
    items: [row(), row({ id: "99999999-2222-3333-4444-555555555555", full_name: "Ben Old", active: false, ...{ leads: 0, leads_overseas: 0, leads_it: 0, conversion_pct: null } })],
    totals: { full_name: "Total", ...figures, leads: 3, calls: 1250 },
    ...over,
  }; // prettier-ignore
}

function report(over: Partial<CounselorPerformanceReport> = {}): CounselorPerformanceReport {
  return {
    from: "2026-05-01", to: "2026-05-31", as_of: "2026-05-20T05:00:00Z", intake: "Sep 2027", division: "it",
    period: [{ key: "leads", label: "Leads", definition: "D", unit: "count", value: 2 }], now: [],
    applications: { rows: [], total: { applications: 0, students: 0 }, definitions: [] },
    ...over,
  }; // prettier-ignore
}

describe("ccrm-053 performance filters", () => {
  afterEach(cleanup);

  it("reads the intake and division from the address, dropping a repeated value", () => {
    expect(performanceQuery({ from: "2026-05-01", to: "2026-05-31", intake: " Sep 2027 ", division: "it" })).toEqual({ ...QUERY, division: "it" });
    expect(performanceQuery({ intake: ["Sep 2027", "Jan 2028"] })).toEqual({ from: "", to: "", intake: "", division: "" });
  });

  it("shows the intake picker and the lead division in the counselor's form, sending the chosen intake", () => {
    render(<CounselorPerformance data={report()} error="" query={{ ...QUERY, division: "it" }} />);
    const form = screen.getByRole("form", { name: "Choose a period" });
    expect(within(form).getByLabelText("Intake month")).toHaveValue("Sep");
    expect(within(form).getByLabelText("Intake year")).toHaveValue("2027");
    expect(form.querySelector('input[type="hidden"][name="intake"]')).toHaveValue("Sep 2027");
    expect(within(form).getByLabelText("Lead division")).toHaveValue("it");
    fireEvent.change(within(form).getByLabelText("Intake month"), { target: { value: "Jan" } });
    expect(form.querySelector('input[type="hidden"][name="intake"]')).toHaveValue("Jan 2027");
    expect(screen.getByText(/Leads for the Sep 2027 intake in the IT division only\./)).toBeInTheDocument();
    expect(screen.getByText(/Applications for the Sep 2027 intake only\./)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("No applications are assigned to you for the Sep 2027 intake yet.");
  });

  it("the counselor's page asks the API with the filters and drops empty ones from the address", async () => {
    vi.mocked(serverApi).mockReset();
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? counselor : report()) as never);
    await CounselorReportsPage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31", intake: "Sep 2027", division: "it" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/counselor/performance?from=2026-05-01&to=2026-05-31&intake=Sep+2027&division=it");
    vi.mocked(redirect).mockClear();
    await CounselorReportsPage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31", intake: "", division: "" }) });
    expect(redirect).toHaveBeenCalledWith("/overseas/counselor/reports?from=2026-05-01&to=2026-05-31");
  });
});

describe("ccrm-053 CounselorTeamPerformance", () => {
  afterEach(cleanup);

  it("lists each counselor with a link to their report under the same filters, and the Total row", () => {
    render(<CounselorTeamPerformance data={team()} error="" query={QUERY} />);
    const region = screen.getByRole("region", { name: "Overseas counselors" });
    const headers = within(region).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Counselor", "Leads", "Overseas leads", "IT leads", "Conversion %", "Visas approved"]);
    const link = within(region).getByRole("link", { name: "Asha Rao" });
    expect(link).toHaveAttribute("href", `/overseas/admin/counselor-performance/${ID}?from=2026-05-01&to=2026-05-31&intake=Sep+2027`);
    expect(link.closest("tr")).toHaveTextContent("25.0%");
    const old = within(region).getByRole("link", { name: "Ben Old" }).closest("tr")!;
    expect(old).toHaveTextContent("(inactive)");
    expect(old).toHaveTextContent("—");
    expect(within(region).getByRole("rowheader", { name: "Total" }).closest("tr")).toHaveTextContent("3");
    expect(screen.getByText("D:leads_it")).toBeInTheDocument();
    expect(screen.getByText(/Leads and applications for the Sep 2027 intake\./)).toBeInTheDocument();
    const exports = screen.getByRole("group", { name: "Export counselor performance" });
    expect(within(exports).getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
    expect(screen.queryByText(/revenue/i)).toBeNull();
  });

  it("says so when there are no overseas counselors, and keeps the form with an error", () => {
    render(<CounselorTeamPerformance data={team({ items: [] })} error="" query={QUERY} />);
    expect(screen.getByRole("status")).toHaveTextContent("No overseas counselors yet.");
    expect(screen.queryByRole("group", { name: "Export counselor performance" })).toBeNull();
    cleanup();
    render(<CounselorTeamPerformance data={null} error="Choose the intake month and year, like Sep 2027" query={QUERY} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Choose the intake month and year");
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("href", "/overseas/admin/counselor-performance");
  });
});

describe("ccrm-053 Overseas Admin pages", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(user: User, result: unknown) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const value = path === "/api/v1/auth/me" ? user : result;
      if (value instanceof Error) throw value;
      return value as never;
    });
  }

  it("the list page reads the filters, renders in the admin sidebar, and lists the nav entry", async () => {
    answer(admin, team());
    const tree = await AdminCounselorPerformancePage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31", intake: "Sep 2027" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/overseas-admin/counselor-performance?from=2026-05-01&to=2026-05-31&intake=Sep+2027");
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toBe(PORTAL_NAV["overseas/admin"]);
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "Counselor performance", href: "/overseas/admin/counselor-performance" });
    render(tree);
    expect(screen.getByRole("heading", { name: "Counselor performance", level: 2 })).toBeInTheDocument();
  });

  it("refuses a counselor without asking for the figures, and shows a 422's own message", async () => {
    answer(counselor, team());
    render(await AdminCounselorPerformancePage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(serverApi).toHaveBeenCalledTimes(1);
    cleanup();
    answer(admin, new ApiError("Choose the intake month and year, like Sep 2027", 422));
    render(await AdminCounselorPerformancePage({ searchParams: Promise.resolve({ intake: "Sep" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose the intake month and year, like Sep 2027");
  });

  it("the detail page shows that counselor's report, its form submitting to itself", async () => {
    answer(admin, report({ counselor: { id: ID, full_name: "Asha Rao", active: false } }));
    render(await AdminCounselorReportPage({ params: Promise.resolve({ id: ID }), searchParams: Promise.resolve({ intake: "Sep 2027" }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/overseas-admin/counselor-performance/${ID}?intake=Sep+2027`);
    expect(screen.getByRole("heading", { name: "Asha Rao (inactive)", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Choose a period" })).toHaveAttribute("action", `/overseas/admin/counselor-performance/${ID}`);
    expect(screen.getByRole("link", { name: "Back to all counselors" })).toHaveAttribute("href", "/overseas/admin/counselor-performance?intake=Sep+2027");
    expect(screen.getByRole("status")).toHaveTextContent("No applications are assigned to Asha Rao for the Sep 2027 intake yet.");
  });

  it("the detail page says a missing counselor in words, without asking for a malformed id", async () => {
    answer(admin, new ApiError("Counselor not found", 404));
    render(await AdminCounselorReportPage({ params: Promise.resolve({ id: ID }), searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("This counselor was not found.");
    cleanup();
    vi.mocked(serverApi).mockClear();
    render(await AdminCounselorReportPage({ params: Promise.resolve({ id: "not-an-id" }), searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("This counselor was not found.");
    expect(serverApi).toHaveBeenCalledTimes(1);
  });
});
