import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CounselorReportsPage from "@/app/overseas/counselor/reports/page";
import CounselorPerformance from "@/components/CounselorPerformance";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { CounselorPerformanceReport, PerformanceFigure } from "@/lib/counselorPerformance";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/overseas/counselor/reports" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const QUERY = { from: "2026-05-01", to: "2026-05-31" };
const counselor = { id: "c1", full_name: "Asha Rao", role: "counselor", division: "overseas" } as User;

const figure = (key: string, value: number | null, unit: PerformanceFigure["unit"] = "count"): PerformanceFigure => ({ key, label: `L:${key}`, definition: `D:${key}`, unit, value });

function report(over: Partial<CounselorPerformanceReport> = {}): CounselorPerformanceReport {
  return {
    from: "2026-05-01", to: "2026-05-31", as_of: "2026-05-20T05:00:00Z",
    period: [figure("leads_assigned", 1250), figure("conversion_pct", 33.3, "percent"), figure("follow_up_completion_pct", null, "percent")],
    now: [figure("overdue_tasks", 2), figure("applications", 5)],
    applications: {
      rows: [
        { stage: "enquiry", stage_label: "Enquiry", sub_status: null, sub_status_label: "Not set", applications: 1, students: 1 },
        { stage: "university_selection", stage_label: "University selection", sub_status: "documents_pending", sub_status_label: "Documents pending", applications: 2, students: 1 },
      ],
      total: { applications: 3, students: 2 },
      definitions: [{ key: "students", label: "Students", definition: "Distinct students." }],
    },
    ...over,
  }; // prettier-ignore
}

describe("ccrm-036 CounselorPerformance", () => {
  afterEach(cleanup);

  it("shows the period's figures and the figures now, each with its definition", () => {
    render(<CounselorPerformance data={report()} error="" query={QUERY} />);
    const period = screen.getByRole("list", { name: "In the period" });
    expect(within(period).getByText("L:leads_assigned").closest("li")).toHaveTextContent("1,250");
    expect(within(period).getByText("L:conversion_pct").closest("li")).toHaveTextContent("33.3%");
    expect(within(period).getByText("D:conversion_pct")).toBeInTheDocument();
    expect(within(period).getByText("L:follow_up_completion_pct").closest("li")).toHaveTextContent("No follow-ups due");
    const now = screen.getByRole("list", { name: "Now" });
    expect(within(now).getByText("L:overdue_tasks").closest("li")).toHaveTextContent("2");
    expect(screen.queryByText(/revenue/i)).toBeNull();
  });

  it("lists applications by stage and sub-status with a total, in a labelled scroll region", () => {
    render(<CounselorPerformance data={report()} error="" query={QUERY} />);
    const region = screen.getByRole("region", { name: "Applications by stage and sub-status" });
    const rows = within(region).getAllByRole("row");
    expect(rows[2]).toHaveTextContent("University selection");
    expect(rows[2]).toHaveTextContent("Documents pending");
    expect(within(region).getByRole("rowheader", { name: "Total" }).closest("tr")).toHaveTextContent("32");
    expect(screen.getByText("Distinct students.")).toBeInTheDocument();
  });

  it("says so when there are no applications", () => {
    render(<CounselorPerformance data={report({ applications: { rows: [], total: { applications: 0, students: 0 }, definitions: [] } })} error="" query={QUERY} />);
    expect(screen.getByRole("status")).toHaveTextContent("No applications are assigned to you yet.");
  });

  it("keeps the period form with the error when there is no data", () => {
    render(<CounselorPerformance data={null} error="The period must start on or before its end" query={QUERY} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    expect(screen.getByLabelText("From")).toHaveValue("2026-05-01");
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("href", "/overseas/counselor/reports");
  });
});

describe("ccrm-036 counselor Reports page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(user: User, result: CounselorPerformanceReport | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const value = path === "/api/v1/auth/me" ? user : path.startsWith("/api/v1/counselor/performance") ? result : (null as never);
      if (value instanceof Error) throw value;
      return value as never;
    });
  }

  it("reads the period from the address and renders in the counselor sidebar", async () => {
    answer(counselor, report());
    const tree = await CounselorReportsPage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/counselor/performance?from=2026-05-01&to=2026-05-31");
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toBe(PORTAL_NAV["overseas/counselor"]);
    render(tree);
    expect(screen.getByRole("heading", { name: "My performance" })).toBeInTheDocument();
  });

  it("refuses anyone but an overseas counselor without asking for the report", async () => {
    answer({ ...counselor, division: "it" } as User, report());
    render(await CounselorReportsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(serverApi).toHaveBeenCalledTimes(1);
  });

  it("shows the API's 422 message, and a generic message on a server error", async () => {
    answer(counselor, new ApiError("The period must start on or before its end", 422));
    render(await CounselorReportsPage({ searchParams: Promise.resolve({ from: "2026-05-31", to: "2026-05-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    cleanup();
    answer(counselor, new ApiError("Internal Server Error", 500));
    render(await CounselorReportsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Your performance figures are unavailable right now. Please try again.");
  });
});
