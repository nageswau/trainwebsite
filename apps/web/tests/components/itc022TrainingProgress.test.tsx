import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItProgressPlansPanel from "@/components/ItProgressPlansPanel";
import MyTrainingProgress from "@/components/MyTrainingProgress";
import RemediationPlans from "@/components/RemediationPlans";
import TrainerProgressPanel from "@/components/TrainerProgressPanel";
import TrainerTopicsPanel from "@/components/TrainerTopicsPanel";
import { fromCopySource, weightsSummary } from "@/lib/itProgress";
import { PORTAL_NAV } from "@/lib/navigation";

// itc-022 (DEC-SCOPE-365): progress plans, topic completion, remediation plans and the student's progress view.
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
type Call = [string, RequestInit | undefined];
const calls = (fetchMock: ReturnType<typeof vi.fn>) => fetchMock.mock.calls as unknown as Call[];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("itProgress helpers", () => {
  it("words the weights, leaving zero parts out, and says when the trainer sets progress", () => {
    expect(weightsSummary({ topics: 50, assignments: 50, assessments: 0 })).toBe("Topics 50% · Assignments 50%");
    expect(weightsSummary(null)).toBe("Set by the trainer");
  });

  it("copies the syllabus as new modules and topics, dropping blanks", () => {
    expect(fromCopySource([{ title: " Basics ", topics: ["OOP", " "] }, { title: " ", topics: [] }])).toEqual([{ title: "Basics", topics: [{ title: "OOP" }] }]);
  });

  it("adds Progress Plans to the IT Admin's nav", () => {
    expect(PORTAL_NAV["it/admin"].some(item => item.href === "/it/admin/progress-plans" && item.label === "Progress Plans")).toBe(true);
  });
});

const SUMMARY = { program_id: "p1", program: "Full Stack Java", active: true, modules: 0, topics: 0, weights: null, computed: false };
const PLAN = { program_id: "p1", program: "Full Stack Java", modules: [], weights: null, computed: false, copy_source: [{ title: "Basics", topics: ["OOP", "Git"] }] };

describe("ItProgressPlansPanel", () => {
  it("copies the syllabus, refuses weights that do not add up to 100, then saves the plan", async () => {
    const saved = { ...PLAN, modules: [{ id: "m1", title: "Basics", topics: [{ id: "t1", title: "OOP" }, { id: "t2", title: "Git" }] }], weights: { topics: 60, assignments: 20, assessments: 20 }, computed: true };
    const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "PUT" ? json(saved) : url.endsWith("/p1") ? json(PLAN) : json([SUMMARY])));
    vi.stubGlobal("fetch", fetchMock);
    render(<ItProgressPlansPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit progress plan for Full Stack Java" }));
    fireEvent.click(await screen.findByRole("button", { name: "Copy from syllabus" }));
    expect((screen.getByLabelText("Module 1") as HTMLInputElement).value).toBe("Basics");
    expect((screen.getByLabelText("Module 1 topic 2") as HTMLInputElement).value).toBe("Git");

    fireEvent.click(screen.getByLabelText("Work it out from these weights"));
    expect(screen.getByText("The weights add up to 100.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Topics completed (%)"), { target: { value: "70" } });
    expect(screen.getByText(/add up to 120 — they must add up to 100/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save plan" }));
    expect((await screen.findByRole("alert")).textContent).toContain("must add up to 100 (they add up to 120)");
    expect(calls(fetchMock).some(([, init]) => init?.method === "PUT")).toBe(false);

    fireEvent.change(screen.getByLabelText("Topics completed (%)"), { target: { value: "60" } });
    fireEvent.change(screen.getByLabelText("Assignments and labs graded (%)"), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Save plan" }));
    expect((await screen.findByRole("status")).textContent).toContain("Progress is now worked out from the formula");
    const [, init] = calls(fetchMock).find(([, i]) => i?.method === "PUT")!;
    expect(JSON.parse(String(init?.body))).toEqual({ modules: [{ title: "Basics", topics: [{ title: "OOP" }, { title: "Git" }] }], weights: { topics: 60, assignments: 20, assessments: 20 } });
    expect(screen.getByText("Topics 60% · Assignments 20% · Assessments 20%")).toBeTruthy();
  });

  it("shows the server's error when the list fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ detail: "x" }, 500)));
    render(<ItProgressPlansPanel />);
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load the progress plans");
  });
});

const TOPICS = { batch_id: "b1", computed: true, modules: [{ id: "m1", title: "Basics", topics: [{ id: "t1", title: "OOP", completed_enrollment_ids: ["e1"] }] }] };
const PROGRESS = { students: [
  { enrollment_id: "e1", student: "Asha Rao", student_code: "ITS-1", status: "active" },
  { enrollment_id: "e2", student: "Bala Iyer", student_code: null, status: "active" },
  { enrollment_id: "e3", student: "Gone", student_code: null, status: "dropped" },
] };

describe("TrainerTopicsPanel", () => {
  it("marks a topic complete for every selected active student in one request and tells the table", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "PUT" ? json({ topic_id: "t1", completed_enrollment_ids: ["e1", "e2"] }) : url.includes("/topics") ? json(TOPICS) : json(PROGRESS)));
    vi.stubGlobal("fetch", fetchMock);
    render(<TrainerTopicsPanel batches={[{ id: "b1", name: "FSJ-Nov" }]} onChanged={onChanged} />);
    const students = await screen.findByRole("group", { name: "Students" });
    expect(within(students).queryByText(/Gone/)).toBeNull();
    expect(within(students).getByText("Done")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Mark complete (0)" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Select all (2)"));
    fireEvent.click(screen.getByRole("button", { name: "Mark complete (2)" }));
    expect((await screen.findByRole("status")).textContent).toBe('"OOP" marked complete for 2 students.');
    const [url, init] = calls(fetchMock).find(([, i]) => i?.method === "PUT")!;
    expect(url).toBe("/api/v1/it/batches/b1/topics/t1/completions");
    expect(JSON.parse(String(init?.body))).toEqual({ enrollment_ids: ["e1", "e2"], completed: true });
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("says when the course has no topics yet", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => (url.includes("/topics") ? json({ ...TOPICS, modules: [] }) : json(PROGRESS))));
    render(<TrainerTopicsPanel batches={[{ id: "b1", name: "FSJ-Nov" }]} />);
    expect(await screen.findByText(/no topics yet/)).toBeTruthy();
  });
});

