import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruitmentDashboardPage from "@/app/recruiter/recruitment-dashboards/[board]/page";
import RecruitmentDashboard from "@/components/RecruitmentDashboard";
import { ApiError, serverApi } from "@/lib/api";
import { managementNavFor } from "@/lib/management";
import { PORTAL_NAV, RECRUITER_MANAGER_NAV, RECRUITER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { boardUrl, dashboardQuery, drillUrl, exportUrl, pageHref, type Board, type DashboardQuery, type Drill } from "@/lib/recruitmentDashboards";

const redirect = vi.hoisted(() => vi.fn());
const notFound = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect, notFound, usePathname: () => "/recruiter/recruitment-dashboards/vacancy", useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const EMPLOYER = "11111111-1111-1111-1111-111111111111";
const QUERY: DashboardQuery = { from: "", to: "", owner: "", employer: "", job: "", drill: "", offset: 0 };
const VACANCY: Board = {
  board: "vacancy", label: "Vacancy dashboard", note: "Vacancies as they stand now.", owner_label: "Requirement owner", date_from: null, date_to: null, can_download: true,
  filters: { owner: null, employer: null, job: null },
  sections: [
    { key: "status", label: "Status", figures: [{ key: "open", label: "Open", definition: "Open vacancies.", value: 7 }, { key: "closed", label: "Closed", definition: "Closed.", value: 0 }] },
    { key: "ageing", label: "Open vacancies by age", figures: [{ key: "age_0_15", label: "0–15 days", definition: "Young.", value: 7 }] },
  ],
  options: { owners: [{ id: "o1", label: "Rita Recruiter" }], employers: [{ id: EMPLOYER, label: "Acme" }], jobs: [{ id: "j1", label: "REQ-000001 — Java" }] },
}; // prettier-ignore
const FUNNEL: Board = {
  ...VACANCY, board: "funnel", label: "Recruitment funnel", date_from: "2026-11-01", date_to: "2026-11-06",
  sections: [{ key: "stages", label: "Stages", figures: [{ key: "registered", label: "Registered", definition: "Registered in the period.", value: 10 }, { key: "applied", label: "Applied", definition: "With an application.", value: 5 }] }],
}; // prettier-ignore
const DRILL: Drill = {
  figure: { key: "open", label: "Open", definition: "Open vacancies." }, total: 30, limit: 25, offset: 0,
  columns: [{ key: "requirement", label: "Requirement", type: "text" }, { key: "opened_on", label: "Opened on", type: "date" }, { key: "age_days", label: "Age (days)", type: "number" }],
  items: [{ id: "r1", href: "/recruiter/requirements/r1", requirement: "REQ-000001", opened_on: "2026-10-01", age_days: 36 }, { id: "r2", href: null, requirement: "REQ-000002", opened_on: null, age_days: 0 }],
}; // prettier-ignore

afterEach(cleanup);

describe("the address rules", () => {
  it("keeps only well-formed values and drops the rest", () => {
    expect(dashboardQuery({ from: "2026-13-40", to: "2026-11-06", owner: "x' OR 1=1", employer: EMPLOYER, job: ["a", "b"], drill: "open", offset: "50" })).toEqual({
      ...QUERY, to: "2026-11-06", employer: EMPLOYER, drill: "open", offset: 50,
    }); // prettier-ignore
    expect(dashboardQuery({ drill: "<script>", offset: "-5" })).toEqual(QUERY);
  });

  it("builds the board, drill, export and page addresses with only what is set", () => {
    const q = { ...QUERY, from: "2026-11-01", employer: EMPLOYER };
    expect(boardUrl("vacancy", q)).toBe(`/api/v1/recruiter/recruitment-dashboards/vacancy?from=2026-11-01&employer=${EMPLOYER}`);
    expect(drillUrl("vacancy", { ...q, drill: "open", offset: 25 })).toBe(`/api/v1/recruiter/recruitment-dashboards/vacancy/drill/open?from=2026-11-01&employer=${EMPLOYER}&limit=25&offset=25`);
    expect(exportUrl("vacancy", q)).toBe(`/api/v1/recruiter/recruitment-dashboards/vacancy.csv?from=2026-11-01&employer=${EMPLOYER}`);
    expect(pageHref("funnel", { ...q, drill: "applied" })).toBe(`/recruiter/recruitment-dashboards/funnel?from=2026-11-01&employer=${EMPLOYER}&drill=applied#records`);
    expect(pageHref("funnel", QUERY)).toBe("/recruiter/recruitment-dashboards/funnel");
  });
});

describe("the dashboard", () => {
  it("shows each figure with its definition, as a link to its records keeping the filters", () => {
    render(<RecruitmentDashboard board="vacancy" data={VACANCY} drill={null} error="" query={{ ...QUERY, employer: EMPLOYER }} />);
    const open = screen.getByRole("link", { name: /Open: 7/ });
    expect(open.getAttribute("href")).toBe(`/recruiter/recruitment-dashboards/vacancy?employer=${EMPLOYER}&drill=open#records`);
    expect(screen.getByText("Open vacancies.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Open vacancies by age" })).toBeTruthy();
  });

  it("marks the current board among all five", () => {
    render(<RecruitmentDashboard board="vacancy" data={VACANCY} drill={null} error="" query={QUERY} />);
    const nav = within(screen.getByRole("navigation", { name: "Recruitment dashboards" }));
    expect(nav.getAllByRole("link").map((a) => a.textContent)).toEqual(["Funnel", "Vacancy", "Recruiter", "Placement officer", "Interview"]);
    expect(nav.getByRole("link", { name: "Vacancy" }).getAttribute("aria-current")).toBe("page");
    expect(nav.getByRole("link", { name: "Funnel" }).getAttribute("aria-current")).toBeNull();
  });

  it("offers the scoped filters, keeps the chosen values and says why branch cannot be used", () => {
    render(<RecruitmentDashboard board="vacancy" data={VACANCY} drill={null} error="" query={{ ...QUERY, employer: EMPLOYER }} />);
    expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "Employer" }).value).toBe(EMPLOYER);
    expect(screen.getByRole("combobox", { name: "Requirement owner" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Job" })).toBeTruthy();
    expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "Branch" }).disabled).toBe(true);
    expect(screen.getByText(/Branch is not recorded/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Clear filters" }).getAttribute("href")).toBe("/recruiter/recruitment-dashboards/vacancy");
  });

  it("shows a funnel as an ordered list of stages", () => {
    render(<RecruitmentDashboard board="funnel" data={FUNNEL} drill={null} error="" query={QUERY} />);
    expect(within(screen.getByRole("list", { name: "Stages" })).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /Registered: 10/ })).toBeTruthy();
  });

  it("says so when no figure has anything", () => {
    const empty = { ...VACANCY, sections: VACANCY.sections.map((s) => ({ ...s, figures: s.figures.map((f) => ({ ...f, value: 0 })) })) };
    render(<RecruitmentDashboard board="vacancy" data={empty} drill={null} error="" query={QUERY} />);
    expect(screen.getByRole("status").textContent).toMatch(/Nothing to show/);
  });

  it("shows the download only for the download grant", () => {
    const { unmount } = render(<RecruitmentDashboard board="vacancy" data={VACANCY} drill={null} error="" query={QUERY} />);
    expect(screen.getByRole("group", { name: "Export Vacancy dashboard" })).toBeTruthy();
    unmount();
    render(<RecruitmentDashboard board="vacancy" data={{ ...VACANCY, can_download: false }} drill={null} error="" query={QUERY} />);
    expect(screen.queryByRole("group", { name: "Export Vacancy dashboard" })).toBeNull();
  });

  it("shows the error in place of the figures and keeps the form", () => {
    render(<RecruitmentDashboard board="vacancy" data={null} drill={null} error="The range can't end in the future" query={{ ...QUERY, to: "2099-01-01" }} />);
    expect(screen.getByRole("alert").textContent).toContain("can't end in the future");
    expect(screen.getByLabelText<HTMLInputElement>("To").value).toBe("2099-01-01");
  });
});

