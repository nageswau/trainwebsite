import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentDashboardPanel, { AgentDashboardBoard } from "@/components/AgentDashboardPanel";
import { ApiError, serverApi } from "@/lib/api";
import { dashboardRange } from "@/lib/agentDashboard";
import type { AgentDashboard } from "@/lib/types";

// nehn-038 (DEC-SCOPE-306): applications submitted, the visa outcome split, conversion, and the referral-date filter.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
const api = vi.mocked(serverApi);
afterEach(() => {
  cleanup();
  api.mockReset();
});

const NONE = { from: "", to: "" };
const data: AgentDashboard = {
  scope: "agency",
  member_code: "ABC-M001",
  students: 4,
  applications: 5,
  offers: 4,
  visa_applications: 4,
  visa_approvals: 1,
  enrollments: 3,
  pending_documents: 0,
  pending_actions: 1,
  applications_submitted: 5,
  visa_decisions: 3,
  visa_refusals: 1,
  visa_withdrawals: 1,
  conversions: 2,
  conversion_rate: 33.3,
  date_from: null,
  date_to: null,
  by_country: { items: [], other: 0 },
  by_university: { items: [], other: 0 },
  staff: [
    { code: "ABC-S001", name: "Staff A", active: true, students: 2, applications: 3, offers: 2, enrollments: 1, conversions: 1, conversion_rate: 50 },
    { code: "ABC-S002", name: "Staff B", active: true, students: 0, applications: 0, offers: 0, enrollments: 0, conversions: 0, conversion_rate: null },
  ],
  unassigned_students: 1,
  commission: { claimable: [], claims: 0, revenue: [] },
  reports_available: false,
  as_of: "2026-10-27T00:00:00Z",
};

function tile(label: string) {
  return screen.getByText(label, { selector: "dt" }).closest(".kpi-tile") as HTMLElement;
}

describe("AgentDashboardBoard KPIs (nehn-038)", () => {
  it("shows applications submitted, the visa outcome split and conversion", () => {
    render(<AgentDashboardBoard data={data} range={NONE} />);
    const expected: [string, string][] = [
      ["Applications submitted", "5"], ["Visa decisions", "3"], ["Visa approvals", "1"], ["Visa refusals", "1"], ["Visa withdrawals", "1"],
      ["Conversions", "2"], ["Conversion rate", "33.3%"],
    ];
    for (const [label, value] of expected) expect(tile(label).querySelector(".kpi-value")?.textContent).toBe(value);
    expect(within(screen.getByRole("region", { name: "Visa outcomes" })).getByText("Visa decisions")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Conversion" })).getByText("Conversion rate")).toBeInTheDocument();
  });

  it("shows a dash, not 0%, when there are no students to convert", () => {
    render(<AgentDashboardBoard data={{ ...data, students: 0, conversions: 0, conversion_rate: null }} range={NONE} />);
    expect(tile("Conversion rate").querySelector(".kpi-value")?.textContent).toBe("—");
  });

  it("adds each staff member's conversions and rate to the staff table", () => {
    render(<AgentDashboardBoard data={data} range={NONE} />);
    const team = within(screen.getByRole("region", { name: "Staff performance" })).getByRole("table");
    const [, a, b] = within(team).getAllByRole("row");
    expect(within(a).getAllByRole("cell").map((td) => [td.getAttribute("data-label"), td.textContent])).toEqual([
      ["Students", "2"], ["Applications", "3"], ["Offers", "2"], ["Enrollments", "1"], ["Conversions", "1"], ["Conversion rate", "50%"],
    ]);
    expect(within(b).getByText("—")).toHaveAttribute("data-label", "Conversion rate");
  });

  it("has a labelled GET date filter that keeps the applied range", () => {
    render(<AgentDashboardBoard data={{ ...data, date_from: "2026-03-01", date_to: "2026-03-31" }} range={{ from: "2026-03-01", to: "2026-03-31" }} />);
    const form = screen.getByRole("form", { name: "Dashboard date range" });
    expect(form).toHaveAttribute("method", "get");
    expect(form).toHaveAttribute("action", "/overseas/agent/dashboard");
    expect(within(form).getByLabelText("Referred from")).toHaveValue("2026-03-01");
    expect(within(form).getByLabelText("Referred to")).toHaveAttribute("name", "to");
    expect(within(form).getByRole("button", { name: "Apply" })).toHaveAttribute("type", "submit");
    expect(screen.getByRole("link", { name: "Clear dates" })).toHaveAttribute("href", "/overseas/agent/dashboard");
    expect(screen.getByText(/Students referred 2026-03-01 to 2026-03-31/)).toBeInTheDocument();
    expect(screen.getByText(/Pending documents, pending actions and commission are current/)).toBeInTheDocument();
  });

  it("never lets the browser restore typed dates over the applied range on Back (QA38-01)", () => {
    render(<AgentDashboardBoard data={data} range={NONE} />);
    expect(screen.getByRole("form", { name: "Dashboard date range" })).toHaveAttribute("autocomplete", "off");
  });

  it("tells staff which figures are current in a sentence without commission (QA38-02)", () => {
    render(<AgentDashboardBoard data={{ ...data, scope: "own", staff: null, commission: null }} range={NONE} />);
    expect(screen.getByText(/Pending documents and pending actions are current, whatever the dates\./)).toBeInTheDocument();
  });

  it("offers no Clear link and says 'at any time' without a range", () => {
    render(<AgentDashboardBoard data={data} range={NONE} />);
    expect(screen.queryByRole("link", { name: "Clear dates" })).toBeNull();
    expect(screen.getByText(/Students referred at any time/)).toBeInTheDocument();
  });
});

describe("AgentDashboardPanel range (nehn-038)", () => {
  it("passes the range to the endpoint", async () => {
    api.mockResolvedValue(data);
    render(await AgentDashboardPanel({ range: { from: "2026-03-01", to: "" } }));
    expect(api).toHaveBeenCalledWith("/api/v1/workflows/overseas/agent/crm/dashboard?date_from=2026-03-01");
  });

  it("shows a rejected range as a field message and keeps the form", async () => {
    api.mockRejectedValue(new ApiError("date_to must be on or after date_from", 422));
    render(await AgentDashboardPanel({ range: { from: "2026-03-31", to: "2026-03-01" } }));
    expect(screen.getByRole("alert")).toHaveTextContent("'Referred to' must be on or after 'Referred from'");
    expect(screen.getByLabelText("Referred from")).toHaveValue("2026-03-31");
    expect(screen.getByRole("link", { name: "Clear dates" })).toBeInTheDocument();
  });
});

describe("dashboardRange (nehn-038)", () => {
  it("reads well-formed dates from the page query and drops the rest", () => {
    expect(dashboardRange({ from: "2026-03-01", to: ["2026-03-31", "x"] })).toEqual({ from: "2026-03-01", to: "2026-03-31" });
    expect(dashboardRange({ from: "03/01/2026", to: undefined })).toEqual(NONE);
    expect(dashboardRange(undefined)).toEqual(NONE);
  });
});
