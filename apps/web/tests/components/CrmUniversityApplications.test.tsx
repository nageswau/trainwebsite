import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminUniversityPage from "@/app/overseas/admin/crm-reports/universities/[id]/page";
import ManagementUniversityPage from "@/app/management/crm-reports/universities/[id]/page";
import CrmUniversityApplications from "@/components/CrmUniversityApplications";
import { ApiError, serverApi } from "@/lib/api";
import { ADMIN_CRM_REPORTS_HOME, CRM_REPORTS_HOME, EMPTY_CRM_FILTERS, type CrmUniversityApplications as Data } from "@/lib/managementCrmReports";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/overseas/admin/crm-reports" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const UNI = "11111111-1111-4111-8111-111111111111";
const item = (n: number, extra: Partial<Data["items"][number]> = {}) => ({
  application_id: `a${n}`, application_code: `APP-${n}`, student_name: `Student ${n}`, course: "MSc Data Science", intake: "Fall 2027",
  stage: "visa", stage_label: "Visa", counselor: "Meera", deposit_paid: true, visa: "approved" as const, ...extra,
}); // prettier-ignore
const PARTNER = { id: "p1", full_name: "Kiran", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const data = (items: Data["items"], total = items.length, page = 1): Data => ({ university: { id: UNI, label: "Leeds" }, items, total, page, page_size: 100 });

afterEach(cleanup);

describe("ccrm-052 CrmUniversityApplications", () => {
  it("lists the university's applications with a back link that keeps the filters", () => {
    const filters = { ...EMPTY_CRM_FILTERS, intake: "Fall 2027" };
    render(<CrmUniversityApplications data={data([item(1), item(2, { course: null, counselor: null, deposit_paid: false, visa: null })])} error="" filters={filters} home={ADMIN_CRM_REPORTS_HOME} />);
    expect(screen.getByRole("heading", { level: 2, name: "Leeds" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Back to CRM reports/ }).getAttribute("href")).toBe(`${ADMIN_CRM_REPORTS_HOME}?intake=Fall+2027`);
    const table = screen.getByRole("table", { name: /Applications at Leeds/ });
    expect(within(table).getAllByRole("columnheader").map((c) => c.textContent)).toEqual(["Application", "Student", "Course", "Intake", "Stage", "Counselor", "Deposit paid", "Visa"]);
    expect(within(within(table).getByRole("row", { name: /APP-1/ })).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Student 1", "MSc Data Science", "Fall 2027", "Visa", "Meera", "Yes", "Approved"]);
    expect(within(within(table).getByRole("row", { name: /APP-2/ })).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Student 2", "—", "Fall 2027", "Visa", "Not assigned", "No", "—"]);
    expect(screen.getByText(/^2 applications — /)).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Pages" })).toBeNull();
  });

  it("shows an empty state and the API's error", () => {
    const { rerender } = render(<CrmUniversityApplications data={data([])} error="" filters={EMPTY_CRM_FILTERS} home={CRM_REPORTS_HOME} />);
    expect(screen.getByRole("status").textContent).toBe("No applications at this university match these filters.");
    rerender(<CrmUniversityApplications data={null} error="That university is not in the reports." filters={EMPTY_CRM_FILTERS} home={CRM_REPORTS_HOME} />);
    expect(screen.getByRole("alert").textContent).toBe("That university is not in the reports.");
    expect(screen.getByRole("link", { name: /Back to CRM reports/ }).getAttribute("href")).toBe(CRM_REPORTS_HOME);
  });

  it("pages by 100 with links that keep the filters", () => {
    const filters = { ...EMPTY_CRM_FILTERS, intake: "Fall 2027" };
    render(<CrmUniversityApplications data={data([item(1)], 201, 2)} error="" filters={filters} home={CRM_REPORTS_HOME} />);
    const pages = screen.getByRole("navigation", { name: "Pages" });
    expect(within(pages).getByText("Page 2 of 3")).toBeTruthy();
    expect(within(pages).getByRole("link", { name: "Previous" }).getAttribute("href")).toBe(`${CRM_REPORTS_HOME}/universities/${UNI}?intake=Fall+2027`);
    expect(within(pages).getByRole("link", { name: "Next" }).getAttribute("href")).toBe(`${CRM_REPORTS_HOME}/universities/${UNI}?intake=Fall+2027&page=3`);
  });
});

describe("ccrm-052 drill-down pages", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  const props = (search: Record<string, string> = {}) => ({ params: Promise.resolve({ id: UNI }), searchParams: Promise.resolve(search) });

  it("the Overseas Admin page calls the drill-down with the filters and page", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? { role: "overseas_admin", full_name: "Asha" } : data([item(1)]))) as never;
    render(await AdminUniversityPage(props({ intake: "Fall 2027", page: "2" })));
    expect(vi.mocked(serverApi).mock.calls.map((c) => c[0])).toContain(`/api/v1/management/crm-reports/universities/${UNI}/applications?intake=Fall+2027&page=2`);
    expect(screen.getByRole("heading", { level: 2, name: "Leeds" })).toBeTruthy();
  });

  it("the Overseas Admin page refuses other roles before calling the API", async () => {
    vi.mocked(serverApi).mockResolvedValueOnce({ role: "counselor", full_name: "Ravi" });
    render(await AdminUniversityPage(props()));
    expect(vi.mocked(serverApi)).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("an unknown university shows a message, not a crash", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/me") return PARTNER;
      throw new ApiError("University not found", 404);
    }) as never;
    render(await ManagementUniversityPage(props()));
    expect(screen.getByRole("alert").textContent).toBe("That university is not in the reports.");
  });

  it("a malformed id never reaches the API", async () => {
    vi.mocked(serverApi).mockResolvedValueOnce(PARTNER);
    render(await ManagementUniversityPage({ params: Promise.resolve({ id: "not-a-uuid" }), searchParams: Promise.resolve({}) }));
    expect(vi.mocked(serverApi)).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert").textContent).toBe("That university is not in the reports.");
  });
});
