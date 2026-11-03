import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItCounselorDashboardPanel, { ItCounselorDashboardBoard, WIDGETS } from "@/components/ItCounselorDashboardPanel";
import ItCounselorDashboardFilters from "@/components/ItCounselorDashboardFilters";
import { ApiError, serverApi } from "@/lib/api";
import type { ItCounselorDashboard } from "@/lib/types";

// itc-030 (DEC-SCOPE-367): the IT counselor dashboard -- figure tiles, the nine widgets, their empty/overdue/"more" states, the filter
// form (values in the address, empty ones dropped) and the panel's 422 fallback and error card.
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/it/counselor/dashboard" }));
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
const api = vi.mocked(serverApi);
afterEach(() => {
  cleanup();
  api.mockReset();
  push.mockReset();
});

const none = { count: 0, more: false, items: [] };
function data(over: Partial<ItCounselorDashboard["widgets"]> = {}, filters: Partial<ItCounselorDashboard["filters"]> = {}): ItCounselorDashboard {
  return {
    filters: { program: null, batch: null, from: null, to: null, stage: null, owner: null, ...filters },
    options: {
      programs: [{ value: "p1", label: "Python" }, { value: "p2", label: "Java" }],
      batches: [{ value: "b1", label: "PY-1", program: "p1" }, { value: "b2", label: "JV-1", program: "p2" }],
      stages: [{ value: "qualified", label: "Qualified" }],
      owners: [],
    },
    today: "2026-11-03",
    widgets: {
      assigned_leads: none, follow_ups: { ...none, overdue: 0 }, pipeline: { count: 0, stages: [] }, conversions: none,
      enrolled_students: none, outstanding_fees: { ...none, total: 0 }, at_risk: none, pending_hr: none, ready_to_convert: none, ...over,
    },
  };
}
const region = (name: RegExp) => screen.getByRole("region", { name });

describe("ItCounselorDashboardBoard", () => {
  it("shows every widget with a zero count and its empty line (a counselor with nothing)", () => {
    render(<ItCounselorDashboardBoard data={data()} />);
    expect(WIDGETS).toHaveLength(8);
    for (const w of WIDGETS) expect(within(region(new RegExp(`^${w.title}`))).getByText(w.empty)).toBeTruthy();
    expect(within(region(/^Counseling pipeline/)).getByText("No open leads.")).toBeTruthy();
    expect(screen.getByText("INR 0.00")).toBeTruthy(); // the outstanding tile
  });

  it("lists items as links, flags overdue follow-ups and says when only the first ten show", () => {
    render(
      <ItCounselorDashboardBoard
        data={data({
          follow_ups: {
            count: 12, overdue: 1, more: true,
            items: [{ id: "f1", label: "Asha", detail: "Call back", date: "2026-11-01T05:30:00Z", overdue: true, href: "/it/counselor/leads/l1" }],
          },
          pipeline: { count: 3, stages: [{ stage: "qualified", label: "Qualified", count: 3 }] },
        })}
      />,
    );
    const follow = region(/^Follow-ups due today and overdue/);
    expect(within(follow).getByRole("link", { name: "Asha" }).getAttribute("href")).toBe("/it/counselor/leads/l1");
    expect(within(follow).getByText("Overdue")).toBeTruthy();
    expect(within(follow).getByText("Showing 1 of 12")).toBeTruthy();
    expect(screen.getByText(/^1 overdue/)).toBeTruthy();
    expect(within(region(/^Counseling pipeline/)).getByText("Qualified")).toBeTruthy();
  });

  it("notes that the stage filter leaves the student widgets alone", () => {
    render(<ItCounselorDashboardBoard data={data({}, { stage: "qualified" })} />);
    expect(screen.getByText(/Status filters the lead widgets only/)).toBeTruthy();
  });
});

describe("ItCounselorDashboardFilters", () => {
  it("pushes only the chosen filters into the address and narrows batches to the course", () => {
    render(<ItCounselorDashboardFilters filters={data().filters} options={data().options} />);
    fireEvent.change(screen.getByLabelText("Course"), { target: { value: "p1" } });
    const batch = screen.getByLabelText("Batch");
    expect(within(batch).queryByText("JV-1")).toBeNull();
    fireEvent.change(batch, { target: { value: "b1" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-11-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(push).toHaveBeenCalledWith("/it/counselor/dashboard?program=p1&batch=b1&from=2026-11-01");
    expect(screen.queryByLabelText("Owner")).toBeNull(); // the IT Admin's only
  });

  it("clears back to the plain dashboard and shows a refused filter's message", () => {
    render(<ItCounselorDashboardFilters filters={data({}, { program: "p1" }).filters} options={data().options} error="Unknown filter value" />);
    expect(screen.getByRole("alert").textContent).toBe("Unknown filter value");
    expect(screen.getByRole("link", { name: "Clear filters" }).getAttribute("href")).toBe("/it/counselor/dashboard");
  });

  it("offers the owner picker to the IT Admin", () => {
    const options = { ...data().options, owners: [{ value: "c1", label: "Counselor One" }] };
    render(<ItCounselorDashboardFilters filters={data().filters} options={options} />);
    expect(within(screen.getByLabelText("Owner")).getByText("Counselor One")).toBeTruthy();
  });
});

describe("ItCounselorDashboardPanel", () => {
  it("falls back to the unfiltered board with the message on a refused filter", async () => {
    api.mockRejectedValueOnce(new ApiError("Unknown filter value", 422)).mockResolvedValueOnce(data());
    render(await ItCounselorDashboardPanel({ query: "program=x" }));
    expect(api).toHaveBeenNthCalledWith(1, "/api/v1/counselor/it/dashboard?program=x");
    expect(api).toHaveBeenNthCalledWith(2, "/api/v1/counselor/it/dashboard");
    expect(screen.getByRole("alert").textContent).toBe("Unknown filter value");
  });

  it("shows an error card when the board cannot be read", async () => {
    api.mockRejectedValueOnce(new ApiError("Only an IT counselor or the IT Admin has this dashboard", 403));
    render(await ItCounselorDashboardPanel({ query: "" }));
    expect(screen.getByRole("alert").textContent).toBe("The dashboard is unavailable right now.");
  });
});
