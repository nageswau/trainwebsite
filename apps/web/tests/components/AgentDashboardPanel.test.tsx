import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentDashboardPanel, { AgentDashboardBoard, AgentDashboardSkeleton } from "@/components/AgentDashboardPanel";
import { ApiError, serverApi } from "@/lib/api";
import type { AgentDashboard } from "@/lib/types";

// AGN-018 (DEC-SCOPE-062; spec §6.2): the agency KPI board -- Master and Staff variants, links, empty, error and loading states.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
const api = vi.mocked(serverApi);
afterEach(() => {
  cleanup();
  api.mockReset();
});

const breakdown = (items: [string, number][], other = 0) => ({ items: items.map(([label, count]) => ({ label, count })), other });
const master: AgentDashboard = {
  scope: "agency",
  member_code: "ABC-M001",
  students: 4,
  applications: 7,
  offers: 6,
  visa_applications: 2,
  visa_approvals: 1,
  enrollments: 1,
  pending_documents: 4,
  pending_actions: 2,
  by_country: breakdown([["Aland", 4], ["Betaland", 3]]),
  by_university: breakdown([["Alpha University", 4]], 3),
  staff: [
    { code: "ABC-S001", name: "Staff One", active: true, students: 2, applications: 5, offers: 3, enrollments: 1 },
    { code: "ABC-S002", name: "Staff Two", active: false, students: 1, applications: 1, offers: 2, enrollments: 0 },
  ],
  unassigned_students: 1,
  commission: {
    claimable: [{ currency: "INR", count: 1, amount: 1000 }, { currency: "USD", count: 1, amount: 200 }],
    claims: 1,
    revenue: [{ currency: "INR", count: 1, amount: 12000 }],
  },
  reports_available: true,
  as_of: "2026-10-03T00:00:00Z",
};
const staff: AgentDashboard = { ...master, scope: "own", member_code: "ABC-S001", staff: null, unassigned_students: null, commission: null, reports_available: false };

function tile(label: string) {
  return screen.getByText(label, { selector: "dt" }).closest(".kpi-tile") as HTMLElement;
}

