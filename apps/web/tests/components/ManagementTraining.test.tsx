import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementTrainingPage from "@/app/management/training/page";
import ManagementTraining from "@/components/ManagementTraining";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import type { TrainerRow, TrainingDashboard, TrainingKpi } from "@/lib/managementTraining";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/training" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Priya Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Sam Admin", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const QUERY = { from: "2026-05-01", to: "2026-05-31" };
const KPI_LABELS = [
  "Total courses", "Active batches", "Students", "Trainers", "Attendance", "Completion", "Dropouts", "Assessments", "Certifications",
  "Placement-ready students", "Placements",
]; // prettier-ignore

function dashboard(over: Partial<TrainingDashboard> = {}): TrainingDashboard {
  const values: Record<string, number | null> = {
    total_courses: 6, active_batches: 4, students: 1250, trainers: 3, attendance_pct: 87.5, completion_pct: 40, dropouts: 2, assessments: 5,
    certifications: 12, placement_ready: 9, placements: 3,
  }; // prettier-ignore
  const keys = Object.keys(values);
  const meera: TrainerRow = {
    id: "t1", full_name: "Meera Iyer", active: true, batches: 2, students_trained: 1100, attendance_pct: 75, completion_pct: 33.3, feedback_avg: 4,
    feedback_count: 3, assessment_pass_pct: 66.7, batch_performance: 76.7, placements: 1,
  }; // prettier-ignore
  const ravi: TrainerRow = {
    id: "t2", full_name: "Ravi Kumar", active: false, batches: 0, students_trained: 0, attendance_pct: null, completion_pct: null, feedback_avg: null,
    feedback_count: 0, assessment_pass_pct: null, batch_performance: null, placements: 0,
  }; // prettier-ignore
  return {
    from: "2026-05-01", to: "2026-05-31", as_of: "2026-10-13T05:00:00Z",
    kpis: keys.map((key, i) => ({ key, label: KPI_LABELS[i], definition: `About ${KPI_LABELS[i]}.`, value: values[key] }) as TrainingKpi),
    trainer_figures: [
      { key: "students_trained", label: "Students trained", definition: "" }, { key: "attendance_pct", label: "Attendance", definition: "" },
      { key: "completion_pct", label: "Completion", definition: "" }, { key: "feedback_avg", label: "Student feedback", definition: "" },
      { key: "assessment_pass_pct", label: "Assessment results", definition: "" }, { key: "batch_performance", label: "Batch performance", definition: "" },
      { key: "placements", label: "Placement outcomes", definition: "" },
    ],
    trainers: [meera, ravi],
    ...over,
  }; // prettier-ignore
}

function view(props: Partial<Parameters<typeof ManagementTraining>[0]> = {}) {
  return render(<ManagementTraining data={dashboard()} error="" query={QUERY} {...props} />);
}

const tiles = () => screen.getByRole("list", { name: "Training KPIs" });
const tile = (label: string) => within(tiles()).getByText(label, { selector: "span" }).closest("li")!;

