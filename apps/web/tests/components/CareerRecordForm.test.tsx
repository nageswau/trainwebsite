import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { pickOption } from "../helpers/pickOption";
import { afterEach, describe, expect, it, vi } from "vitest";
import CareerRecordForm from "@/components/CareerRecordForm";
import type { CareerRecord } from "@/lib/careerRecords";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const STUDENTS = [{ id: "s1", full_name: "Asha", school_name: "Hill School" }];
const RECORD: CareerRecord = {
  id: "r1", school_student_id: "s1", record_type: "counselling_note", notes: "Met.", created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z",
  status: "completed", scheduled_for: null, completed_on: "2026-09-01", next_follow_up_date: null,
  career_interests: null, academic_strengths: null, weak_areas: ["Essays"], recommended_careers: null, recommended_courses: null,
  recommended_stream: null, recommended_skills: null, global_education_interest: null, parent_participated: null, parent_participation_note: null,
  counselor_name: "C", updated_by_name: null,
};

describe("CareerRecordForm", () => {
  it("shows the date input that belongs to the chosen status", () => {
    render(<CareerRecordForm students={STUDENTS} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "counselling_note" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "scheduled" } });
    expect(screen.getByLabelText("Scheduled for")).toBeInTheDocument();
    expect(screen.queryByLabelText("Next follow-up")).not.toBeInTheDocument();
  });

  it("does not offer past dates for the next follow-up (QA-03)", () => {
    render(<CareerRecordForm students={STUDENTS} record={RECORD} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "follow_up_required" } });
    const min = (screen.getByLabelText("Next follow-up") as HTMLInputElement).min;
    expect(min).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const now = new Date();
    const local = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    expect(min).toBe(local);
  });

  // QA-05 (browser QA 2026-09-28): Type and Status survived a successful create while the other fields reset, and "Record saved."
  // stayed on screen indefinitely.
  it("resets the whole form after a create and clears the success message on the next change", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "r9" }) }));
    render(<CareerRecordForm students={STUDENTS} onDone={vi.fn()} onCancel={vi.fn()} />);
    pickOption(screen, "Student", "s1");
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "counselling_note" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "not_started" } });
    fireEvent.click(screen.getByRole("button", { name: "Save record" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Record saved.");
    expect(screen.getByLabelText("Type")).toHaveValue("");
    expect(screen.queryByLabelText("Status")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "guidance_session" } });
    expect(screen.getByLabelText("Status")).toHaveValue("completed");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("hides status and structured fields for a recommendation", () => {
    render(<CareerRecordForm students={STUDENTS} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "recommendation" } });
    expect(screen.queryByLabelText("Status")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Weak areas")).not.toBeInTheDocument();
  });

  it("edits with PATCH and sends expected_status", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ...RECORD }) });
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();
    render(<CareerRecordForm students={STUDENTS} record={RECORD} onDone={onDone} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/career-counselor/records/r1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toMatchObject({ expected_status: "completed", weak_areas: ["Essays"] });
  });

  it("offers a reload when the record changed elsewhere (409)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail: "This record was changed by someone else (now Follow-up Required). Reload to see the latest." }) }));
    render(<CareerRecordForm students={STUDENTS} record={RECORD} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed by someone else");
    // QA-09 (browser QA 2026-09-28): the action throws away what was typed, so it says so.
    expect(screen.getByRole("button", { name: "Discard my changes and reload" })).toBeInTheDocument();
  });

  // QA-11 (browser QA 2026-09-28): a 5xx showed the bare "Internal Server Error".
  it("words a server failure for people and keeps the entry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: "Internal Server Error" }) }));
    render(<CareerRecordForm students={STUDENTS} record={RECORD} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again; your entry is kept.");
  });

  it("cancels with Escape", () => {
    const onCancel = vi.fn();
    render(<CareerRecordForm students={STUDENTS} record={RECORD} onDone={vi.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(screen.getByLabelText("Status"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });
});
