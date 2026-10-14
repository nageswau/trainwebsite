import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementUniversitiesPage from "@/app/management/universities/page";
import ManagementUniversities from "@/components/ManagementUniversities";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { UniversitiesDashboard } from "@/lib/managementUniversities";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { ExpectedRow } from "@/lib/partnershipExpected";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/universities" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Priya Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Sam Admin", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const QUERY = { from: "2026-05-01", to: "2026-05-31" };
const LABELS = ["Universities identified", "Contacted", "Meetings", "Negotiations", "MoUs", "Signed", "Active", "Exclusive", "Countries", "Applications", "Enrollments"];
const KEYS = ["identified", "contacted", "meetings", "negotiations", "mous", "signed", "active", "exclusive", "countries", "applications", "enrollments"];
const STEPS = ["Identified", "Contacted", "Meeting", "Proposal", "Negotiation", "Agreement", "Signed", "Active Partner"];

const row = (over: Partial<ExpectedRow> = {}): ExpectedRow => ({
  university: { id: "u1", university_code: "UNI-0001", name: "Northbridge University" }, country: "United Kingdom", stage: "interested",
  stage_label: "Interested", expected_agreement_date: "2026-06-12", owner: { id: "m1", full_name: "Rahul Partnerships" }, probability: 40,
  stage_probability: 40, override_reason: null, ...over,
}); // prettier-ignore

function dashboard(over: Partial<UniversitiesDashboard> = {}): UniversitiesDashboard {
  return {
    today: "2026-05-20", from: "2026-05-01", to: "2026-05-20",
    kpis: KEYS.map((key, i) => ({ key, label: LABELS[i], value: i === 0 ? 1200 : i })),
    revenue: { expected: [{ currency: "GBP", amount: "5400.00" }], received: [{ currency: "GBP", amount: "2700.00" }] },
    pipeline: { steps: STEPS.map((label, i) => ({ key: `s${i}`, label, count: i + 1 })), lost: 2, total: 38 },
    expected: {
      windows: [
        { key: "this_month", label: "This month", first: "2026-05-01", last: "2026-05-31", count: 3, weighted: 1.2 },
        { key: "next_month", label: "Next month", first: "2026-06-01", last: "2026-06-30", count: 1, weighted: 0.4 },
        { key: "this_quarter", label: "This quarter", first: "2026-04-01", last: "2026-06-30", count: 4, weighted: 1.6 },
      ],
      undated: 5,
      next_month: { total: 1, items: [row()] },
    },
    ...over,
  }; // prettier-ignore
}

const tiles = () => within(screen.getByRole("list", { name: "University partnership KPIs" })).getAllByRole("listitem");