describe("mgmt-017 ManagementTraining", () => {
  afterEach(cleanup);

  it("shows the eleven §12 KPIs in source order, counts with Indian grouping and shares to one decimal", () => {
    view();
    expect(within(tiles()).getAllByRole("listitem").map((li) => li.querySelector("span")!.textContent)).toEqual(KPI_LABELS);
    expect(tile("Students")).toHaveTextContent("1,250");
    expect(tile("Attendance")).toHaveTextContent("87.5%");
    expect(tile("Completion")).toHaveTextContent("40.0%");
    expect(tile("Placements")).toHaveTextContent("About Placements.");
  });

  it("says why a share is missing instead of showing 0", () => {
    const empty = dashboard();
    empty.kpis = empty.kpis.map((k) => (k.key === "attendance_pct" || k.key === "completion_pct" ? { ...k, value: null } : k));
    view({ data: empty });
    expect(within(tile("Attendance")).getByText("Nothing marked")).toHaveClass("metric-untracked");
    expect(within(tile("Completion")).getByText("No seats taken")).toHaveClass("metric-untracked");
  });

  it("lists every trainer with the seven §12 metrics, a dash where there is nothing to show", () => {
    view();
    const table = screen.getByRole("table", { name: "Trainer performance" });
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Trainer", "Batches", "Students trained", "Attendance", "Completion", "Student feedback", "Assessment results", "Batch performance", "Placement outcomes",
    ]); // prettier-ignore
    const meera = within(table).getByRole("rowheader", { name: "Meera Iyer" }).closest("tr")!;
    expect(Array.from(meera.querySelectorAll("td")).map((td) => td.textContent)).toEqual(["2", "1,100", "75.0%", "33.3%", "4.0 / 5 (3)", "66.7%", "76.7%", "1"]);
    const ravi = within(table).getByRole("rowheader", { name: /Ravi Kumar/ }).closest("tr")!;
    expect(ravi).toHaveTextContent("Inactive");
    expect(Array.from(ravi.querySelectorAll("td")).map((td) => td.textContent)).toEqual(["0", "0", "—", "—", "—", "—", "—", "0"]);
    expect(screen.getByRole("heading", { name: "Trainer performance" }).closest("section")).toHaveAttribute("id", "trainers");
  });

  it("names the period and the trainers, in a GET period form", () => {
    view();
    // QA17-01: the note counts every trainer account and names the inactive ones, so it agrees with the Trainers tile (active only).
    expect(screen.getByText(new RegExp(`^${formatCalendarDate("2026-05-01")} to ${formatCalendarDate("2026-05-31")}`))).toHaveTextContent("2 trainer accounts, 1 inactive.");
    const form = screen.getByRole("form", { name: "Choose a period" });
    expect(form).toHaveAttribute("method", "get");
    expect(within(form).getByLabelText("From")).toHaveValue("2026-05-01");
    expect(within(form).getByLabelText("To")).toHaveValue("2026-05-31");
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("href", "/management/training");
  });

  it("says so when there are no trainers yet", () => {
    view({ data: dashboard({ trainers: [] }) });
    expect(screen.getByRole("status")).toHaveTextContent("No trainer accounts yet");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText(/0 trainer accounts\./)).toBeInTheDocument();
  });

  it("shows an error without figures", () => {
    view({ data: null, error: "The period must start on or before its end" });
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    expect(screen.queryByRole("list", { name: "Training KPIs" })).toBeNull();
    expect(screen.getByRole("form", { name: "Choose a period" })).toBeInTheDocument();
  });
});

describe("mgmt-017 Training dashboard page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(me: ManagementMe, result: TrainingDashboard | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const value = path === "/api/v1/management/me" ? me : path.startsWith("/api/v1/management/training") ? result : (null as never);
      if (value instanceof Error) throw value;
      return value as never;
    });
  }

  it("asks for the period in the address and renders in the Command Center sidebar", async () => {
    answer(partner, dashboard());
    const tree = await ManagementTrainingPage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/training?from=2026-05-01&to=2026-05-31");
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toContainEqual({ label: "Training", href: "/management/training" });
    render(tree);
    expect(screen.getByRole("heading", { name: "Training dashboard" })).toBeInTheDocument();
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin, dashboard());
    const tree = await ManagementTrainingPage({ searchParams: Promise.resolve({}) });
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the API's 422 message, a generic message on a server error, and the access card when refused", async () => {
    answer(partner, new ApiError("The period must start on or before its end", 422));
    render(await ManagementTrainingPage({ searchParams: Promise.resolve({ from: "2026-05-31", to: "2026-05-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    cleanup();
    answer(partner, new ApiError("Internal Server Error", 500));
    render(await ManagementTrainingPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Training figures are unavailable right now. Please try again.");
    cleanup();
    answer(partner, new ApiError("Operational access required", 403));
    render(await ManagementTrainingPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
  });
});
