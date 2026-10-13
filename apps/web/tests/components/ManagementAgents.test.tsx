import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementAgentsPage from "@/app/management/agents/page";
import ManagementAgents from "@/components/ManagementAgents";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import type { AgencyRow, AgentsDashboard } from "@/lib/managementAgents";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/agents" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Priya Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Sam Admin", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const QUERY = { from: "2026-05-01", to: "2026-05-31" };
const LABELS = ["Total agents", "New agents", "Active agents", "Inactive agents", "Agent staff", "Students", "Applications", "Offers", "Visa", "Enrollments", "Commission", "Revenue"];
const KEYS = ["agents", "new_agents", "active_agents", "inactive_agents", "staff", "students", "applications", "offers", "visa", "enrollments", "commission", "revenue"] as const;

const agency = (over: Partial<AgencyRow>): AgencyRow => ({
  id: "o1", name: "Globe Admissions", prefix: "GLB", status: "active", new: false,
  staff: 0, students: 0, applications: 0, offers: 0, visa: 0, enrollments: 0, commission: "0.00", revenue: "0.00", ...over,
}); // prettier-ignore

function dashboard(over: Partial<AgentsDashboard> = {}): AgentsDashboard {
  return {
    from: "2026-05-01", to: "2026-05-31", as_of: "2026-10-13T05:00:00Z", money_visible: true,
    figures: KEYS.map((key, i) => ({ key, label: LABELS[i], definition: `${LABELS[i]} meaning.` })),
    totals: { agents: 2, new_agents: 1, active_agents: 1, inactive_agents: 1, staff: 5, students: 12, applications: 1500, offers: 6, visa: 3,
              enrollments: 2, commission: "5000.00", revenue: "150000.00" },
    chain: [
      { key: "agents", label: "Agent", value: 2 }, { key: "staff", label: "Staff", value: 5 }, { key: "students", label: "Student", value: 12 },
      { key: "applications", label: "Application", value: 1500 }, { key: "enrollments", label: "Enrollment", value: 2 },
      { key: "revenue", label: "Revenue", value: "150000.00" },
    ],
    agencies: [
      agency({ id: "o1", name: "Globe Admissions", new: true, staff: 3, students: 10, applications: 1499, offers: 6, visa: 3, enrollments: 2, commission: "5000.00", revenue: "150000.00" }),
      agency({ id: "o2", name: "Quiet Overseas", prefix: "QOV", status: "suspended", staff: 2, students: 2, applications: 1 }),
    ],
    ...over,
  }; // prettier-ignore
}

function hidden(): AgentsDashboard {
  const data = dashboard({ money_visible: false });
  data.totals = { ...data.totals, commission: null, revenue: null };
  data.agencies = data.agencies.map((a) => ({ ...a, commission: null, revenue: null }));
  data.chain = data.chain.filter((s) => s.key !== "revenue");
  return data;
}

function view(props: Partial<Parameters<typeof ManagementAgents>[0]> = {}) {
  return render(<ManagementAgents data={dashboard()} error="" query={QUERY} {...props} />);
}

const figures = () => screen.getByRole("list", { name: "Agent network figures" });
const tile = (label: string) => within(figures()).getByText(label, { selector: "span" }).closest("li")!;
const table = () => screen.getByRole("table", { name: "Agency-wise performance" });