describe("mgmt-023 ManagementUniversities", () => {
  afterEach(cleanup);

  it("shows the twelve §19 KPIs in source order, Revenue last, for a partner", () => {
    render(<ManagementUniversities data={dashboard()} error="" query={QUERY} />);
    const items = tiles();
    expect(items.map((li) => li.querySelector("span")!.textContent)).toEqual([...LABELS, "Revenue"]);
    expect(items[0]).toHaveTextContent("1,200");
    expect(items[11]).toHaveTextContent("GBP 2,700.00");
    expect(items[11]).toHaveTextContent("Commission received in the period"); // QA23-01
    expect(items[11]).toHaveTextContent("Expected: GBP 5,400.00");
  });

  it("has no Revenue tile when the API sends none (super_admin, M13)", () => {
    render(<ManagementUniversities data={dashboard({ revenue: undefined })} error="" query={QUERY} />);
    expect(tiles()).toHaveLength(11);
    expect(screen.queryByText("Revenue")).toBeNull();
    expect(screen.queryByText(/GBP/)).toBeNull();
  });

  it("lists the eight-step pipeline with lost/closed apart", () => {
    render(<ManagementUniversities data={dashboard()} error="" query={QUERY} />);
    const steps = within(screen.getByRole("list", { name: "Partnership pipeline" })).getAllByRole("listitem");
    expect(steps.map((li) => li.querySelector(".funnel-label")!.textContent)).toEqual(STEPS);
    expect(steps[7]).toHaveTextContent("8");
    expect(screen.getByText(/2 lost \/ closed are not in a step; 38 universities in all/)).toHaveClass("universities-lost"); // QA23-02: spaced from the last step
  });

  it("shows the expected windows and the universities expected to sign next month", () => {
    render(<ManagementUniversities data={dashboard()} error="" query={QUERY} />);
    const windows = within(screen.getByRole("list", { name: "Expected partnerships" })).getAllByRole("listitem");
    expect(windows.map((li) => li.textContent)).toEqual(["This month3Weighted forecast 1.2", "Next month1Weighted forecast 0.4", "This quarter4Weighted forecast 1.6"]);
    const table = screen.getByRole("table", { name: "Universities expected to sign next month" });
    const cells = within(table).getAllByRole("row")[1];
    expect(cells).toHaveTextContent("Northbridge University");
    expect(cells).toHaveTextContent("United Kingdom");
    expect(cells).toHaveTextContent("Interested");
    expect(cells).toHaveTextContent("12 Jun 2026");
    expect(cells).toHaveTextContent("Rahul Partnerships");
    expect(cells).toHaveTextContent("40%");
    expect(screen.getByText(/5 in progress have no expected date/)).toBeInTheDocument();
  });

  it("says when nobody is expected next month, and when the list is cut", () => {
    const { rerender } = render(<ManagementUniversities data={dashboard({ expected: { ...dashboard().expected, next_month: { total: 0, items: [] } } })} error="" query={QUERY} />);
    expect(screen.getByRole("status")).toHaveTextContent("No universities are expected to sign next month.");
    rerender(<ManagementUniversities data={dashboard({ expected: { ...dashboard().expected, next_month: { total: 30, items: [row()] } } })} error="" query={QUERY} />);
    expect(screen.getByText("Showing 1 of 30, earliest expected date first.")).toBeInTheDocument();
  });

  it("holds the period in a GET form keyed on the address and shows the API's error", () => {
    render(<ManagementUniversities data={null} error="The period must start on or before its end" query={QUERY} />);
    expect(screen.getByText("The period must start on or before its end")).toHaveClass("form-error");
    const form = screen.getByRole("form", { name: "Universities period" });
    expect(form).toHaveAttribute("method", "get");
    expect(screen.getByLabelText("From")).toHaveValue("2026-05-01");
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("href", "/management/universities");
    expect(screen.queryByRole("list", { name: "University partnership KPIs" })).toBeNull();
  });

  it("fills the inputs from the API's period when the address has none", () => {
    render(<ManagementUniversities data={dashboard()} error="" query={{ from: "", to: "" }} />);
    expect(screen.getByLabelText("From")).toHaveValue("2026-05-01");
    expect(screen.getByLabelText("To")).toHaveValue("2026-05-20");
    expect(screen.queryByRole("link", { name: "This month" })).toBeNull();
  });
});

describe("mgmt-023 ManagementUniversitiesPage", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });

  it("gives the super admin their own sidebar and reads the period from the address", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/management/me" ? superAdmin : dashboard({ revenue: undefined })) as never);
    const tree = await ManagementUniversitiesPage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31" }) });
    expect(vi.mocked(serverApi)).toHaveBeenCalledWith("/api/v1/management/universities?from=2026-05-01&to=2026-05-31");
    const shell = elements(tree).find((el) => el.type === PortalShell)!;
    expect((shell.props as { nav: unknown }).nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the API's 422 words, and an unavailable notice otherwise", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/me") return partner as never;
      throw new ApiError("A period can be at most 366 days", 422);
    });
    let tree = await ManagementUniversitiesPage({ searchParams: Promise.resolve({}) });
    let view = elements(tree).find((el) => el.type === ManagementUniversities)!;
    expect((view.props as { error: string }).error).toBe("A period can be at most 366 days");
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/me") return partner as never;
      throw new ApiError("boom", 500);
    });
    tree = await ManagementUniversitiesPage({ searchParams: Promise.resolve({}) });
    view = elements(tree).find((el) => el.type === ManagementUniversities)!;
    expect((view.props as { error: string }).error).toBe("University partnership figures are unavailable right now. Please try again.");
  });
});