describe("the records behind a figure", () => {
  const rendered = (query: DashboardQuery = { ...QUERY, drill: "open" }, drill: Drill = DRILL) =>
    render(<RecruitmentDashboard board="vacancy" data={VACANCY} drill={drill} error="" query={query} />);

  it("states the total, links a row only when it can be opened and shows a blank date as a dash", () => {
    rendered();
    expect(screen.getByRole("heading", { name: "Open: 30 records" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "REQ-000001" }).getAttribute("href")).toBe("/recruiter/requirements/r1");
    expect(screen.queryByRole("link", { name: "REQ-000002" })).toBeNull();
    const second = screen.getAllByRole("row")[2];
    expect(within(second).getByText("—")).toBeTruthy();
    expect(within(second).getByText("0")).toBeTruthy();
  });

  it("pages forward and back, and closes", () => {
    rendered({ ...QUERY, drill: "open", offset: 25 }, { ...DRILL, total: 27, offset: 25 });
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).toContain("drill=open");
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).not.toContain("offset");
    expect(screen.queryByRole("link", { name: "Next page" })).toBeNull();
    expect(screen.getByRole("link", { name: "Close records" }).getAttribute("href")).toBe("/recruiter/recruitment-dashboards/vacancy");
  });

  it("has a next page while more remain, and an empty figure says so", () => {
    const { unmount } = rendered();
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toContain("offset=25");
    unmount();
    rendered(undefined, { ...DRILL, total: 0, items: [] });
    expect(screen.getByText("No records for this figure.")).toBeTruthy();
  });
});

