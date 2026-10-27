import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalSection from "@/components/PortalSection";
import TrainerProgressPanel from "@/components/TrainerProgressPanel";

// nehn-028 (DEC-SCOPE-305): the trainer's per-student progress table -- attendance with a risk flag, assignments, assessments, progress
// and certificate eligibility with its reasons, for one batch at a time.
const URL = (id: string) => `/api/v1/workflows/it/batches/${id}/progress`;
const RULES = { min_progress_percent: 100, min_attendance_percent: 75 };
const BATCHES = [{ id: "b1", name: "Batch A" }, { id: "b2", name: "Batch B" }];
const student = (over: Record<string, unknown>) => ({
  enrollment_id: "e1", student_id: "s1", student_code: "ST0001", student: "Asha Rao", enrollment_code: "EDU-1", status: "active",
  progress_percent: 40, attendance_percent: 50, attendance_sessions: 4, at_risk: true,
  assignments_submitted: 2, assignments_graded: 1, assignments_total: 3, assessments_passed: 0, assessments_total: 1,
  fee_clear: true, eligible: false, reasons: ["Progress 40% (needs 100%)", "Attendance 50% (needs 75%)"], certificate_issued: false, ...over,
});
const STUDENTS = [
  student({}),
  student({ enrollment_id: "e2", student_id: "s2", student_code: "ST0002", student: "Bala Iyer", enrollment_code: "EDU-2", attendance_percent: 100, at_risk: false, progress_percent: 100, eligible: true, reasons: [] }),
  student({ enrollment_id: "e3", student_id: "s3", student_code: "ST0003", student: "Chitra Das", enrollment_code: "EDU-3", attendance_percent: 0, attendance_sessions: 0, at_risk: false, reasons: ["No attendance recorded yet"] }),
  student({ enrollment_id: "e4", student_id: "s4", student_code: "ST0004", student: "Dev Menon", enrollment_code: "EDU-4", status: "dropped", at_risk: true }),
];
const payload = (students: unknown[]) => ({ batch: { id: "b1", name: "Batch A", program: "Java", start_date: "2026-01-01", end_date: "2026-03-01" }, rules: RULES, students });
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function stub(routes: Record<string, () => Promise<Response>>) {
  const mock = vi.fn((url: string) => (routes[url] ?? (() => json({ detail: "not stubbed" }, 500)))());
  vi.stubGlobal("fetch", mock);
  return mock;
}

