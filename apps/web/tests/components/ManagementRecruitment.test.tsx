import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruitmentPage from "@/app/management/recruitment/page";
import ManagementRecruitment from "@/components/ManagementRecruitment";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { Recruitment } from "@/lib/managementRecruitment";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { redirect } from "next/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/recruitment" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Arjun Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Root", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const data: Recruitment = {
  date_from: "2026-10-01",
  date_to: "2026-10-13",
  revenue_visible: true,
  kpis: {
    recruiters: 6, employer_partners: 1240, new_companies: 12, job_openings: 30, internship_openings: 4, candidates: 210, interviews: 45,
    selections: 9, joining: 5, placement_rate: 12.5, revenue: "450000.00",
  }, // prettier-ignore
  pipeline: [
    { key: "lead", label: "Lead", value: 80 }, { key: "meeting", label: "Meeting", value: 20 }, { key: "requirement", label: "Requirement", value: 10 },
    { key: "candidate", label: "Candidate", value: 8 }, { key: "interview", label: "Interview", value: 5 }, { key: "selection", label: "Selection", value: 2 },
    { key: "joining", label: "Joining", value: 1 },
  ], // prettier-ignore
  requirement_closed: 3,
  lost: 7,
};
const hidden: Recruitment = { ...data, revenue_visible: false, kpis: { ...data.kpis, revenue: null } };
const EMPTY = { date_from: "", date_to: "" };

function answer(me: ManagementMe, body: Recruitment | Error = data) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const result = path === "/api/v1/management/me" ? me : body;
    if (result instanceof Error) throw result;
    return result as never;
  });
}

const page = (search: Record<string, string> = {}) => RecruitmentPage({ searchParams: Promise.resolve(search) });
const tiles = () => within(screen.getByRole("list", { name: "Recruiter KPIs" })).getAllByRole("listitem");

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(() => cleanup());

describe("mgmt-025 recruitment page", () => {
  it("reads the dashboard for the address's period and shows it in the management shell", async () => {
    answer(partner);
    const tree = elements(await page({ date_from: "2026-10-01", date_to: "2026-10-13" }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/recruitment?date_from=2026-10-01&date_to=2026-10-13");
    const shell = tree.find((el) => el.type === PortalShell)!;
    expect(shell.props.roleLabel).toBe("Partner");
    expect(shell.props.nav).toContainEqual({ label: "Recruitment", href: "/management/recruitment" });
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("heading", { level: 2, name: "Recruitment" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Command Center" }).getAttribute("href")).toBe("/management");
  });

  it("drops a submitted form's empty dates from the address by one redirect", async () => {
    answer(partner);
    await page({ date_from: "", date_to: "2026-10-13" });
    expect(redirect).toHaveBeenCalledWith("/management/recruitment?date_to=2026-10-13");
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin, hidden);
    const shell = elements(await page()).find((el) => el.type === PortalShell)!;
    expect(shell.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the access card when the dashboard is refused (the accountant's 403)", async () => {
    answer({ ...partner, role: "accountant", tiers: { operational: false, finance: true, partner_only: false } }, new ApiError("Operational access required", 403));
    render(await page());
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Operational access required")).toBeTruthy();
  });

  it("shows the API's own words for a 422 and a generic message for anything else", async () => {
    answer(partner, new ApiError("The range can't end in the future", 422));
    let shell = elements(await page({ date_to: "2099-01-01" })).find((el) => el.type === PortalShell)!;
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("The range can't end in the future");
    cleanup();
    answer(partner, new ApiError("boom", 500));
    shell = elements(await page()).find((el) => el.type === PortalShell)!;
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("The recruitment dashboard is unavailable right now. Please try again.");
  });
});

describe("mgmt-025 ManagementRecruitment", () => {
  it("shows the eleven §21 KPIs in source order under the #recruitment-kpis anchor", () => {
    render(<ManagementRecruitment data={data} error="" filters={EMPTY} />);
    expect(tiles().map((tile) => tile.querySelector("span")?.textContent)).toEqual([
      "Recruiters", "Employer partners", "New companies", "Job openings", "Internship openings", "Candidates", "Interviews", "Selections",
      "Joining", "Placement rate", "Revenue",
    ]); // prettier-ignore
    expect(within(tiles()[1]).getByText("1,240")).toBeTruthy();
    expect(within(tiles()[9]).getByText("12.5%")).toBeTruthy();
    expect(within(tiles()[10]).getByText("₹4,50,000.00")).toBeTruthy();
    expect(document.getElementById("recruitment-kpis")?.contains(tiles()[0])).toBe(true);
    expect(screen.getByText(/01 Oct 2026 to 13 Oct 2026/)).toBeTruthy();
  });

  it("leaves revenue out for the super admin and says who sees it", () => {
    render(<ManagementRecruitment data={hidden} error="" filters={EMPTY} />);
    expect(tiles()).toHaveLength(10);
    expect(screen.queryByText("Revenue")).toBeNull();
    expect(screen.getByText(/Revenue is shown to partners/)).toBeTruthy();
  });

  it("shows a dash when nobody was sourced", () => {
    render(<ManagementRecruitment data={{ ...data, kpis: { ...data.kpis, placement_rate: null } }} error="" filters={EMPTY} />);
    expect(within(tiles()[9]).getByText("—")).toBeTruthy();
  });

  it("shows the company pipeline in §21 order, then Requirement closed and Lost", () => {
    render(<ManagementRecruitment data={data} error="" filters={EMPTY} />);
    const steps = within(screen.getByRole("list", { name: "Company pipeline" })).getAllByRole("listitem");
    expect(steps.map((step) => step.querySelector(".funnel-label")?.textContent)).toEqual(["Lead", "Meeting", "Requirement", "Candidate", "Interview", "Selection", "Joining"]);
    expect(within(steps[0]).getByText("80")).toBeTruthy();
    expect(document.getElementById("company-pipeline")?.contains(steps[0])).toBe(true);
    expect(screen.getByText(/Requirement closed: 3/).className).toBe("muted funnel-note"); // QA25-01: spaced from the last step
    expect(screen.getByText(/Lost: 7/)).toBeTruthy();
  });

  it("offers the period as a GET form showing the period on screen, and a link back to this month when one is set", () => {
    render(<ManagementRecruitment data={data} error="" filters={{ date_from: "2026-10-05", date_to: "" }} />);
    const form = screen.getByRole("form", { name: "Recruitment period" });
    expect(form.getAttribute("action")).toBe("/management/recruitment");
    expect(form.getAttribute("method")).toBe("get");
    expect((within(form).getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-05");
    expect((within(form).getByLabelText("To") as HTMLInputElement).value).toBe("2026-10-13");
    expect(screen.getByRole("link", { name: "This month" }).getAttribute("href")).toBe("/management/recruitment");
    cleanup();
    render(<ManagementRecruitment data={data} error="" filters={EMPTY} />);
    expect(screen.queryByRole("link", { name: "This month" })).toBeNull();
  });

  it("a client navigation to another period resets the inputs", () => {
    const { rerender } = render(<ManagementRecruitment data={{ ...data, date_from: "2026-10-05" }} error="" filters={{ date_from: "2026-10-05", date_to: "" }} />);
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-05");
    rerender(<ManagementRecruitment data={data} error="" filters={EMPTY} />);
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-01");
  });

  it("shows the error and the form only when the dashboard could not be read", () => {
    render(<ManagementRecruitment data={null} error="The recruitment dashboard is unavailable right now. Please try again." filters={EMPTY} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Recruiter KPIs" })).toBeNull();
    expect(screen.getByRole("form", { name: "Recruitment period" })).toBeTruthy();
  });
});
