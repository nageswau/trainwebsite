import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ApplicationsPage from "@/app/management/applications/page";
import ManagementApplications from "@/components/ManagementApplications";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import { EMPTY_FUNNEL_FILTERS, type ApplicationFunnel } from "@/lib/managementApplications";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { redirect } from "next/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/applications" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Arjun Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Root", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const STAGES: [string, string, number | null][] = [
  ["created", "Applications Created", 1200], ["documents_complete", "Documents Complete", 300], ["submitted", "Submitted", 600],
  ["under_review", "Under Review", null], ["offer", "Offer", 400], ["accepted", "Accepted", null], ["deposit", "Deposit", 150],
  ["cas_coe", "CAS/COE", null], ["visa", "Visa", 120], ["visa_approved", "Visa Approved", 90], ["enrollment", "Enrollment", 60],
]; // prettier-ignore
const none = { date_from: null, date_to: null, agency: null, counselor: null, country: null, university: null, course: null, intake: null, staff: null, status: null };
const funnel: ApplicationFunnel = {
  filters: none,
  stages: STAGES.map(([key, label, value]) => ({ key, label, value, tracked: value !== null })),
  withdrawn: 25,
  options: {
    agencies: [{ value: "a1", label: "Global Pathways" }], counselors: [{ value: "c1", label: "Meera Counselor" }], countries: [{ value: "k1", label: "United Kingdom" }],
    universities: [{ value: "u1", label: "Leeds" }], courses: [{ value: "o1", label: "MSc Data — Leeds" }], intakes: [{ value: "Sep 2027", label: "Sep 2027" }],
    staff: [{ value: "s1", label: "Asha Admin" }], statuses: [{ value: "offer", label: "Offer" }],
  },
}; // prettier-ignore

function answer(me: ManagementMe | Error, data: ApplicationFunnel | Error = funnel) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const result =
      path === "/api/v1/management/me" ? me : String(path).startsWith("/api/v1/management/applications") ? data : ({ id: "x", role: "partner", division: "global", full_name: "Ravi" } as never);
    if (result instanceof Error) throw result;
    return result as never;
  });
}

const page = (search: Record<string, string> = {}) => ApplicationsPage({ searchParams: Promise.resolve(search) });

beforeEach(() => vi.mocked(serverApi).mockReset());
afterEach(() => cleanup());