const rowOf = (name: string) => screen.getByRole("row", { name: new RegExp(name) });
const names = () => screen.getAllByRole("rowheader").map(cell => cell.textContent?.replace(/ST\d+.*/, "").trim());

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TrainerProgressPanel", () => {
  it("shows each factor for the first batch, flags at-risk students and hides dropped ones", async () => {
    const mock = stub({ [URL("b1")]: () => json(payload(STUDENTS)) });
    render(<TrainerProgressPanel batches={BATCHES} />);
    const asha = await screen.findByRole("row", { name: /Asha Rao/ });
    expect(mock).toHaveBeenCalledWith(URL("b1"));
    expect(within(asha).getByText("50%")).toBeTruthy();
    expect(within(asha).getByText("At risk")).toBeTruthy();
    expect(within(asha).getByText("2 / 1 / 3")).toBeTruthy(); // submitted / graded / total
    expect(within(asha).getByText("0 / 1")).toBeTruthy();
    expect(within(asha).getByText("40%")).toBeTruthy();
    expect(within(asha).getByText("Not eligible")).toBeTruthy();
    expect(within(rowOf("Bala Iyer")).getByText("Eligible")).toBeTruthy();
    expect(within(rowOf("Bala Iyer")).queryByText("At risk")).toBeNull();
    expect(within(rowOf("Chitra Das")).getByText("—")).toBeTruthy(); // no sessions yet: no %, no flag
    expect(within(rowOf("Chitra Das")).queryByText("At risk")).toBeNull();
    expect(screen.queryByRole("row", { name: /Dev Menon/ })).toBeNull();
    expect(screen.getByText("1 of 3 students below 75% attendance")).toBeTruthy();
  });

  it("shows dropped students greyed on request, and filters to at-risk only", async () => {
    stub({ [URL("b1")]: () => json(payload(STUDENTS)) });
    render(<TrainerProgressPanel batches={BATCHES} />);
    await screen.findByRole("row", { name: /Asha Rao/ });
    fireEvent.click(screen.getByLabelText("Show dropped and withdrawn"));
    const dev = rowOf("Dev Menon");
    expect(dev.className).toContain("inactive");
    expect(within(dev).getByText("Dropped")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("At risk only"));
    expect(names()).toEqual(["Asha Rao", "Dev Menon"]);
  });

  it("searches by name or student code and sorts by attendance", async () => {
    stub({ [URL("b1")]: () => json(payload(STUDENTS)) });
    render(<TrainerProgressPanel batches={BATCHES} />);
    await screen.findByRole("row", { name: /Asha Rao/ });
    fireEvent.change(screen.getByLabelText("Search students"), { target: { value: "st0002" } });
    expect(names()).toEqual(["Bala Iyer"]);
    fireEvent.change(screen.getByLabelText("Search students"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /Attendance/ }));
    expect(names()).toEqual(["Chitra Das", "Asha Rao", "Bala Iyer"]); // no sessions sorts first (lowest), then 50%, 100%
    expect(screen.getByRole("columnheader", { name: /Attendance/ }).getAttribute("aria-sort")).toBe("ascending");
    fireEvent.click(screen.getByRole("button", { name: /Attendance/ }));
    expect(names()).toEqual(["Bala Iyer", "Asha Rao", "Chitra Das"]);
  });

  it("opens a student's details with the reasons eligibility is not met", async () => {
    stub({ [URL("b1")]: () => json(payload(STUDENTS)) });
    render(<TrainerProgressPanel batches={BATCHES} />);
    await screen.findByRole("row", { name: /Asha Rao/ });
    const toggle = within(rowOf("Asha Rao")).getByRole("button", { name: "Details for Asha Rao" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const details = screen.getByRole("region", { name: "Asha Rao progress details" });
    expect(within(details).getByText("Progress 40% (needs 100%)")).toBeTruthy();
    expect(within(details).getByText("Attendance 50% (needs 75%)")).toBeTruthy();
    expect(within(details).getByText(/4 sessions recorded/)).toBeTruthy();
    expect(within(details).getByText(/Fee: clear/)).toBeTruthy();
    fireEvent.click(toggle);
    expect(screen.queryByRole("region", { name: "Asha Rao progress details" })).toBeNull();
  });

  it("says plainly when no session is recorded yet (QA28-01)", async () => {
    stub({ [URL("b1")]: () => json(payload(STUDENTS)) });
    render(<TrainerProgressPanel batches={BATCHES} />);
    await screen.findByRole("row", { name: /Chitra Das/ });
    fireEvent.click(screen.getByRole("button", { name: "Details for Chitra Das" }));
    const details = screen.getByRole("region", { name: "Chitra Das progress details" });
    expect(within(details).getByText("Attendance: no session recorded yet (needs 75%)")).toBeTruthy();
    expect(details.textContent).not.toContain("— —");
  });

  it("re-reads when the trainer picks another batch", async () => {
    const mock = stub({ [URL("b1")]: () => json(payload(STUDENTS)), [URL("b2")]: () => json(payload([])) });
    render(<TrainerProgressPanel batches={BATCHES} />);
    await screen.findByRole("row", { name: /Asha Rao/ });
    fireEvent.change(screen.getByLabelText("Batch"), { target: { value: "b2" } });
    expect(await screen.findByText("No students are enrolled in this batch yet.")).toBeTruthy();
    expect(mock).toHaveBeenCalledWith(URL("b2"));
  });

  it("shows the server's error, and a retry", async () => {
    let fail = true;
    stub({ [URL("b1")]: () => (fail ? json({ detail: "Batch is outside your assigned batches" }, 403) : json(payload(STUDENTS))) });
    render(<TrainerProgressPanel batches={BATCHES} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Batch is outside your assigned batches");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("row", { name: /Asha Rao/ });
  });

  it("says so when the trainer has no batch, and while batches load", () => {
    stub({});
    const { rerender } = render(<TrainerProgressPanel batches={[]} loading />);
    expect(screen.getByText("Loading your batches…")).toBeTruthy();
    rerender(<TrainerProgressPanel batches={[]} />);
    expect(screen.getByText("No batch is assigned to you yet.")).toBeTruthy();
  });

  it("the header-only Student Progress section shows its title and subtitle but no empty table", () => {
    const data = { title: "Student Progress", subtitle: "Attendance, assignments, assessments, progress and certificate eligibility for each student in your batches.", metrics: [], columns: [], rows: [], actions: [], panels: [] };
    render(<PortalSection data={data} table={false} />);
    expect(screen.getByRole("heading", { name: "Student Progress" })).toBeTruthy();
    expect(screen.getByText(/certificate eligibility for each student/)).toBeTruthy();
    expect(screen.queryByText("No records yet")).toBeNull();
  });

  it("re-reads in place when refreshKey changes", async () => {
    const mock = stub({ [URL("b1")]: () => json(payload(STUDENTS)) });
    const { rerender } = render(<TrainerProgressPanel batches={BATCHES} refreshKey="a" />);
    await screen.findByRole("row", { name: /Asha Rao/ });
    rerender(<TrainerProgressPanel batches={BATCHES} refreshKey="b" />);
    await waitFor(() => expect(mock.mock.calls.filter(([u]) => u === URL("b1")).length).toBe(2));
  });
});