describe("AgentDashboardBoard (AGN-018)", () => {
  it("shows the Master's KPIs with their values", () => {
    render(<AgentDashboardBoard data={master} />);
    expect(screen.getByText(/Whole agency/)).toHaveTextContent("Whole agency · Your code ABC-M001");
    const expected: [string, string][] = [
      ["Total students", "4"], ["Pending actions", "2"], ["Applications", "7"], ["Offers", "6"], ["Visa applications", "2"],
      ["Visa approvals", "1"], ["Enrollments", "1"], ["Pending documents", "4"], ["Claims", "1"],
    ];
    for (const [label, value] of expected) expect(within(tile(label)).getByText(value)).toBeInTheDocument();
    // Exact textContent: getByText normalizes the page's no-break space away, and that space is the QA14-01 wrapping rule.
    expect(tile("Claimable commission").querySelector(".kpi-value")?.textContent).toBe("INR 1,000 · USD 200");
    expect(tile("Revenue").querySelector(".kpi-value")?.textContent).toBe("INR 12,000");
  });

  it("links each countable tile to its list and notes the milestone tiles", () => {
    render(<AgentDashboardBoard data={master} />);
    expect(screen.getByRole("link", { name: "View students" })).toHaveAttribute("href", "/overseas/agent/students");
    expect(screen.getByRole("link", { name: "View applications" })).toHaveAttribute("href", "/overseas/agent/applications");
    expect(screen.getByRole("link", { name: "View enrolled" })).toHaveAttribute("href", "/overseas/agent/applications?status=enrolled");
    expect(screen.getByRole("link", { name: "Review pending" })).toHaveAttribute("href", "/overseas/agent/documents?view=pending");
    expect(screen.getByRole("link", { name: "Open tasks" })).toHaveAttribute("href", "/overseas/agent/tasks?view=open");
    expect(screen.getAllByText("Includes later stages and withdrawn applications")).toHaveLength(3);
    expect(screen.getByRole("link", { name: "View reports" })).toHaveAttribute("href", "/overseas/agent/reports");
  });

  it("shows the breakdowns and the staff table with text badges", () => {
    render(<AgentDashboardBoard data={master} />);
    const countries = screen.getByRole("region", { name: "Applications by country" });
    expect(within(countries).getByRole("rowheader", { name: "Aland" })).toBeInTheDocument();
    const universities = screen.getByRole("region", { name: "Applications by university" });
    expect(within(universities).getByRole("rowheader", { name: "Other" }).closest("tr")).toHaveTextContent("3");
    const team = screen.getByRole("region", { name: "Staff performance" });
    expect(within(team).getByText("Deactivated")).toBeInTheDocument();
    expect(within(team).getByRole("rowheader", { name: "Unassigned" }).closest("tr")).toHaveTextContent("1");
    expect(team).toHaveAttribute("tabindex", "0");
    // AGN-019 (DEC-SCOPE-066 P7): the summary links to the full page.
    expect(screen.getByRole("link", { name: "View staff performance" })).toHaveAttribute("href", "/overseas/agent/performance");
  });

  it("names each table once -- the visible heading labels its scroll region; no hidden caption repeats it (QA18-06)", () => {
    const { container } = render(<AgentDashboardBoard data={master} />);
    for (const title of ["Applications by country", "Applications by university", "Staff performance"]) {
      expect(screen.getAllByText(title)).toHaveLength(1);
      const heading = screen.getByRole("heading", { level: 3, name: title });
      expect(screen.getByRole("region", { name: title })).toHaveAttribute("aria-labelledby", heading.id);
    }
    expect(container.querySelector("caption")).toBeNull();
  });

  it("lets the tables shrink to a phone and marks the tile links as links (QA18-03, QA18-04)", () => {
    const { container } = render(<AgentDashboardBoard data={master} />);
    expect([...container.querySelectorAll("table")].every((t) => t.classList.contains("compact"))).toBe(true);
    expect(screen.getByRole("link", { name: "View students" })).toHaveClass("kpi-link");
  });

  it("labels every staff-table number so a phone can stack each member's row (QA18-04)", () => {
    render(<AgentDashboardBoard data={master} />);
    const team = within(screen.getByRole("region", { name: "Staff performance" })).getByRole("table");
    expect(team).toHaveClass("stack");
    const firstRow = within(team).getAllByRole("row")[1];
    expect(within(firstRow).getAllByRole("cell").map((td) => td.getAttribute("data-label"))).toEqual(["Students", "Applications", "Offers", "Enrollments"]);
  });

  it("shows only the note when the agency has no staff, with the unassigned count in words (QA18-05)", () => {
    render(<AgentDashboardBoard data={{ ...master, staff: [], unassigned_students: 2 }} />);
    expect(screen.getByRole("link", { name: "add staff from Team" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Staff performance" })).toBeNull();
    expect(screen.getByText("2 students are not assigned to anyone yet.")).toBeInTheDocument();
  });

  it("shows Staff their own scope with no commission, staff table or reports link", () => {
    const { container } = render(<AgentDashboardBoard data={staff} />);
    expect(screen.getByText(/Your assigned students/)).toBeInTheDocument();
    expect(container.textContent?.toLowerCase()).not.toContain("commission");
    expect(screen.queryByRole("table", { name: "Staff performance" })).toBeNull();
    expect(screen.queryByRole("link", { name: "View reports" })).toBeNull();
  });

  it("shows zeros and empty notes for an empty agency", () => {
    const empty = { ...master, students: 0, applications: 0, by_country: breakdown([]), by_university: breakdown([]), staff: [], unassigned_students: 0 };
    render(<AgentDashboardBoard data={empty} />);
    expect(within(tile("Total students")).getByText("0")).toBeInTheDocument();
    expect(screen.getAllByText("No applications yet")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "add staff from Team" })).toHaveAttribute("href", "/overseas/agent/team");
  });
});

describe("AgentDashboardPanel (AGN-018)", () => {
  it("reads the dashboard endpoint", async () => {
    api.mockResolvedValue(staff);
    render(await AgentDashboardPanel());
    expect(api).toHaveBeenCalledWith("/api/v1/workflows/overseas/agent/crm/dashboard");
    expect(screen.getByText(/Your assigned students/)).toBeInTheDocument();
  });

  it("shows an inline error, never the error text, when the read fails", async () => {
    api.mockRejectedValue(new ApiError("boom: internal detail", 500));
    render(await AgentDashboardPanel());
    expect(screen.getByRole("alert")).toHaveTextContent("Dashboard figures are unavailable right now.");
    expect(screen.queryByText(/internal detail/)).toBeNull();
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/overseas/agent/dashboard");
  });

  it("shows the access card when the session has expired", async () => {
    api.mockRejectedValue(new ApiError("Not authenticated", 401));
    render(await AgentDashboardPanel());
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
  });

  it("has a busy skeleton with a spoken label", () => {
    const { container } = render(<AgentDashboardSkeleton />);
    expect(container.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(screen.getByText("Loading dashboard figures")).toBeInTheDocument();
  });
});
