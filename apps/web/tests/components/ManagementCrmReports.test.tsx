import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminCrmReportsPage from "@/app/overseas/admin/crm-reports/page";
import CrmReportsPage from "@/app/management/crm-reports/page";
import ManagementCrmReports from "@/components/ManagementCrmReports";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import { ADMIN_CRM_REPORTS_HOME, CRM_REPORTS_HOME, EMPTY_CRM_FILTERS, type CrmReports } from "@/lib/managementCrmReports";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/crm-reports" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const def = (key: string, label: string) => ({ key, label, definition: `${label} means something.` });
const bands = { d0_7: 1, d8_14: 0, d15_30: 2, d31_60: 0, d61_plus: 1 };
const reports: CrmReports = {
  filters: { date_from: null, date_to: null, counselor: null, country: null, university: null, course: null, intake: null },
  as_of: "2026-10-25",
  ageing: {
    definitions: [def("applications", "Applications"), def("students", "Students"), def("days", "Days since last update"), def("oldest_days", "Oldest")],
    rows: [{ stage: "university_selection", stage_label: "University selection", sub_status: "documents_pending", sub_status_label: "Documents pending", applications: 4, students: 3, bands, oldest_days: 70 }],
    total: { applications: 4, students: 3, bands, oldest_days: 70 },
  },
  universities: {
    definitions: [def("applications", "Applications"), def("students", "Students"), def("offers", "Offers"), def("offer_rate", "Offer rate"), def("rejections", "Rejections"), def("acceptances", "Acceptances"), def("enrollments", "Enrolments"), def("deposits_paid", "Deposits paid"), def("visas_approved", "Visas approved"), def("visas_refused", "Visas refused"), def("visas_pending", "Visas pending")],
    rows: [{ university_id: "u1", label: "Leeds", applications: 4, students: 4, offers: 3, offer_rate: 75, rejections: 1, acceptances: 1, enrollments: 1, deposits_paid: 2, visas_approved: 2, visas_refused: 1, visas_pending: 0 }],
    total: { applications: 4, students: 4, offers: 3, offer_rate: 75, rejections: 1, acceptances: 1, enrollments: 1, deposits_paid: 2, visas_approved: 2, visas_refused: 1, visas_pending: 0 },
  },
  visa: { definitions: [def("applications", "Visa cases"), def("students", "Students")], rows: [], total: { applications: 0, students: 0, submitted: 0, pending: 0, approved: 0, refused: 0, enrolled: 0 } },
  readiness: {
    definitions: [def("applications", "Applications"), def("students", "Students"), def("ready", "Ready"), def("blocked", "Blocked"), def("needs_override", "Needs override"), def("no_checklist", "No checklist")],
    rows: [{ stage: "university_selection", stage_label: "University selection", applications: 2, students: 2, ready: 0, blocked: 1, needs_override: 1, no_checklist: 0 }],
    total: { applications: 2, students: 2, ready: 0, blocked: 1, needs_override: 1, no_checklist: 0 },
  },
  leads: {
    definitions: [def("leads", "Leads"), def("converted", "Converted"), def("conversion_pct", "Conversion %"), def("students", "Students"), def("applications", "Applications")],
    rows: [{ intake: null, label: "Not recorded", leads: 3, converted: 0, conversion_pct: 0, students: 0, applications: 0 }],
    total: { leads: 3, converted: 0, conversion_pct: 0, students: 0, applications: 0 },
  },
  forecast: {
    definitions: [def("applications", "Applications"), def("students", "Students"), def("confirmed", "Confirmed"), def("expected", "Expected"), def("possible", "Possible"), def("lost", "Lost"), def("forecast", "Forecast")],
    rows: [{ intake: "Fall 2027", label: "Fall 2027", applications: 6, students: 6, confirmed: 1, expected: 1, possible: 1, lost: 2, forecast: 2 }],
    total: { applications: 6, students: 6, confirmed: 1, expected: 1, possible: 1, lost: 2, forecast: 2 },
  },
  options: { counselors: [{ value: "c1", label: "Meera" }], countries: [{ value: "k1", label: "United Kingdom" }], universities: [], courses: [], intakes: [{ value: "Fall 2027", label: "Fall 2027" }] },
}; // prettier-ignore

afterEach(cleanup);

