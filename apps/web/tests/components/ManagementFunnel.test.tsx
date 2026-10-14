import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementFunnelPage from "@/app/management/funnel/page";
import ManagementFunnel from "@/components/ManagementFunnel";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import type { FunnelBreakdown, FunnelQuery, StudentFunnel } from "@/lib/managementFunnel";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/funnel" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Priya Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Sam Admin", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const QUERY: FunnelQuery = { from: "2026-05-01", to: "2026-05-31", by: "" };
const STAGES: [string, string, string, number][] = [
  ["leads", "Leads", "lead", 1250], ["telecalling", "Telecalling", "lead", 900], ["counseling", "Counseling", "lead", 300], ["registration", "Registration", "lead", 120],
  ["training", "Training", "it", 80], ["it_application", "Application", "it", 40], ["certification", "Certification", "it", 30], ["placement", "Placement", "it", 12],
  ["joining", "Joining", "it", 9], ["abroad_education", "Abroad Education", "abroad", 60], ["abroad_application", "Application", "abroad", 45],
  ["offer", "Offer", "abroad", 20], ["visa", "Visa", "abroad", 8], ["enrollment", "Enrollment", "abroad", 6],
]; // prettier-ignore
const ABROAD = ["abroad_education", "abroad_application", "offer", "visa", "enrollment"];

function dashboard(breakdown: FunnelBreakdown | null = null): StudentFunnel {
  return {
    from: "2026-05-01", to: "2026-05-31", as_of: "2026-10-14T05:00:00Z",
    paths: [{ key: "lead", label: "Lead journey" }, { key: "it", label: "IT training" }, { key: "abroad", label: "Abroad education" }],
    stages: STAGES.map(([key, label, path, value]) => ({ key, label, path, value, definition: `About ${key}.` })),
    dimensions: [
      { key: "country", label: "Country", tracked: true, stages: ABROAD }, { key: "branch", label: "Branch", tracked: false, stages: [] },
    ],
    breakdown,
  }; // prettier-ignore
}

const byCountry: FunnelBreakdown = {
  by: "country", label: "Country", tracked: true, stages: ABROAD,
  rows: [
    { value: "c1", label: "United Kingdom", counts: { abroad_education: 40, abroad_application: 30, offer: 15, visa: 6, enrollment: 5 } },
    { value: "c2", label: "Canada", counts: { abroad_education: 15, abroad_application: 10, offer: 5, visa: 2, enrollment: 1 } },
  ],
  unknown: { abroad_education: 5, abroad_application: 5, offer: 0, visa: 0, enrollment: 0 },
}; // prettier-ignore

function view(props: Partial<Parameters<typeof ManagementFunnel>[0]> = {}) {
  return render(<ManagementFunnel data={dashboard()} error="" query={QUERY} {...props} />);
}

const stage = (path: string, label: string) => within(screen.getByRole("list", { name: path })).getByText(label, { selector: ".pipeline-label" }).closest("li")!;

