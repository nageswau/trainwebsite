import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AttendanceCorrectionPanel from "@/components/AttendanceCorrectionPanel";
import TeacherWorkspaceActions from "@/components/TeacherWorkspaceActions";
import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

// nehn-023: the student requests a correction from their own session row (never a UUID); the trainer works a pending
// queue with Approve / Reject and an optional comment.
const ROWS = "/api/v1/workflows/it/student/attendance";
const CREATE = "/api/v1/workflows/it/student/attendance-corrections";
const RECORD_A = "11111111-1111-4111-8111-111111111111";
const RECORD_B = "22222222-2222-4222-8222-222222222222";
const rows = (pending = false) => [
  { id: RECORD_A, batch: "Batch A", session_date: "2026-10-20", status: "absent", notes: null, correction_pending: pending },
  { id: RECORD_B, batch: "Batch A", session_date: "2026-10-19", status: "present", notes: null, correction_pending: true },
];
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

function stubStudent(createStatus = 201, createBody: unknown = { id: "c1", status: "pending" }) {
  let created = false;
  const mock = vi.fn((url: string, init?: RequestInit) => {
    if (url === CREATE && init?.method === "POST") {
      created = createStatus === 201;
      return json(createBody, createStatus);
    }
    if (url === ROWS) return json(rows(created));
    return json([]);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
const createBody = (mock: ReturnType<typeof stubStudent>) => {
  const call = mock.mock.calls.find(([url, init]) => url === CREATE && init?.method === "POST");
  return call ? JSON.parse(String(call[1]?.body)) : undefined;
};

describe("student AttendanceCorrectionPanel (nehn-023 AC1)", () => {
  it("lists the student's sessions with a row action and never shows a record UUID", async () => {
    stubStudent();
    const { container } = render(<AttendanceCorrectionPanel />);
    expect(screen.getByText("Loading your sessions…")).toBeInTheDocument();
    const button = await screen.findByRole("button", { name: "Request correction for 20 Oct 2026, Batch A" });
    expect(button).toBeInTheDocument();
    // a row that already has a pending request shows that instead of the action
    const pendingRow = screen.getByText("19 Oct 2026").closest("tr")!;
    expect(within(pendingRow).getByText("Correction pending")).toBeInTheDocument();
    expect(within(pendingRow).queryByRole("button")).toBeNull();
    expect(container.textContent).not.toContain(RECORD_A);
    expect(screen.queryByLabelText(/reference/i)).toBeNull();
  });

  it("submits the row's record with the chosen status and trimmed reason, then shows it pending", async () => {
    const mock = stubStudent();
    render(<AttendanceCorrectionPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Request correction for 20 Oct 2026, Batch A" }));
    const status = screen.getByLabelText("Correct status") as HTMLSelectElement;
    // the current status is not offered as the "correct" one
    expect(Array.from(status.options).map(option => option.value)).toEqual(["present", "late", "excused"]);
    fireEvent.change(status, { target: { value: "late" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "  Arrived 10 minutes late, not absent.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByText("Correction request submitted.")).toBeInTheDocument();
    expect(createBody(mock)).toEqual({ attendance_id: RECORD_A, requested_status: "late", reason: "Arrived 10 minutes late, not absent." });
    await waitFor(() => expect(screen.getAllByText("Correction pending")).toHaveLength(2));
    expect(screen.queryByLabelText("Reason")).toBeNull();
    expect(refresh).toHaveBeenCalled();
  });

  it("QA-01/QA-02: opens the form right under the chosen row, and reports success above the table", async () => {
    stubStudent();
    render(<AttendanceCorrectionPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Request correction for 20 Oct 2026, Batch A" }));
    const row = screen.getByText("20 Oct 2026", { selector: "th" }).closest("tr")!;
    expect(within(row.nextElementSibling as HTMLElement).getByLabelText("Reason")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "I was present all day." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));
    const success = await screen.findByText("Correction request submitted.");
    expect(success.compareDocumentPosition(screen.getByRole("table")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("stops a too-short reason in the browser and sends nothing", async () => {
    const mock = stubStudent();
    render(<AttendanceCorrectionPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Request correction for 20 Oct 2026, Batch A" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "  ok  " } });
    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByText("Enter a reason of at least 5 characters.")).toBeInTheDocument();
    expect(createBody(mock)).toBeUndefined();
  });

  it("shows the API error (e.g. a request already pending) and keeps the form", async () => {
    stubStudent(409, { detail: "A correction request is already pending" });
    render(<AttendanceCorrectionPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Request correction for 20 Oct 2026, Batch A" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "I was present all day." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByText("A correction request is already pending")).toBeInTheDocument();
    expect(screen.getByLabelText("Reason")).toBeInTheDocument();
  });

  it("Cancel closes the form without sending", async () => {
    const mock = stubStudent();
    render(<AttendanceCorrectionPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Request correction for 20 Oct 2026, Batch A" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Reason")).toBeNull();
    expect(createBody(mock)).toBeUndefined();
  });

  it("has an empty state and an error state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json([])));
    render(<AttendanceCorrectionPanel />);
    expect(await screen.findByText("No attendance has been recorded for you yet.")).toBeInTheDocument();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => json({ detail: "Service unavailable" }, 503)));
    render(<AttendanceCorrectionPanel />);
    expect(await screen.findByText("Service unavailable")).toBeInTheDocument();
  });

  it("WorkflowPanel mounts the panel for an IT student instead of the UUID form", async () => {
    stubStudent();
    const student = { id: "u1", role: "it_student", division: "it", full_name: "Asha Rao", email: "a@example.local" } as unknown as User;
    render(<WorkflowPanel user={student} section="attendance" />);
    expect(await screen.findByRole("button", { name: "Request correction for 20 Oct 2026, Batch A" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Attendance record reference")).toBeNull();
  });
});

const QUEUE = "/api/v1/workflows/it/trainer/attendance-corrections?status=pending";
const REVIEW = "/api/v1/workflows/it/attendance-corrections/c1";
const correction = { id: "c1", attendance_id: RECORD_A, student: "Asha Rao", batch: "Batch A", session_date: "2026-10-20", current_status: "absent", requested_status: "present", reason: "I was in class.", status: "pending", review_notes: null };

function stubTrainer(reviewStatus = 200) {
  let reviewed = false;
  const mock = vi.fn((url: string, init?: RequestInit) => {
    if (url === REVIEW && init?.method === "PATCH") {
      reviewed = reviewStatus === 200;
      return reviewStatus === 200 ? json({ id: "c1", status: JSON.parse(String(init.body)).status }) : json({ detail: "This correction request has already been reviewed" }, reviewStatus);
    }
    if (url === QUEUE) return json(reviewed ? [] : [correction]);
    if (url === "/api/v1/workflows/it/trainer/context") return json({ batches: [], students: [], enrollments: [] });
    return json([]);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
const reviewBody = (mock: ReturnType<typeof stubTrainer>) => {
  const call = mock.mock.calls.find(([url, init]) => url === REVIEW && init?.method === "PATCH");
  return call ? JSON.parse(String(call[1]?.body)) : undefined;
};

describe("trainer pending corrections queue (nehn-023 AC3)", () => {
  it("shows each pending request with its details, a comment box and Approve / Reject", async () => {
    stubTrainer();
    render(<TeacherWorkspaceActions section="attendance" />);
    const item = (await screen.findByText("Asha Rao")).closest("li")!;
    expect(within(item).getByText(/Batch A · 20 Oct 2026/)).toBeInTheDocument();
    expect(within(item).getByText("Absent → Present")).toBeInTheDocument(); // QA-03: same wording as the student's view
    expect(within(item).getByText("I was in class.")).toBeInTheDocument();
    expect(within(item).getByLabelText("Comment (optional)")).toBeInTheDocument();
    expect(within(item).getByRole("button", { name: "Approve correction for Asha Rao, 20 Oct 2026" })).toBeInTheDocument();
    expect(within(item).getByRole("button", { name: "Reject correction for Asha Rao, 20 Oct 2026" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Pending request")).toBeNull();
  });

  it.each([
    ["Approve", "approved", "  Checked the register.  ", "Checked the register."],
    ["Reject", "rejected", "", null],
  ])("%s sends status %j with the trimmed comment and empties the queue", async (verb, status, comment, sent) => {
    const mock = stubTrainer();
    render(<TeacherWorkspaceActions section="attendance" />);
    await screen.findByText("Asha Rao");
    fireEvent.change(screen.getByLabelText("Comment (optional)"), { target: { value: comment } });
    fireEvent.click(screen.getByRole("button", { name: `${verb} correction for Asha Rao, 20 Oct 2026` }));
    expect(await screen.findByText(status === "approved" ? "Correction approved." : "Correction rejected.")).toBeInTheDocument();
    expect(reviewBody(mock)).toEqual({ status, review_notes: sent });
    expect(await screen.findByText("No pending correction requests.")).toBeInTheDocument();
  });

  it("shows the API error when the request was already decided", async () => {
    stubTrainer(409);
    render(<TeacherWorkspaceActions section="attendance" />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Approve correction for Asha Rao, 20 Oct 2026" }));
    expect(await screen.findByText("This correction request has already been reviewed")).toBeInTheDocument();
  });

  it("WorkflowPanel no longer offers trainers a correction-reference form", () => {
    const trainer = { id: "t1", role: "trainer", division: "it", full_name: "T", email: "t@example.local" } as unknown as User;
    render(<WorkflowPanel user={trainer} section="attendance" />);
    expect(screen.queryByLabelText("Correction reference")).toBeNull();
  });
});
