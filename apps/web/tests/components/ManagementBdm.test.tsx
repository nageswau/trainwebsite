import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementBdmPage from "@/app/management/bdm/page";
import ManagementBdm from "@/components/ManagementBdm";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import type { BdmDashboard, BdmDashboardQuery } from "@/lib/managementBdm";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/bdm" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Priya Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Sam Admin", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };

const QUERY: BdmDashboardQuery = { type: "agent", from: "2026-05-01", to: "2026-05-31" };

function agent(overrides: Partial<BdmDashboard> = {}): BdmDashboard {
  const figure = (key: string, label: string, basis: "period" | "now", value: number | null) =>
    ({ key, label, definition: `${label} definition.`, basis, tracked: value !== null, value });
  return {
    type: "agent", label: "Agent BDM", from: "2026-05-01", to: "2026-05-31", as_of: "2026-10-13T05:00:00Z", bdm_count: 3,
    figures: [
      figure("agent_prospects", "Agent prospects", "period", 4), figure("meetings", "Meetings", "period", 12), figure("visits", "Visits", "period", 1500),
      figure("agreements", "Agreements", "period", 2), figure("new_agents", "New agents", "period", 1), figure("active_agents", "Active agents", "now", 9),
      figure("agent_students", "Agent students", "period", 30), figure("applications", "Applications", "now", 41), figure("enrollments", "Enrollments", "now", 7),
    ],
    ...overrides,
  }; // prettier-ignore
}

function view(props: Partial<Parameters<typeof ManagementBdm>[0]> = {}) {
  return render(<ManagementBdm data={agent()} error="" query={QUERY} {...props} />);
}

const tiles = (name: string) => within(screen.getByRole("list", { name })).getAllByRole("listitem");

describe("mgmt-020 ManagementBdm", () => {
  afterEach(cleanup);

  it("offers the three BDM types as links that keep the period, the shown one current", () => {
    view();
    const links = within(screen.getByRole("navigation", { name: "BDM types" })).getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual(["Agent BDM", "School BDM", "College BDM"]);
    expect(links[0]).toHaveAttribute("aria-current", "page");
    expect(links[1]).not.toHaveAttribute("aria-current");
    expect(links[2]).toHaveAttribute("href", "/management/bdm?type=college&from=2026-05-01&to=2026-05-31");
  });

  it("splits the figures into the period and right now, in source order, with Indian digit grouping", () => {
    view();
    expect(tiles("In the period").map((li) => li.querySelector("span")!.textContent)).toEqual([
      "Agent prospects", "Meetings", "Visits", "Agreements", "New agents", "Agent students",
    ]);
    expect(tiles("Right now").map((li) => li.querySelector("span")!.textContent)).toEqual(["Active agents", "Applications", "Enrollments"]);
    const visits = tiles("In the period")[2];
    expect(within(visits).getByText("1,500")).toBeInTheDocument();
    expect(visits).toHaveTextContent("Visits definition.");
  });

  it("says Not tracked for a figure nothing records, never 0", () => {
    const college = agent({
      type: "college", label: "College BDM",
      figures: [{ key: "internships", label: "Internships", definition: "Not tracked: internships are not recorded in EduSphere.", basis: "period", tracked: false, value: null }],
    }); // prettier-ignore
    view({ data: college, query: { ...QUERY, type: "college" } });
    const internships = tiles("In the period")[0];
    expect(within(internships).getByText("Not tracked")).toBeInTheDocument();
    expect(internships).not.toHaveTextContent(/\b0\b/);
    expect(screen.queryByRole("list", { name: "Right now" })).toBeNull();
  });

  it("names the period and the active BDMs, and keeps the type in the GET period form", () => {
    view();
    expect(screen.getByText(new RegExp(`^${formatCalendarDate("2026-05-01")} to ${formatCalendarDate("2026-05-31")}`))).toHaveTextContent("3 active Agent BDMs");
    const form = screen.getByRole("form", { name: "Choose a period" });
    expect(form).toHaveAttribute("method", "get");
    expect(form.querySelector('input[type="hidden"][name="type"]')).toHaveAttribute("value", "agent");
    expect(within(form).getByLabelText("From")).toHaveValue("2026-05-01");
    expect(within(form).getByLabelText("To")).toHaveValue("2026-05-31");
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("href", "/management/bdm?type=agent");
  });

  it("QA-01: lets the three tabs wrap on a phone instead of hiding the current one off-screen", () => {
    view({ query: { ...QUERY, type: "college" } });
    expect(screen.getByRole("navigation", { name: "BDM types" })).toHaveClass("report-tablist", "wrap");
  });

  it("QA-02: sets Not tracked as words, not at the figure size", () => {
    view({ data: agent({ figures: [{ key: "internships", label: "Internships", definition: "Not tracked.", basis: "period", tracked: false, value: null }] }) });
    expect(screen.getByText("Not tracked")).toHaveClass("metric-untracked");
  });

  it("QA-03: says one active BDM in the singular", () => {
    view({ data: agent({ bdm_count: 1 }) });
    expect(screen.getByText(/active Agent BDM\./)).toHaveTextContent("1 active Agent BDM.");
  });

  it("shows an error without figures", () => {
    view({ data: null, error: "The period must start on or before its end" });
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    expect(screen.queryByRole("list", { name: "In the period" })).toBeNull();
    expect(screen.getByRole("navigation", { name: "BDM types" })).toBeInTheDocument();
  });
});

describe("mgmt-020 BDM dashboards page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(me: ManagementMe, result: BdmDashboard | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const value = path === "/api/v1/management/me" ? me : path.startsWith("/api/v1/management/bdm") ? result : (null as never);
      if (value instanceof Error) throw value;
      return value as never;
    });
  }

  it("asks for the type and period in the address and renders in the Command Center sidebar", async () => {
    answer(partner, agent());
    const tree = await ManagementBdmPage({ searchParams: Promise.resolve({ type: "school", from: "2026-05-01", to: "2026-05-31" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/bdm?type=school&from=2026-05-01&to=2026-05-31");
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toContainEqual({ label: "BDM", href: "/management/bdm" });
    render(tree);
    expect(screen.getByRole("heading", { name: "BDM dashboards" })).toBeInTheDocument();
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin, agent());
    const tree = await ManagementBdmPage({ searchParams: Promise.resolve({}) });
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the API's 422 message, a generic message on a server error, and the access card when refused", async () => {
    answer(partner, new ApiError("The period must start on or before its end", 422));
    render(await ManagementBdmPage({ searchParams: Promise.resolve({ from: "2026-05-31", to: "2026-05-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    cleanup();
    answer(partner, new ApiError("Internal Server Error", 500));
    render(await ManagementBdmPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("BDM figures are unavailable right now. Please try again.");
    cleanup();
    answer(partner, new ApiError("Operational access required", 403));
    render(await ManagementBdmPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
  });
});
