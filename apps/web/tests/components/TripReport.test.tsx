import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagerTripReport from "@/app/bdm/manager/trips/[id]/report/page";
import TripReportPage from "@/app/bdm/travel/[id]/report/page";
import TripReport, { ReportTitle } from "@/components/TripReport";
import { ApiError, serverApi } from "@/lib/api";
import { elements, text } from "@/tests/helpers/elementTree";

import { metrics, trip } from "./tripFixtures";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));
vi.mock("@/lib/bdmNav", () => ({ bdmNav: async () => [], bdmManagerNav: async () => [] }));

const UUID = "9184f803-d155-4ec1-8008-8d65ff92412d";
const route = (id = UUID) => ({ params: Promise.resolve({ id }) });
const me = { id: "b1", full_name: "Asha", bdm_profile: { bdm_type: "college" } };
const manager = { id: "m1", full_name: "Meera", role: "bdm_manager" };
const done = (over = {}) => trip({
  id: UUID, approval_status: "approved", travel_status: "completed", completed_at: "2026-10-12T10:00:00Z", remarks: "Two colleges keen.",
  actual_cost: "1650.50", metrics: metrics({ meetings_planned: 2, meetings_completed: 1, actual_cost: "1650.50" }),
  expenses: [
    { id: "e1", category: "travel", amount: "1200.00", expense_date: "2026-10-10", note: null },
    { id: "e2", category: "food", amount: "250.50", expense_date: "2026-10-10", note: null },
    { id: "e3", category: "food", amount: "200.00", expense_date: "2026-10-11", note: null },
  ],
  ...over,
});
const allText = (node: unknown) => elements(node as never).map((el) => text(el)).join(" ");

function answer(byPath: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const key = Object.keys(byPath).find((k) => path.startsWith(k));
    if (!key) throw new Error(`unexpected ${path}`);
    const value = byPath[key];
    if (value instanceof Error) throw value;
    return value as never;
  });
}

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(cleanup);

describe("TripReport (bdm-011 AC3)", () => {
  it("summarises the trip: details, appointments, productivity, expenses by category with the total, and the remarks", () => {
    render(<TripReport trip={done()} view="owner" />);
    for (const name of ["Trip details", "Appointments", "Productivity", "Expenses by category", "Remarks"]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
    const table = screen.getByRole("table", { name: "Expenses by category" });
    const rows = within(table).getAllByRole("row").slice(1).map((r) => Array.from(r.children).map((c) => c.textContent));
    expect(rows).toEqual([["Travel", "₹1,200.00"], ["Food", "₹450.50"], ["Total", "₹1,650.50"]]);
    expect(within(table).getByRole("rowheader", { name: "Total" })).toHaveStyle({ textAlign: "left" }); // QA11-03
    expect(screen.getByText("Two colleges keen.")).toBeInTheDocument();
  });

  it("says when there were no expenses or remarks", () => {
    render(<TripReport trip={done({ expenses: [], remarks: null })} view="owner" />);
    expect(screen.getByText("No expenses were recorded.")).toBeInTheDocument();
    expect(screen.getByText("No remarks were added.")).toBeInTheDocument();
  });
});

// The page tree is asserted without rendering (elementTree): ReportTitle carries the way back to the trip.
const backHref = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === ReportTitle)?.props.tripHref;

describe("travel report pages (bdm-011)", () => {
  it("the BDM's report reads the report endpoint and links back to the trip", async () => {
    answer({ "/api/v1/bdm/me": me, [`/api/v1/bdm/trips/${UUID}/report`]: done() });
    const tree = elements(await TripReportPage(route()));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/trips/${UUID}/report`);
    expect(tree.find((el) => el.type === TripReport)?.props.view).toBe("owner");
    expect(backHref(tree)).toBe(`/bdm/travel/${UUID}`);
  });

  it("before completion it says when the report will be available", async () => {
    answer({ "/api/v1/bdm/me": me, [`/api/v1/bdm/trips/${UUID}/report`]: new ApiError("The travel report is available once the trip is completed", 409) });
    const page = await TripReportPage(route());
    expect(allText(page)).toContain("The travel report is available once the trip is completed");
    expect(elements(page).some((el) => el.type === TripReport)).toBe(false);
    expect(backHref(elements(page))).toBe(`/bdm/travel/${UUID}`);
  });

  it("a malformed link is Trip not found without asking for the trip", async () => {
    answer({ "/api/v1/auth/me": me });
    const card = elements(await TripReportPage(route("nope"))).find((el) => typeof el.props.message === "string")!;
    expect(card.props.message).toBe("Trip not found");
    expect(vi.mocked(serverApi).mock.calls.map((c) => c[0]).some((p) => p.includes("/trips/"))).toBe(false);
  });

  it("the manager's report reads the team endpoint", async () => {
    answer({ "/api/v1/auth/me": manager, [`/api/v1/bdm/manager/trips/${UUID}/report`]: done() });
    const tree = elements(await ManagerTripReport(route()));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/manager/trips/${UUID}/report`);
    expect(tree.find((el) => el.type === TripReport)?.props.view).toBe("manager");
    expect(backHref(tree)).toBe(`/bdm/manager/trips/${UUID}`);
  });
});