const PLANS = {
  student: { id: "s1", full_name: "Asha Rao", student_code: "ITS-1" },
  items: [{ id: "r1", actions: "Two extra labs", due_date: "2026-11-10", status: "open", owner_name: "Tara Trainer", batch: "FSJ-Nov", owner_user_id: "u1", enrollment_id: "e1", risk_flag_id: "f1" }],
  enrollments: [{ enrollment_id: "e1", batch: "FSJ-Nov" }],
  owner_options: [{ id: "u1", name: "Tara Trainer", role: "trainer" }, { id: "c1", name: "Cora Counselor", role: "counselor" }],
  viewer_id: "u1",
};

describe("RemediationPlans", () => {
  it("lists plans, moves a status and adds a plan with an owner", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method && init.method !== "GET" ? json({ id: "r2" }, init.method === "POST" ? 201 : 200) : json(PLANS)));
    vi.stubGlobal("fetch", fetchMock);
    render(<RemediationPlans studentId="s1" />);
    expect(await screen.findByText("Two extra labs")).toBeTruthy();
    expect(screen.getByText(/from an at-risk flag/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: 'Mark plan "Two extra labs" in progress' }));
    expect((await screen.findByRole("status")).textContent).toBe("Plan marked in progress.");

    fireEvent.click(screen.getByRole("button", { name: "Add remediation plan" }));
    fireEvent.change(screen.getByLabelText("Actions"), { target: { value: "Weekly check-in" } });
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2099-01-01" } });
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save remediation plan" }));
    await waitFor(() => expect(calls(fetchMock).some(([, i]) => i?.method === "POST")).toBe(true));
    const [url, init] = calls(fetchMock).find(([, i]) => i?.method === "POST")!;
    expect(url).toBe("/api/v1/it/enrollments/e1/remediation-plans");
    expect(JSON.parse(String(init?.body))).toEqual({ actions: "Weekly check-in", due_date: "2099-01-01", owner_user_id: "c1" });
  });

  it("lets the plan's owner move its status from the server's viewer id, and lists the caller once (QA-03/QA-04)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ ...PLANS, enrollments: [], owner_options: [], viewer_id: "u1" })));
    render(<RemediationPlans studentId="s1" />);
    expect(await screen.findByRole("button", { name: 'Mark plan "Two extra labs" completed' })).toBeTruthy();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => json({ ...PLANS, viewer_id: "u1" })));
    render(<RemediationPlans studentId="s1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add remediation plan" }));
    expect(screen.getAllByRole("option").map(o => o.textContent)).toEqual(["Tara Trainer (me)", "Cora Counselor (counselor)"]);
  });

  it("is read-only for a reader who cannot add plans and does not own them", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ ...PLANS, enrollments: [], owner_options: [], viewer_id: "someone-else" })));
    render(<RemediationPlans studentId="s1" />);
    expect(await screen.findByText("Two extra labs")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add remediation plan" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Mark plan/ })).toBeNull();
  });
});