describe("mgmt-016 ManagementFunnel", () => {
  afterEach(cleanup);

  it("shows the lead journey, then the IT and abroad paths, each stage with its count and definition", () => {
    view();
    const labels = (path: string) => within(screen.getByRole("list", { name: path })).getAllByRole("listitem").map((li) => li.querySelector(".pipeline-label")!.textContent);
    expect(labels("Lead journey")).toEqual(["Leads", "Telecalling", "Counseling", "Registration"]);
    expect(labels("IT training")).toEqual(["Training", "Application", "Certification", "Placement", "Joining"]);
    expect(labels("Abroad education")).toEqual(["Abroad Education", "Application", "Offer", "Visa", "Enrollment"]);
    expect(stage("Lead journey", "Leads")).toHaveTextContent("1,250");
    expect(stage("Lead journey", "Leads")).toHaveTextContent("About leads.");
    expect(stage("Abroad education", "Application")).toHaveTextContent("45");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("names the period and says the stages are activity, not a cohort", () => {
    view();
    expect(screen.getByText(new RegExp(`^${formatCalendarDate("2026-05-01")} to ${formatCalendarDate("2026-05-31")}, India time`))).toHaveTextContent(
      "Each stage counts what reached it in the period",
    );
  });

  it("offers the period and a breakdown in a GET form", () => {
    view({ query: { ...QUERY, by: "country" } });
    const form = screen.getByRole("form", { name: "Choose a period and breakdown" });
    expect(form).toHaveAttribute("method", "get");
    expect(within(form).getByLabelText("From")).toHaveValue("2026-05-01");
    expect(within(form).getByLabelText("To")).toHaveValue("2026-05-31");
    const select = within(form).getByLabelText("Break down by");
    expect(select).toHaveValue("country");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "No breakdown", "Country", "Course", "Agent", "School", "Counselor", "Marketing source", "BDM", "Intake", "Branch (not tracked)",
    ]); // prettier-ignore
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("href", "/management/funnel");
  });

  it("breaks the applicable stages down by the chosen dimension, with Unknown and Total rows that match the stages", () => {
    view({ data: dashboard(byCountry), query: { ...QUERY, by: "country" } });
    const table = screen.getByRole("table", { name: "Student funnel by Country" });
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Country", "Abroad Education", "Application (Abroad education)", "Offer", "Visa", "Enrollment",
    ]); // prettier-ignore
    const row = (name: string) => Array.from(within(table).getByRole("rowheader", { name }).closest("tr")!.querySelectorAll("td")).map((td) => td.textContent);
    expect(row("United Kingdom")).toEqual(["40", "30", "15", "6", "5"]);
    expect(row("Unknown")).toEqual(["5", "5", "0", "0", "0"]);
    expect(row("Total")).toEqual(["60", "45", "20", "8", "6"]);
    expect(screen.getByText(/Not broken down by Country:/)).toHaveTextContent("Leads, Telecalling, Counseling, Registration, Training, Application (IT training)");
  });

  it("keeps the dimension's own spelling in the note on the other stages (QA16-01)", () => {
    const leadStages = ["leads", "telecalling", "counseling", "registration"];
    view({ data: dashboard({ by: "bdm", label: "BDM", tracked: true, stages: leadStages, rows: [], unknown: Object.fromEntries(leadStages.map((k) => [k, 0])) }) });
    expect(screen.getByText(/Not broken down by BDM:/)).toHaveTextContent(/Their records carry no BDM value\.$/);
  });

  it("says when nothing in the period carries the dimension", () => {
    view({ data: dashboard({ ...byCountry, rows: [], unknown: { abroad_education: 0, abroad_application: 0, offer: 0, visa: 0, enrollment: 0 } }) });
    expect(screen.getByRole("status")).toHaveTextContent("No Country recorded on anything in this period.");
  });

  it("says Branch is not tracked instead of a table", () => {
    view({ data: dashboard({ by: "branch", label: "Branch", tracked: false, stages: [], rows: [], unknown: {} }) });
    expect(screen.getByRole("status")).toHaveTextContent("Branch is not tracked in EduSphere yet");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows an error without figures", () => {
    view({ data: null, error: "The period must start on or before its end" });
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    expect(screen.queryByRole("list", { name: "Lead journey" })).toBeNull();
    expect(screen.getByRole("form", { name: "Choose a period and breakdown" })).toBeInTheDocument();
  });
});

describe("mgmt-016 Student funnel page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(me: ManagementMe, result: StudentFunnel | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const value = path === "/api/v1/management/me" ? me : path.startsWith("/api/v1/management/funnel") ? result : (null as never);
      if (value instanceof Error) throw value;
      return value as never;
    });
  }

  it("asks for the period and breakdown in the address and renders in the Command Center sidebar", async () => {
    answer(partner, dashboard());
    const tree = await ManagementFunnelPage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31", by: "school" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/funnel?from=2026-05-01&to=2026-05-31&by=school");
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toContainEqual({ label: "Student funnel", href: "/management/funnel" });
    render(tree);
    expect(screen.getByRole("heading", { name: "Student funnel" })).toBeInTheDocument();
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin, dashboard());
    const tree = await ManagementFunnelPage({ searchParams: Promise.resolve({}) });
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the API's 422 message, a generic message on a server error, and the access card when refused", async () => {
    answer(partner, new ApiError("The period must start on or before its end", 422));
    render(await ManagementFunnelPage({ searchParams: Promise.resolve({ from: "2026-05-31", to: "2026-05-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    cleanup();
    answer(partner, new ApiError("Internal Server Error", 500));
    render(await ManagementFunnelPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Student funnel figures are unavailable right now. Please try again.");
    cleanup();
    answer(partner, new ApiError("Operational access required", 403));
    render(await ManagementFunnelPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
  });
});
