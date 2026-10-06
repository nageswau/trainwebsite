import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmTaskForm from "@/components/BdmTaskForm";
import type { Task } from "@/lib/bdmTasks";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const task = (over: Partial<Task> = {}): Task => ({
  id: "t1", kind: "task", title: "Send brochure", notes: null, due_on: "2030-01-07", status: "open", source: "manual", overdue: false,
  organization: null, appointment: null, assignee: { id: "b1", full_name: "Asha", active: true }, completed_at: null, cancelled_at: null,
  cancel_reason: null, created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z",
  permissions: { can_edit: true, can_complete: true, can_cancel: true }, ...over,
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("BdmTaskForm (bdm-008 §9)", () => {
  it("creates with the organization fixed and sends blanks as null", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(task(), 201)));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<BdmTaskForm organization={{ id: "o1", name: "St Mary" }} onSaved={onSaved} onCancel={vi.fn()} />);
    expect(screen.getByLabelText("Title (required)")).toHaveFocus();
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Send brochure" } });
    fireEvent.change(screen.getByLabelText("Due date (IST, required)"), { target: { value: "2030-01-07" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ kind: "follow_up", title: "Send brochure", due_on: "2030-01-07", notes: null, organization_id: "o1" });
    expect(screen.getByText("St Mary")).toBeInTheDocument();
  });

  it("checks required fields before sending", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTaskForm onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByText("Title is required")).toBeInTheDocument();
    expect(screen.getByText("Choose a due date")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("puts a 422 on its field and keeps the typed text", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Due date can't be in the past" }, 422))));
    render(<BdmTaskForm task={task()} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Changed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Due date can't be in the past")).toBeInTheDocument();
    expect(screen.getByLabelText("Due date (IST, required)")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Title (required)")).toHaveValue("Changed");
    expect(screen.queryByRole("radio")).toBeNull(); // kind is fixed after create
  });

  it("words a server error plainly and keeps the text (QA8B-03)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Internal Server Error" }, 500))));
    render(<BdmTaskForm task={task()} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Kept" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("We couldn't save this. Please try again.")).toBeInTheDocument();
    expect(screen.queryByText("Internal Server Error")).toBeNull();
    expect(screen.getByLabelText("Title (required)")).toHaveValue("Kept");
  });

  it("offers sign-in when the session has ended, keeping the text (QA8B-02)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Not authenticated" }, 401))));
    render(<BdmTaskForm task={task()} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Your session has ended — sign in again to continue.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to login" })).toBeInTheDocument();
    expect(screen.getByLabelText("Title (required)")).toHaveValue("Send brochure");
  });

  it("Escape cancels", () => {
    const onCancel = vi.fn();
    render(<BdmTaskForm onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(screen.getByLabelText("Title (required)"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });
});
