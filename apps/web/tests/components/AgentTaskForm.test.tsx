import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentTaskForm from "@/components/AgentTaskForm";
import type { AgentTask } from "@/lib/agentTasks";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const apps = { items: [{ id: "a1", university: "Leeds", course: null, intake: "Sep 2027", status: "enquiry" }], total: 1, limit: 100, offset: 0 };
const saved = { task: { id: "t1" } };

function stub(write: (init: RequestInit) => Response) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method ? write(init) : res(apps)));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
const sent = (fetchMock: ReturnType<typeof stub>) => JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method)![1]!.body));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentTaskForm (AGN-016)", () => {
  it("creates a task for a fixed student, sending the due time with an offset", async () => {
    const fetchMock = stub(() => res(saved, 201));
    const onSaved = vi.fn();
    render(<AgentTaskForm mode="create" studentId="s1" onCancel={vi.fn()} onSaved={onSaved} />);
    await screen.findByRole("option", { name: "Leeds — Sep 2027" });
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: " Call Asha " } });
    fireEvent.change(screen.getByLabelText("Due"), { target: { value: "2031-10-05T09:30" } });
    fireEvent.change(screen.getByLabelText("Application (optional)"), { target: { value: "a1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent(fetchMock)).toEqual({ agent_student_id: "s1", title: "Call Asha", due_at: new Date(2031, 9, 5, 9, 30).toISOString(), notes: null, application_id: "a1" });
  });

  it("shows field errors and sends nothing when required fields are empty", async () => {
    const fetchMock = stub(() => res(saved, 201));
    render(<AgentTaskForm mode="create" studentId="s1" onCancel={vi.fn()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(await screen.findByText("Title is required.")).toBeInTheDocument();
    expect(screen.getByText("Choose a due date and time.")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method)).toBe(false);
  });

  it("marks an unpicked student invalid on the picker itself, with its linked message (QA16-02)", async () => {
    stub(() => res(saved, 201));
    render(<AgentTaskForm mode="create" onCancel={vi.fn()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    const combo = screen.getByRole("combobox", { name: "Student" });
    await waitFor(() => expect(combo).toHaveAttribute("aria-invalid", "true"));
    const message = document.getElementById(combo.getAttribute("aria-describedby")!.split(" ")[0])!;
    expect(message).toHaveTextContent("Choose a student from the list.");
    // one message, not the picker's and the form's
    expect(screen.getAllByText("Choose a student from the list.")).toHaveLength(1);
    expect(screen.queryByText("Choose a student.")).toBeNull();
    expect(combo).toHaveFocus();
  });

  it("warns, without blocking, when the due time has passed", async () => {
    stub(() => res(saved, 201));
    render(<AgentTaskForm mode="create" studentId="s1" onCancel={vi.fn()} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Due"), { target: { value: "2020-01-01T09:00" } });
    expect(screen.getByText("This time has passed — the task will show as overdue.")).toBeInTheDocument();
  });

  it("keeps the form open with the server's message on a 422", async () => {
    stub(() => res({ detail: "Choose an application of this student" }, 422));
    const onSaved = vi.fn();
    render(<AgentTaskForm mode="create" studentId="s1" onCancel={vi.fn()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Call" } });
    fireEvent.change(screen.getByLabelText("Due"), { target: { value: "2031-10-05T09:30" } });
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose an application of this student");
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Title")).toHaveValue("Call");
  });

  it("Escape in the open student list closes only the list, never the form (final review)", async () => {
    const students = { items: [{ id: "s1", full_name: "Asha Rao", has_login: false, email: null }], total: 1, limit: 20, offset: 0 };
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(res(String(url).includes("/crm/students") ? students : apps))));
    const onCancel = vi.fn();
    render(<AgentTaskForm mode="create" onCancel={onCancel} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Kept title" } });
    const combo = screen.getByRole("combobox", { name: "Student" });
    fireEvent.focus(combo);
    fireEvent.change(combo, { target: { value: "As" } });
    await screen.findByRole("option", { name: /Asha Rao/ });
    fireEvent.keyDown(combo, { key: "Escape" });
    expect(onCancel).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Title")).toHaveValue("Kept title");
    fireEvent.keyDown(combo, { key: "Escape" }); // the list is closed now: Escape cancels the form as before
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("edits: sends only changed fields and cancels with Escape", async () => {
    const fetchMock = stub(() => res(saved));
    const onCancel = vi.fn();
    const task: AgentTask = {
      id: "t1", title: "Call", notes: "Old", due_at: new Date(2031, 9, 5, 9, 30).toISOString(), status: "open", overdue: false,
      student: { id: "s1", full_name: "Asha", status: "active" }, application: null, assigned_to: null,
      created_by: "M", closed_by: null, closed_at: null, created_at: "", updated_at: "",
    };
    const onSaved = vi.fn();
    render(<AgentTaskForm mode="edit" task={task} onCancel={onCancel} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText("Notes (optional)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save task" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent(fetchMock)).toEqual({ notes: null });
    fireEvent.keyDown(screen.getByLabelText("Title"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });
});