describe("the page", () => {
  const user = { id: "u1", full_name: "Hema HR", role: "hr_manager" };
  const respond = (routes: Record<string, unknown>) =>
    vi.mocked(serverApi).mockImplementation(async (url: string) => {
      for (const [prefix, value] of Object.entries(routes)) {
        if (url.startsWith(prefix)) {
          if (value instanceof Error) throw value;
          return value;
        }
      }
      throw new Error(`unexpected ${url}`);
    });
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
    redirect.mockReset();
    notFound.mockReset();
  });

  it("reads the board and, with a figure, its records", async () => {
    respond({ "/api/v1/auth/me": user, "/api/v1/recruiter/recruitment-dashboards/vacancy/drill/open": DRILL, "/api/v1/recruiter/recruitment-dashboards/vacancy": VACANCY });
    render(await RecruitmentDashboardPage({ params: Promise.resolve({ board: "vacancy" }), searchParams: Promise.resolve({ drill: "open" }) }));
    expect(screen.getByRole("heading", { name: "Vacancy dashboard" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Open: 30 records" })).toBeTruthy();
  });

  it("drops the empty values a GET form sends", async () => {
    respond({ "/api/v1/auth/me": user, "/api/v1/recruiter/recruitment-dashboards/vacancy": VACANCY });
    redirect.mockImplementation(() => {
      throw new Error("NEXT_REDIRECT");
    });
    await expect(RecruitmentDashboardPage({ params: Promise.resolve({ board: "vacancy" }), searchParams: Promise.resolve({ owner: "", employer: EMPLOYER }) })).rejects.toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenCalledWith(`/recruiter/recruitment-dashboards/vacancy?employer=${EMPLOYER}`);
  });

  it("treats an unknown board as not found", async () => {
    notFound.mockImplementation(() => {
      throw new Error("NEXT_NOT_FOUND");
    });
    await expect(RecruitmentDashboardPage({ params: Promise.resolve({ board: "nonsense" }), searchParams: Promise.resolve({}) })).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("shows a role with no grant the access card, not the dashboard", async () => {
    respond({ "/api/v1/auth/me": { ...user, role: "bdm" }, "/api/v1/recruiter/recruitment-dashboards": new ApiError("Your role has no recruitment dashboards", 403) });
    render(await RecruitmentDashboardPage({ params: Promise.resolve({ board: "vacancy" }), searchParams: Promise.resolve({}) }));
    expect(screen.getByText("Your role has no recruitment dashboards")).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Recruitment dashboards" })).toBeNull();
  });

  it("shows the API's words for a bad range", async () => {
    respond({ "/api/v1/auth/me": user, "/api/v1/recruiter/recruitment-dashboards": new ApiError("The range can't end in the future", 422) });
    render(await RecruitmentDashboardPage({ params: Promise.resolve({ board: "vacancy" }), searchParams: Promise.resolve({ to: "2099-01-01" }) }));
    expect(screen.getByRole("alert").textContent).toContain("can't end in the future");
  });

  it("keeps the figures when only the records fail", async () => {
    respond({ "/api/v1/auth/me": user, "/api/v1/recruiter/recruitment-dashboards/vacancy/drill": new ApiError("Figure not found", 404), "/api/v1/recruiter/recruitment-dashboards/vacancy": VACANCY });
    render(await RecruitmentDashboardPage({ params: Promise.resolve({ board: "vacancy" }), searchParams: Promise.resolve({ drill: "nope" }) }));
    expect(screen.getByRole("link", { name: /Open: 7/ })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Figure not found");
  });
});

describe("the menus", () => {
  const LINK = "/recruiter/recruitment-dashboards";
  it("lists the dashboards for the operational management tier only", () => {
    const tiers = { operational: false, finance: true, partner_only: false };
    expect(managementNavFor(tiers).some((item) => item.href === LINK)).toBe(false);
    expect(managementNavFor({ ...tiers, operational: true }).some((item) => item.href === LINK)).toBe(true);
  });
  it.each([["recruiter", RECRUITER_NAV], ["manager", RECRUITER_MANAGER_NAV], ["super admin", SUPER_ADMIN_NAV], ["HR manager", PORTAL_NAV["it/hr-manager"]], ["officer", PORTAL_NAV["it/placement-officer"]], ["IT admin", PORTAL_NAV["it/admin"]]])("lists the dashboards for the %s", (_who, nav) => {
    expect(nav.some((item) => item.href === LINK)).toBe(true);
  }); // prettier-ignore
});
