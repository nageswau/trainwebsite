import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PartnershipTaskItem from "@/components/PartnershipTaskItem";
import type { PartnershipTask } from "@/lib/partnershipTasks";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const task = (over: Partial<PartnershipTask> = {}): PartnershipTask => ({
  id: "t1", university: { id: "u1", university_code: "UNV-000001", name: "XYZ University" }, kind: "follow_up", title: "Follow up on proposal",
  notes: "Ask about fees", due_on: "2030-01-04", priority: "high", status: "open", band: "overdue", overdue: true, source: "stage",
  assignee: { id: "p1", full_name: "Rahul", active: true }, created_by: { id: "p1", full_name: "Rahul", active: true },
  completed_at: null, cancelled_at: null, cancel_reason: null, created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z",
  permissions: { can_edit: true, can_reschedule: true, can_complete: true, can_cancel: true }, ...over,
});
const props = { showUniversity: true, onChanged: vi.fn(), onRefused: vi.fn() };

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("PartnershipTaskItem (upc-020)", () => {
  it("says the band, priority, kind and source in words, links the university and names the owner", () => {
    render(<ul><PartnershipTaskItem task={task()} {...props} /></ul>);
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText("High priority")).toBeInTheDocument();
    expect(screen.getByText("Follow-up")).toBeInTheDocument();
    expect(screen.getByText("Auto: stage change")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "XYZ University" })).toHaveAttribute("href", "/partnership/universities/u1");
    expect(screen.getByText(/Owner: Rahul/)).toBeInTheDocument();
  });

  it("hides the university on its own page and every action the API does not allow", () => {
    const none = { can_edit: false, can_reschedule: false, can_complete: false, can_cancel: false };
    render(<ul><PartnershipTaskItem task={task({ permissions: none })} {...props} showUniversity={false} /></ul>);
    expect(screen.queryByRole("link", { name: "XYZ University" })).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("completes through the API and reports the change", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res({ task: task({ status: "done", band: "done", overdue: false }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<ul><PartnershipTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "done" }), "Marked done."));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/tasks/t1/complete");
  });

  it("reschedules with a new due date", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res({ task: task({ due_on: "2030-02-01", band: "upcoming" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<ul><PartnershipTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Reschedule" }));
    fireEvent.change(screen.getByLabelText("New due date (IST)"), { target: { value: "2030-02-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save date" }));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(expect.objectContaining({ due_on: "2030-02-01" }), "Rescheduled."));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/tasks/t1/reschedule");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ due_on: "2030-02-01" });
  });

  it("cancels with a reason", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res({ task: task({ status: "cancelled", band: "cancelled" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<ul><PartnershipTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Cancel task" }));
    fireEvent.change(screen.getByLabelText("Reason (required)"), { target: { value: "Intake paused" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel it" }));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "cancelled" }), "Cancelled."));
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ reason: "Intake paused" });
  });

  it("a refused write (changed elsewhere) goes to the list; a 422 stays on the row in the server's words", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "This task is already done" }, 409))));
    render(<ul><PartnershipTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(props.onRefused).toHaveBeenCalledWith("This task is already done"));
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "The due date can't be in the past" }, 422))));
    fireEvent.click(screen.getByRole("button", { name: "Reschedule" }));
    fireEvent.change(screen.getByLabelText("New due date (IST)"), { target: { value: "2020-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save date" }));
    expect(await screen.findByText("The due date can't be in the past")).toBeInTheDocument();
  });

  it("shows when a done or cancelled task was closed, with the reason, and wraps long text", () => {
    render(<ul><PartnershipTaskItem task={task({ status: "cancelled", band: "cancelled", overdue: false, cancelled_at: "2030-01-05T05:00:00Z", cancel_reason: "y".repeat(300), notes: "x".repeat(400) })} {...props} /></ul>);
    expect(screen.getByText(/Cancelled .*y{300}/)).toHaveStyle({ overflowWrap: "anywhere" });
    expect(screen.getByText("x".repeat(400))).toHaveStyle({ overflowWrap: "anywhere" });
  });
});
