import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmTaskItem from "@/components/BdmTaskItem";
import type { Task } from "@/lib/bdmTasks";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const task = (over: Partial<Task> = {}): Task => ({
  id: "t1", kind: "follow_up", title: "Call the principal", notes: "Line 1\nLine 2", due_on: "2030-01-04", status: "open", source: "manual", overdue: true,
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college", archived: false }, appointment: null,
  assignee: { id: "b1", full_name: "Asha", active: true }, completed_at: null, cancelled_at: null, cancel_reason: null,
  created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z", permissions: { can_edit: true, can_complete: true, can_cancel: true }, ...over,
});
const props = { today: "2030-01-07", basePath: "/bdm" as const, showAssignee: false, onChanged: vi.fn(), onRefused: vi.fn() };

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("BdmTaskItem (bdm-008 §9)", () => {
  it("shows overdue in words, the organization and the notes", () => {
    render(<ul><BdmTaskItem task={task()} {...props} /></ul>);
    expect(screen.getByText("Overdue · 3 days")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "St Mary" })).toHaveAttribute("href", "/bdm/organizations/o1");
    expect(screen.getByText("College")).toBeInTheDocument();
    expect(screen.getByText(/Line 1/)).toHaveStyle({ whiteSpace: "pre-wrap" });
  });

  it("wraps unbroken notes and reasons instead of widening the page (QA8: 600-char note overflowed by 3600px at 390px)", () => {
    render(<ul><BdmTaskItem task={task({ notes: "x".repeat(600), status: "cancelled", cancelled_at: "2030-01-07T05:00:00Z", cancel_reason: "y".repeat(400) })} {...props} /></ul>);
    expect(screen.getByText("x".repeat(600))).toHaveStyle({ overflowWrap: "anywhere" });
    expect(screen.getByText(/y{400}/)).toHaveStyle({ overflowWrap: "anywhere" });
  });

  it("completes and reports the change", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(task({ status: "done", completed_at: "2030-01-07T05:00:00Z" })))));
    render(<ul><BdmTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "done" }), "Marked done."));
  });

  it("cancels with a reason", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(task({ status: "cancelled", cancel_reason: "Clash" }))));
    vi.stubGlobal("fetch", fetchMock);
    render(<ul><BdmTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Cancel task" }));
    fireEvent.change(screen.getByLabelText("Reason (required)"), { target: { value: "Clash" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel it" }));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "cancelled" }), "Cancelled."));
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ reason: "Clash" });
  });

  it("returns focus to Edit / Cancel task when their form is closed with Escape", async () => {
    render(<ul><BdmTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.keyDown(screen.getByLabelText("Title (required)"), { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Cancel task" }));
    fireEvent.keyDown(screen.getByLabelText("Reason (required)"), { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel task" })).toHaveFocus());
  });

  it("hands a 409 to the list (reloads on a 409)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "This task was cancelled" }, 409))));
    render(<ul><BdmTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(props.onRefused).toHaveBeenCalledWith("This task was cancelled"));
  });

  it("offers only what permissions allow and links an outcome follow-up to its appointment", () => {
    const outcome = task({ source: "appointment_outcome", appointment: { id: "a1", code: "APT-000001" }, permissions: { can_edit: false, can_complete: true, can_cancel: false } });
    render(<ul><BdmTaskItem task={outcome} {...props} basePath="/bdm/manager" showAssignee /></ul>);
    expect(screen.getByRole("link", { name: "From APT-000001" })).toHaveAttribute("href", "/bdm/manager/appointments/a1");
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel task" })).toBeNull();
    expect(screen.getByText("Asha")).toBeInTheDocument();
  });
});
