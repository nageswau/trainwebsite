import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateNotes from "@/components/RecruiterCandidateNotes";
import RecruiterCandidateTasks from "@/components/RecruiterCandidateTasks";

afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const ok = (body: object, status = 200) => new Response(JSON.stringify(body), { status });
const fail = (status: number, detail: string) => new Response(JSON.stringify({ detail }), { status });
const page = (items: object[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const note = { id: "n1", body: "Prefers Pune\ncall after 6", author: { id: "u1", full_name: "Riya Recruiter" }, created_at: "2026-11-04T05:00:00Z" };
const task = {
  id: "t1", task_type: "resume_screening", title: "Screen the resume", notes: null, due_at: "2026-11-05T05:00:00Z", status: "open", overdue: false,
  assignee: { id: "u2", full_name: "Ravi Kumar", active: false }, candidate: { id: "c1", candidate_code: "CAN-000001", name: "Rahul" }, application_id: null,
  requirement: null, created_by: { id: "u1", full_name: "Riya Recruiter" }, created_at: "2026-11-04T05:00:00Z", completed_at: null, completed_by: null,
  cancelled_at: null, cancelled_by: null, can_change: true,
};

describe("RecruiterCandidateNotes (hrc-016 T2)", () => {
  it("loads, shows the empty state and the private hint", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok(page([])));
    render(<RecruiterCandidateNotes candidateId="c1" canAdd />);
    expect(screen.getByText("Loading notes…")).toBeInTheDocument();
    expect(await screen.findByText("No notes yet.")).toBeInTheDocument();
    expect(screen.getByText(/never shown to candidates or employers/)).toBeInTheDocument();
    expect(vi.mocked(global.fetch).mock.calls[0][0]).toBe("/api/v1/recruiter/candidates/c1/notes?limit=50&offset=0");
  });

  it("adds a note, clears the box and tells the page", async () => {
    const onAdded = vi.fn();
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(page([]))).mockResolvedValueOnce(ok(note, 201)).mockResolvedValueOnce(ok(page([note])));
    render(<RecruiterCandidateNotes candidateId="c1" canAdd onAdded={onAdded} />);
    await screen.findByText("No notes yet.");
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "Prefers Pune" } });
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));
    const list = await screen.findByRole("list", { name: "Candidate notes" });
    expect(within(list).getByText(/Prefers Pune/)).toBeInTheDocument();
    const [url, init] = vi.mocked(global.fetch).mock.calls[1];
    expect(url).toBe("/api/v1/recruiter/candidates/c1/notes");
    expect(JSON.parse(String(init?.body))).toEqual({ body: "Prefers Pune" });
    expect(screen.getByLabelText("New note")).toHaveValue("");
    expect(onAdded).toHaveBeenCalledOnce();
  });

  it("refuses an empty note without a request and shows a server refusal", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(page([]))).mockResolvedValueOnce(fail(409, "Restore this candidate first"));
    render(<RecruiterCandidateNotes candidateId="c1" canAdd />);
    await screen.findByText("No notes yet.");
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Write a note first");
    expect(global.fetch).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByText("Restore this candidate first")).toBeInTheDocument();
    expect(screen.getByLabelText("New note")).toHaveValue("x"); // typed text is kept
  });

  it("is read only for a reader and retries a failed load", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(fail(500, "x")).mockResolvedValueOnce(ok(page([note])));
    render(<RecruiterCandidateNotes candidateId="c1" canAdd={false} />);
    expect(await screen.findByText("Unable to load notes.")).toBeInTheDocument();
    expect(screen.queryByLabelText("New note")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/Riya Recruiter/)).toBeInTheDocument();
  });
});

describe("RecruiterCandidateTasks (hrc-016 T5/T11)", () => {
  it("lists a task with an inactive assignee and marks it done", async () => {
    const onChanged = vi.fn();
    const done = { ...task, status: "done", completed_at: "2026-11-04T06:00:00Z", completed_by: task.created_by, can_change: false };
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(page([task]))).mockResolvedValueOnce(ok(done)).mockResolvedValueOnce(ok(page([done])));
    render(<RecruiterCandidateTasks candidateId="c1" canAdd onChanged={onChanged} />);
    const list = await screen.findByRole("list", { name: "Candidate tasks" });
    expect(within(list).getByText("Screen the resume")).toBeInTheDocument();
    expect(within(list).getByText("Resume screening")).toBeInTheDocument();
    expect(within(list).getByText("Ravi Kumar (inactive)")).toBeInTheDocument();
    fireEvent.click(within(list).getByRole("button", { name: "Done" }));
    expect(await screen.findByText("Task marked done.")).toBeInTheDocument();
    expect(vi.mocked(global.fetch).mock.calls[1][0]).toBe("/api/v1/recruiter/candidate-tasks/t1/complete");
    expect(await screen.findByText("Done", { selector: ".badge" })).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("offers no actions to a reader and no Add task", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok(page([{ ...task, can_change: false }])));
    render(<RecruiterCandidateTasks candidateId="c1" canAdd={false} />);
    await screen.findByText("Screen the resume");
    expect(screen.queryByRole("button", { name: "Done" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add task" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My tasks" })).not.toBeInTheDocument();
  });

  it("opens the add form, validates it locally and cancels with Escape", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(page([]))).mockResolvedValue(ok({ items: [] }));
    render(<RecruiterCandidateTasks candidateId="c1" canAdd />);
    await screen.findByText("No tasks yet.");
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    const form = screen.getByRole("form", { name: "Add task" });
    fireEvent.click(within(form).getByRole("button", { name: "Add task" }));
    expect(await within(form).findByText("Choose a task type")).toBeInTheDocument();
    expect(within(form).getByText("Enter a title")).toBeInTheDocument();
    expect(within(form).getByText("Choose who does it")).toBeInTheDocument();
    fireEvent.keyDown(form, { key: "Escape" });
    expect(screen.queryByRole("form", { name: "Add task" })).not.toBeInTheDocument();
  });

  it("hands a 409 up as a notice and reloads", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(page([task]))).mockResolvedValueOnce(fail(409, "This task is already done")).mockResolvedValueOnce(ok(page([])));
    render(<RecruiterCandidateTasks candidateId="c1" canAdd />);
    fireEvent.click(await screen.findByRole("button", { name: "Done" }));
    expect(await screen.findByText("This task is already done")).toBeInTheDocument();
    expect(await screen.findByText("No tasks yet.")).toBeInTheDocument();
  });
});