const COURSE = {
  enrollment_id: "e1", course: "Full Stack Java", batch: "FSJ-Nov", status: "active", progress_percent: 45, mode: "computed",
  weights: { topics: 50, assignments: 30, assessments: 20 }, topics_completed: 1, topics_total: 2, labs_graded: 1, labs_total: 2,
  assignments_graded: 2, assignments_total: 4, assessments_passed: 0, assessments_total: 1,
  modules: [{ title: "Basics", topics: [{ title: "OOP", completed: true }, { title: "Git", completed: false }] }],
};

describe("MyTrainingProgress", () => {
  it("shows the overall %, how it is worked out, the parts, the topics and open support plans", async () => {
    const plan = { ...PLANS.items[0], owner_user_id: undefined, enrollment_id: undefined, risk_flag_id: undefined };
    vi.stubGlobal("fetch", vi.fn(() => json({ courses: [COURSE], remediation_plans: [plan, { ...plan, id: "r9", actions: "Old plan", status: "completed" }] })));
    render(<MyTrainingProgress />);
    expect((await screen.findByRole("progressbar", { name: "Full Stack Java overall progress" })).getAttribute("aria-valuenow")).toBe("45");
    expect(screen.getByText("Worked out from Topics 50% · Assignments 30% · Assessments 20%.")).toBeTruthy();
    expect(screen.getByText("Labs: 1 of 2 graded")).toBeTruthy();
    expect(screen.getByText("Topics: 1 of 2 completed")).toBeTruthy();
    expect(screen.getByText("Two extra labs")).toBeTruthy();
    expect(screen.queryByText("Old plan")).toBeNull();
    expect(screen.getByRole("link", { name: "Updates" }).getAttribute("href")).toBe("/it/student/updates");
  });

  it("says when the student is not enrolled, and offers a retry on failure", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ courses: [], remediation_plans: [] })));
    render(<MyTrainingProgress />);
    expect(await screen.findByText(/once you are enrolled/)).toBeTruthy();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => json({ detail: "boom" }, 500)));
    render(<MyTrainingProgress />);
    expect(await screen.findByRole("button", { name: "Try again" })).toBeTruthy();
  });
});

describe("TrainerProgressPanel (itc-022 additions)", () => {
  const row = {
    enrollment_id: "e1", student_id: "s1", student_code: "ITS-1", student: "Asha Rao", enrollment_code: "EDU-1", status: "active",
    progress_percent: 80, attendance_percent: 90, attendance_sessions: 4, at_risk: false, assignments_submitted: 1, assignments_graded: 1,
    assignments_total: 2, assessments_passed: 0, assessments_total: 0, fee_clear: true, eligible: false, reasons: [], certificate_issued: false,
    override_reason: "Finished offline", computed_percent: 50, topics_completed: 1, topics_total: 2, labs_graded: 1, labs_total: 1,
  };

  it("badges an override, explains it and switches back to the worked-out figure", async () => {
    const body = { rules: { min_progress_percent: 100, min_attendance_percent: 75 }, progress_mode: "computed", students: [row] };
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      init?.method === "DELETE" ? json({ id: "e1", progress_percent: 50, override_reason: null }) : url.includes("remediation") ? json({ ...PLANS, items: [] }) : json(body),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<TrainerProgressPanel batches={[{ id: "b1", name: "FSJ-Nov" }]} />);
    expect(await screen.findByText("Override")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Details for Asha Rao" }));
    expect(screen.getByText("Topics: 1 of 2 completed")).toBeTruthy();
    expect(screen.getByText(/Set by hand: “Finished offline” — worked out it would be 50%/)).toBeTruthy();
    expect(await screen.findByText("No remediation plan yet.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use worked-out figure" }));
    await waitFor(() => expect(calls(fetchMock).some(([u, i]) => i?.method === "DELETE" && u === "/api/v1/workflows/it/trainer/enrollments/e1/progress/override")).toBe(true));
  });
});