describe("mgmt-021 ManagementAgents", () => {
  afterEach(cleanup);

  it("shows the twelve §17 figures in source order, with Indian grouping and rupees", () => {
    view();
    expect(within(figures()).getAllByRole("listitem").map((li) => li.querySelector("span")!.textContent)).toEqual(LABELS);
    expect(tile("Applications")).toHaveTextContent("1,500");
    expect(tile("Revenue")).toHaveTextContent("₹1,50,000.00");
    expect(tile("Commission")).toHaveTextContent("₹5,000.00");
    expect(tile("Agent staff")).toHaveTextContent("Agent staff meaning.");
  });

  it("shows the chain in order, revenue last", () => {
    view();
    const chain = screen.getByRole("list", { name: "Agent → Staff → Student → Application → Enrollment → Revenue" });
    expect(within(chain).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Agent2", "Staff5", "Student12", "Application1,500", "Enrollment2", "Revenue₹1,50,000.00",
    ]);
  });

  it("ranks every agency with its chain columns and an All agencies total", () => {
    view();
    expect(within(table()).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Rank", "Agency", "Agent staff", "Students", "Applications", "Offers", "Visa", "Enrollments", "Commission", "Revenue",
    ]);
    const globe = within(table()).getByRole("rowheader", { name: /Globe Admissions/ }).closest("tr")!;
    expect(globe).toHaveTextContent("New");
    expect(Array.from(globe.querySelectorAll("td")).map((td) => td.textContent)).toEqual(["1", "3", "10", "1,499", "6", "3", "2", "₹5,000.00", "₹1,50,000.00"]);
    const quiet = within(table()).getByRole("rowheader", { name: /Quiet Overseas/ }).closest("tr")!;
    expect(quiet).toHaveTextContent("Suspended");
    expect(quiet.querySelector("td")).toHaveTextContent("2");
    const total = table().querySelector("tfoot tr")!;
    expect(total).toHaveTextContent("All agencies");
    expect(total).toHaveTextContent("₹1,50,000.00");
    expect(screen.getByRole("heading", { name: "Agency-wise performance" }).closest("section")).toHaveAttribute("id", "agencies");
  });

  it("shows the super admin no money: Partners only tiles, no money columns, no revenue step", () => {
    view({ data: hidden() });
    expect(within(tile("Commission")).getByText("Partners only")).toHaveClass("metric-untracked");
    expect(within(tile("Revenue")).getByText("Partners only")).toHaveClass("metric-untracked");
    expect(within(table()).queryByRole("columnheader", { name: "Revenue" })).toBeNull();
    expect(within(table()).queryByRole("columnheader", { name: "Commission" })).toBeNull();
    expect(screen.getByRole("list", { name: "Agent → Staff → Student → Application → Enrollment" })).toBeInTheDocument();
    expect(screen.queryByText(/₹/)).toBeNull();
  });

  it("names the period and the agencies, in a GET period form", () => {
    view();
    expect(screen.getByText(new RegExp(`^${formatCalendarDate("2026-05-01")} to ${formatCalendarDate("2026-05-31")}`))).toHaveTextContent("2 agencies");
    const form = screen.getByRole("form", { name: "Choose a period" });
    expect(form).toHaveAttribute("method", "get");
    expect(within(form).getByLabelText("From")).toHaveValue("2026-05-01");
    expect(within(form).getByLabelText("To")).toHaveValue("2026-05-31");
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("href", "/management/agents");
  });

  it("says one agency in the singular", () => {
    view({ data: dashboard({ totals: { ...dashboard().totals, agents: 1 } }) });
    expect(screen.getByText(/1 agency\./)).toBeInTheDocument();
  });

  it("says so when there are no approved agencies yet", () => {
    view({ data: dashboard({ agencies: [] }) });
    expect(screen.getByRole("status")).toHaveTextContent("No approved agencies yet");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows an error without figures", () => {
    view({ data: null, error: "The period must start on or before its end" });
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    expect(screen.queryByRole("list", { name: "Agent network figures" })).toBeNull();
    expect(screen.getByRole("form", { name: "Choose a period" })).toBeInTheDocument();
  });
});

describe("mgmt-021 Agent network dashboard page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(me: ManagementMe, result: AgentsDashboard | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const value = path === "/api/v1/management/me" ? me : path.startsWith("/api/v1/management/agents") ? result : (null as never);
      if (value instanceof Error) throw value;
      return value as never;
    });
  }

  it("asks for the period in the address and renders in the Command Center sidebar", async () => {
    answer(partner, dashboard());
    const tree = await ManagementAgentsPage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/agents?from=2026-05-01&to=2026-05-31");
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toContainEqual({ label: "Agents", href: "/management/agents" });
    render(tree);
    expect(screen.getByRole("heading", { name: "Agent network dashboard" })).toBeInTheDocument();
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin, hidden());
    const tree = await ManagementAgentsPage({ searchParams: Promise.resolve({}) });
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the API's 422 message, a generic message on a server error, and the access card when refused", async () => {
    answer(partner, new ApiError("The period must start on or before its end", 422));
    render(await ManagementAgentsPage({ searchParams: Promise.resolve({ from: "2026-05-31", to: "2026-05-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    cleanup();
    answer(partner, new ApiError("Internal Server Error", 500));
    render(await ManagementAgentsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Agent figures are unavailable right now. Please try again.");
    cleanup();
    answer(partner, new ApiError("Operational access required", 403));
    render(await ManagementAgentsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
  });
});