describe("ccrm-034 ManagementCrmReports", () => {
  it("shows the six reports, each with students and applications and its definitions", () => {
    render(<ManagementCrmReports data={reports} error="" filters={EMPTY_CRM_FILTERS} home={CRM_REPORTS_HOME} />);
    for (const heading of ["Application ageing", "University performance", "Visa outcomes", "Document readiness", "Lead conversion by intake", "Forecast by intake"]) {
      expect(screen.getByRole("heading", { level: 3, name: heading })).toBeTruthy();
    }
    const ageing = screen.getByRole("table", { name: "Application ageing" });
    const row = within(ageing).getByRole("row", { name: /University selection · Documents pending/ });
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["4", "3", "1", "0", "2", "0", "1", "70"]);
    expect(within(ageing).getAllByRole("columnheader").map((c) => c.textContent)).toContain("Students");
    const perf = screen.getByRole("table", { name: "University performance" });
    expect(within(perf).getByRole("row", { name: /Leeds/ }).textContent).toContain("75%");
    expect(within(perf).getByRole("row", { name: /Total/ })).toBeTruthy();
    expect(screen.getAllByText("Offer rate means something.").length).toBe(1);
    expect(screen.getByText("No visa cases match these filters.")).toBeTruthy();
    expect(within(screen.getByRole("table", { name: "Lead conversion by intake" })).getByRole("row", { name: /Not recorded/ })).toBeTruthy();
  });

  it("filters with a GET form to its own page and offers Clear only when filtered", () => {
    const { rerender } = render(<ManagementCrmReports data={reports} error="" filters={EMPTY_CRM_FILTERS} home={ADMIN_CRM_REPORTS_HOME} />);
    const form = screen.getByRole("form", { name: "Report filters" });
    expect(form.getAttribute("action")).toBe(ADMIN_CRM_REPORTS_HOME);
    expect(within(form).getByLabelText("Counselor")).toBeTruthy();
    expect(within(form).getByRole("option", { name: "No counselor" })).toBeTruthy();
    expect(within(form).getByLabelText("Destination")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Clear filters" })).toBeNull();
    rerender(<ManagementCrmReports data={reports} error="" filters={{ ...EMPTY_CRM_FILTERS, intake: "Fall 2027" }} home={ADMIN_CRM_REPORTS_HOME} />);
    expect(screen.getByRole("link", { name: "Clear filters" }).getAttribute("href")).toBe(ADMIN_CRM_REPORTS_HOME);
  });

  // ccrm-052: deposits and visas per university, and each university opens its applications with the filters kept.
  it("shows deposits and visas per university and links each one to its applications", () => {
    render(<ManagementCrmReports data={reports} error="" filters={{ ...EMPTY_CRM_FILTERS, intake: "Fall 2027" }} home={ADMIN_CRM_REPORTS_HOME} />);
    const perf = screen.getByRole("table", { name: "University performance" });
    expect(within(perf).getAllByRole("columnheader").map((c) => c.textContent).slice(-4)).toEqual(["Deposits paid", "Visas approved", "Visas refused", "Visas pending"]);
    const leeds = within(perf).getByRole("row", { name: /Leeds/ });
    expect(within(leeds).getAllByRole("cell").map((c) => c.textContent).slice(-4)).toEqual(["2", "2", "1", "0"]);
    expect(within(leeds).getByRole("link", { name: "Leeds" }).getAttribute("href")).toBe(`${ADMIN_CRM_REPORTS_HOME}/universities/u1?intake=Fall+2027`);
    expect(within(perf).queryByRole("link", { name: "Total" })).toBeNull();
    expect(within(screen.getByRole("table", { name: "Application ageing" })).queryByRole("link")).toBeNull();
  });

  // ccrm-035 (DEC-SCOPE-268 E2): each report with rows exports its own table with the applied filters; an empty one offers nothing.
  it("offers CSV and Excel for each report that has rows", () => {
    render(<ManagementCrmReports data={reports} error="" filters={{ ...EMPTY_CRM_FILTERS, intake: "Fall 2027" }} home={CRM_REPORTS_HOME} />);
    const group = screen.getByRole("group", { name: "Export University performance" });
    expect(within(group).getByRole("button", { name: "Download CSV" })).toBeTruthy();
    expect(within(group).getByRole("button", { name: "Download Excel" })).toBeTruthy();
    expect(screen.getAllByRole("group", { name: /^Export / })).toHaveLength(5);
    expect(screen.queryByRole("group", { name: "Export Visa outcomes" })).toBeNull();
  });

  it("shows the API's error", () => {
    render(<ManagementCrmReports data={null} error="The end date must be on or after the start date" filters={EMPTY_CRM_FILTERS} home={CRM_REPORTS_HOME} />);
    expect(screen.getByRole("alert").textContent).toBe("The end date must be on or after the start date");
    expect(screen.queryByRole("table")).toBeNull();
  });
});

const partner: ManagementMe = { id: "p1", full_name: "Arjun Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };

function answer(results: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const key = Object.keys(results).find((prefix) => String(path).startsWith(prefix));
    const result = key ? results[key] : undefined;
    if (result instanceof Error) throw result;
    return result as never;
  });
}

describe("ccrm-034 pages", () => {
  beforeEach(() => vi.mocked(serverApi).mockReset());

  it("the Command Center page reads the reports with the address's filters", async () => {
    answer({ "/api/v1/management/me": partner, "/api/v1/management/crm-reports": reports });
    render(await CrmReportsPage({ searchParams: Promise.resolve({ intake: "Fall 2027" }) }));
    expect(vi.mocked(serverApi)).toHaveBeenCalledWith("/api/v1/management/crm-reports?intake=Fall+2027");
    expect(screen.getByRole("heading", { level: 2, name: "CRM reports" })).toBeTruthy();
  });

  it("the Command Center page shows the access card on a 403", async () => {
    answer({ "/api/v1/management/me": partner, "/api/v1/management/crm-reports": new ApiError("Management or Overseas Administrator access required", 403) });
    render(await CrmReportsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("the Overseas Admin page reads the same reports", async () => {
    answer({ "/api/v1/auth/me": { id: "a1", role: "overseas_admin", division: "overseas", full_name: "Asha Admin" }, "/api/v1/management/crm-reports": reports });
    render(await AdminCrmReportsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { level: 2, name: "CRM reports" })).toBeTruthy();
    expect(screen.getByRole("form", { name: "Report filters" }).getAttribute("action")).toBe(ADMIN_CRM_REPORTS_HOME);
  });

  it("the Overseas Admin page refuses a counselor before asking for the reports", async () => {
    answer({ "/api/v1/auth/me": { id: "c1", role: "counselor", division: "overseas", full_name: "Meera" } });
    render(await AdminCrmReportsPage({ searchParams: Promise.resolve({}) }));
    expect(vi.mocked(serverApi)).not.toHaveBeenCalledWith(expect.stringContaining("/crm-reports"));
    expect(screen.queryByRole("table")).toBeNull();
  });
});