describe("mgmt-024 applications page", () => {
  it("reads the funnel with the address's filters and shows it in the management shell", async () => {
    answer(partner);
    const tree = elements(await page({ status: "offer", intake: "Sep 2027" }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/applications?intake=Sep+2027&status=offer");
    const shell = tree.find((el) => el.type === PortalShell)!;
    expect(shell.props.roleLabel).toBe("Partner");
    expect(shell.props.nav).toContainEqual({ label: "Applications", href: "/management/applications" });
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("heading", { level: 2, name: "Applications funnel" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Command Center" }).getAttribute("href")).toBe("/management");
  });

  it("QA24-01: a submitted form's empty fields are dropped from the address by one redirect", async () => {
    answer(partner);
    await page({ date_from: "", agency: "", status: "offer", intake: "" });
    expect(redirect).toHaveBeenCalledWith("/management/applications?status=offer");
    vi.mocked(redirect).mockClear();
    await page({ status: "offer" });
    expect(redirect).not.toHaveBeenCalled();
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin);
    const shell = elements(await page()).find((el) => el.type === PortalShell)!;
    expect(shell.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the access card when the funnel is refused (the accountant's 403)", async () => {
    answer({ ...partner, role: "accountant", tiers: { operational: false, finance: true, partner_only: false } }, new ApiError("Operational access required", 403));
    render(await page());
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Operational access required")).toBeTruthy();
  });

  it("shows the API's own words for a 422 and a generic message for anything else", async () => {
    answer(partner, new ApiError("The end date must be on or after the start date", 422));
    let shell = elements(await page({ date_from: "2026-05-01", date_to: "2026-04-01" })).find((el) => el.type === PortalShell)!;
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("The end date must be on or after the start date");
    cleanup();
    answer(partner, new ApiError("boom", 500));
    shell = elements(await page()).find((el) => el.type === PortalShell)!;
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("The applications funnel is unavailable right now. Please try again.");
  });
});

describe("mgmt-024 ManagementApplications", () => {
  it("lists the eleven stages in source order with counts, shares of Created, and Not tracked for the three untracked ones", () => {
    render(<ManagementApplications data={funnel} error="" filters={EMPTY_FUNNEL_FILTERS} />);
    const rows = within(screen.getByRole("list", { name: "Application funnel" })).getAllByRole("listitem");
    expect(rows.map((row) => row.querySelector(".funnel-label")?.textContent)).toEqual(STAGES.map(([, label]) => label));
    expect(within(rows[0]).getByText("1,200")).toBeTruthy();
    expect(within(rows[2]).getByText("50% of applications created")).toBeTruthy();
    for (const index of [3, 5, 7]) {
      expect(within(rows[index]).getByText("Not tracked")).toBeTruthy();
      expect(rows[index].querySelector(".funnel-track")).toBeNull();
    }
    expect(screen.getByText(/25 of these applications are withdrawn/).className).toContain("funnel-note"); // QA24-04: spaced from the bars
  });

  it("QA24-03: a small non-zero stage reads less than 1%, never 0%", () => {
    const small = { ...funnel, stages: funnel.stages.map((s) => (s.key === "submitted" ? { ...s, value: 2 } : s)) };
    render(<ManagementApplications data={small} error="" filters={EMPTY_FUNNEL_FILTERS} />);
    const rows = within(screen.getByRole("list", { name: "Application funnel" })).getAllByRole("listitem");
    expect(within(rows[2]).getByText("Less than 1% of applications created")).toBeTruthy();
  });

  it("QA24-02: lays the filters out on the even filter grid", () => {
    render(<ManagementApplications data={funnel} error="" filters={EMPTY_FUNNEL_FILTERS} />);
    expect(screen.getByRole("form", { name: "Application filters" }).className).toBe("funnel-filters");
  });

  it("offers the eight filters and the created dates, each labelled, with the applied values selected", () => {
    const filters = { ...EMPTY_FUNNEL_FILTERS, agency: "none", status: "offer", date_from: "2026-04-01" };
    render(<ManagementApplications data={funnel} error="" filters={filters} />);
    const form = screen.getByRole("form", { name: "Application filters" });
    expect(form.getAttribute("method")).toBe("get");
    expect(form.getAttribute("action")).toBe("/management/applications");
    for (const label of ["Agent", "Counselor", "Country", "University", "Course", "Intake", "Staff", "Status"]) expect(within(form).getByLabelText(label)).toBeTruthy();
    expect((within(form).getByLabelText("Agent") as HTMLSelectElement).value).toBe("none");
    expect((within(form).getByLabelText("Status") as HTMLSelectElement).value).toBe("offer");
    expect((within(form).getByLabelText("Created from") as HTMLInputElement).value).toBe("2026-04-01");
    expect(within(form).getByRole("option", { name: "Global Pathways" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Clear filters" }).getAttribute("href")).toBe("/management/applications");
  });

  it("has no Clear link when nothing is filtered", () => {
    render(<ManagementApplications data={funnel} error="" filters={EMPTY_FUNNEL_FILTERS} />);
    expect(screen.queryByRole("link", { name: "Clear filters" })).toBeNull();
  });

  it("says so when no application matches", () => {
    const empty = { ...funnel, withdrawn: 0, stages: funnel.stages.map((s) => ({ ...s, value: s.tracked ? 0 : null })) };
    render(<ManagementApplications data={empty} error="" filters={{ ...EMPTY_FUNNEL_FILTERS, intake: "Sep 2027" }} />);
    expect(screen.getByRole("status").textContent).toBe("No applications match these filters.");
    expect(screen.queryByText(/withdrawn/)).toBeNull();
  });

  it("shows the error and the form only when the funnel could not be read", () => {
    render(<ManagementApplications data={null} error="The applications funnel is unavailable right now. Please try again." filters={EMPTY_FUNNEL_FILTERS} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Application funnel" })).toBeNull();
    expect(screen.getByRole("form", { name: "Application filters" })).toBeTruthy();
  });
});
