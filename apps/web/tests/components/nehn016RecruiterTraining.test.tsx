import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateTraining from "@/components/RecruiterCandidateTraining";
import ReportView from "@/components/ReportView";
import type { CandidateTraining } from "@/lib/candidateTraining";
import { RECRUITER_MANAGER_NAV, RECRUITER_NAV } from "@/lib/navigation";
import type { CatalogueItem, Report } from "@/lib/reports";

// nehn-016 (DEC-SCOPE-312): the recruiter's Report library link, the "Completing within (days)" filter, and the read-only training panel
// on the candidate page -- its seats, the "—" for no attendance, readiness, the external candidate, and the load error with Retry.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const SEAT = {
  course: "Python Full Stack", batch: "PFS-Oct", trainer: "Ravi", starts: "2026-08-01", ends: "2026-11-07", status: "active", progress: 60,
  attendance_pct: 75, attendance_marked: 4, assignments_graded: 1, assignments_total: 2, assessments_passed: 0, assessments_total: 1,
  certificate: "Not issued",
};
const FULL: CandidateTraining = {
  student: true,
  seats: [SEAT, { ...SEAT, batch: "PFS-Old", ends: "2026-03-01", status: "dropped", attendance_pct: null, attendance_marked: 0, trainer: null }],
  readiness: { readiness_status: "ready", resume_status: "approved", mock_interview_status: "pending", aptitude_status: "pending", available: true },
};

let body: CandidateTraining;
let fails: boolean;
beforeEach(() => {
  body = FULL;
  fails = false;
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(fails ? res({ detail: "boom" }, 500) : res(body))));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("recruiter navigation (nehn-016)", () => {
  it("links recruiters and placement managers to their report library", () => {
    expect(RECRUITER_NAV).toContainEqual({ label: "Report library", href: "/recruiter/report-library" });
    expect(RECRUITER_MANAGER_NAV).toContainEqual({ label: "Report library", href: "/recruiter/manager/report-library" });
  });
});

describe("ReportView days filter (nehn-016)", () => {
  it("renders 'Completing within (days)' as a whole-number input keeping the address's value", () => {
    const item: CatalogueItem = { id: "completing-soon", title: "Students completing soon", description: "-", filters: ["days", "course_id"], can_download: true };
    const report: Report = {
      id: "completing-soon", title: "Students completing soon", description: "-", columns: [{ key: "student", label: "Student" }], items: [],
      total: 0, page: 1, page_size: 50, filters: item.filters, applied: { days: "30" }, options: {},
    };
    render(<ReportView item={item} report={report} error="" params={{ days: "30" }} basePath="/recruiter/report-library" />);
    const input = screen.getByLabelText("Completing within (days)") as HTMLInputElement;
    expect([input.type, input.min, input.max, input.step, input.value, input.placeholder]).toEqual(["number", "1", "365", "1", "30", "15"]);
  });
});

describe("RecruiterCandidateTraining (nehn-016)", () => {
  it("lists each seat with progress, attendance and the criteria, and the readiness", async () => {
    render(<RecruiterCandidateTraining candidateId="C1" />);
    const table = await screen.findByRole("table", { name: "Training progress" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Python Full Stack");
    expect(rows[0].textContent).toContain("PFS-Oct");
    expect(rows[0].textContent).toContain("60%");
    expect(rows[0].textContent).toContain("75%");
    expect(rows[0].textContent).toContain("1 / 2 graded");
    expect(rows[0].textContent).toContain("0 / 1 passed");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Course", "Trainer", "Ends", "Status", "Progress", "Attendance", "Assignments", "Assessments", "Certificate",
    ]);  // QA16-01: few and short enough to fit a desktop card
    expect(rows[0].textContent).toContain("Not issued");
    expect(rows[1].textContent).toContain("—");  // no attendance marked is "—", never 0 %
    expect(rows[1].textContent).toContain("Dropped");
    expect(screen.getByText(/Readiness/).closest("p")?.textContent).toContain("Ready");
    expect(fetch).toHaveBeenCalledWith("/api/v1/recruiter/candidates/C1/training", expect.anything());
    expect(screen.queryByRole("button")).toBeNull();  // read only: nothing to edit
  });

  it("says an external candidate has no EduSphere training", async () => {
    body = { student: false, seats: [], readiness: null };
    render(<RecruiterCandidateTraining candidateId="C1" />);
    expect(await screen.findByText("Not an EduSphere IT student — no training to show.")).toBeTruthy();
  });

  it("says a student with no enrolment has no training yet", async () => {
    body = { ...FULL, seats: [] };
    render(<RecruiterCandidateTraining candidateId="C1" />);
    expect(await screen.findByText("No course enrolments yet.")).toBeTruthy();
  });

  it("shows loading, then the error with Retry, then the panel", async () => {
    fails = true;
    render(<RecruiterCandidateTraining candidateId="C1" />);
    expect(screen.getByRole("status").textContent).toBe("Loading training progress…");
    expect((await screen.findByText("Unable to load training progress.")).getAttribute("role")).toBe("alert");
    fails = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("table", { name: "Training progress" })).toBeTruthy();
  });
});
