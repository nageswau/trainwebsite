import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementTaskForm from "@/components/ManagementTaskForm";
import ManagementTasks from "@/components/ManagementTasks";
import MyManagementTasks from "@/components/MyManagementTasks";
import type { DiscussionOptions } from "@/lib/managementDiscussions";
import type { ManagementTask, MyTask, TaskCounts } from "@/lib/managementTasks";

const router = { replace: vi.fn(), refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, redirect: vi.fn(), usePathname: () => "/management/tasks" }));

const PARTNER = { id: "u1", full_name: "Arjun Partner", role: "partner" };
const BDM = { id: "u2", full_name: "Uma BDM", role: "partnership_manager" };
const options: DiscussionOptions = { users: [PARTNER, BDM] };
const counts: TaskCounts = { overdue: 1, today: 1, week: 0, later: 0, completed: 1 };

function task(overrides: Partial<ManagementTask> = {}): ManagementTask {
  return {
    id: "t1", title: "Approve marketing budget", owner: BDM, owner_active: true, priority: "high", deadline: "2026-10-12", status: "open", band: "today",
    source: "manual", completed_at: null, created_by: PARTNER, created_at: "2026-10-01T04:30:00Z", updated_at: "2026-10-01T04:30:00Z", ...overrides,
  };
}
function mine(overrides: Partial<MyTask> = {}): MyTask {
  return { id: "t1", title: "Approve marketing budget", priority: "high", deadline: "2026-10-12", status: "open", band: "today", updated_at: "2026-10-01T04:30:00Z", ...overrides };
}

type Call = { url: string; method: string; body: unknown };
let calls: Call[];
function respond(...answers: { status?: number; body?: unknown }[]) {
  const queue = [...answers];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : undefined });
    const answer = queue.shift() ?? { body: { id: "t9" } };
    return new Response(JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200, headers: { "Content-Type": "application/json" } });
  }));
}

beforeEach(() => {
  calls = [];
  router.push.mockReset();
  router.refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("mgmt-028 management to-do", () => {
  it("lists tasks under the §28 bands in order, with counts, owner, priority and an inactive-owner prompt", () => {
    const items = [task({ id: "t3", band: "completed", status: "completed", title: "Review monthly P&L" }), task({ id: "t2", band: "overdue", title: "Review agent performance", owner_active: false }), task()];
    render(<ManagementTasks data={{ items, total: 3, limit: 200, offset: 0, today: "2026-10-12", counts }} error="" filters={{ view: "everyone" }} />);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Overdue (1)", "Due Today (1)", "Completed (1)"]);
    const overdue = screen.getByRole("region", { name: "Overdue (1)" });
    expect(within(overdue).getByText("Review agent performance")).toBeTruthy();
    expect(within(overdue).getByText("Owner inactive — reassign")).toBeTruthy();
    const today = screen.getByRole("region", { name: "Due Today (1)" });
    expect(today.textContent).toContain("Uma BDM");
    expect(within(today).getByText("High priority")).toBeTruthy(); // QA-01: the priority badge says what it is
    expect(within(today).getByRole("link", { name: "Edit Approve marketing budget" }).getAttribute("href")).toBe("/management/tasks/t1/edit");
    expect(screen.getByRole("link", { name: "Everyone" }).getAttribute("aria-current")).toBe("page");
  });

  it("shows an empty state, and the error without hiding the views", () => {
    render(<ManagementTasks data={{ items: [], total: 0, limit: 200, offset: 0, today: "2026-10-12", counts: { ...counts, overdue: 0, today: 0, completed: 0 } }} error="" filters={{ view: "mine" }} />);
    expect(screen.getByRole("status").textContent).toBe("No tasks here.");
    cleanup();
    render(<ManagementTasks data={null} error="Tasks are unavailable right now." filters={{ view: "mine" }} />);
    expect(screen.getByRole("alert").textContent).toBe("Tasks are unavailable right now.");
    expect(screen.getByRole("link", { name: "My tasks" })).toBeTruthy();
  });
});

describe("mgmt-028 staff Management tasks", () => {
  it("lets the owner move a task's status on", async () => {
    respond({ body: mine({ status: "completed", band: "completed" }) });
    render(<MyManagementTasks data={{ items: [mine()], today: "2026-10-12", counts }} />);
    expect(screen.getByRole("region", { name: "Due Today (1)" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Status of “Approve marketing budget”"), { target: { value: "completed" } });
    fireEvent.click(screen.getByRole("button", { name: "Update status" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Status updated."));
    expect(calls).toEqual([{ url: "/api/v1/me/management-tasks/t1", method: "PATCH", body: { status: "completed" } }]);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("shows the API's refusal", async () => {
    respond({ status: 409, body: { detail: "This task was cancelled; it can't be updated" } });
    render(<MyManagementTasks data={{ items: [mine()], today: "2026-10-12", counts }} />);
    fireEvent.change(screen.getByLabelText("Status of “Approve marketing budget”"), { target: { value: "in_progress" } });
    fireEvent.click(screen.getByRole("button", { name: "Update status" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("cancelled"));
  });

  it("has an empty state", () => {
    render(<MyManagementTasks data={{ items: [], today: "2026-10-12", counts: { overdue: 0, today: 0, week: 0, later: 0, completed: 0 } }} />);
    expect(screen.getByRole("status").textContent).toBe("No management tasks are assigned to you.");
  });
});

describe("mgmt-028 task form", () => {
  it("checks the fields before sending", () => {
    respond();
    render(<ManagementTaskForm options={options} today="2026-10-12" />);
    fireEvent.click(screen.getByRole("button", { name: "Save task" }));
    expect(screen.getByText("Give the title (2-200 characters)")).toBeTruthy();
    expect(screen.getByText("Choose the owner")).toBeTruthy();
    expect(calls).toEqual([]);
  });

  it("creates a task and goes back to the list", async () => {
    respond({ status: 201, body: task() });
    render(<ManagementTaskForm options={options} today="2026-10-12" />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: " Approve marketing budget " } });
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "u2" } });
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "high" } });
    fireEvent.click(screen.getByRole("button", { name: "Save task" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/tasks?view=everyone"));
    expect(calls).toEqual([{ url: "/api/v1/management/tasks", method: "POST", body: { title: "Approve marketing budget", owner_user_id: "u2", priority: "high", deadline: "2026-10-12", status: "open" } }]);
  });

  it("puts the API's field error on its field", async () => {
    respond({ status: 422, body: { detail: [{ loc: ["body", "owner_user_id"], msg: "Choose an active staff member", type: "value_error" }] } });
    render(<ManagementTaskForm options={options} today="2026-10-12" />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Approve new trainer" } });
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "u2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save task" }));
    await waitFor(() => expect(screen.getByText("Choose an active staff member")).toBeTruthy());
    expect(screen.getByLabelText("Owner").getAttribute("aria-invalid")).toBe("true");
  });

  it("sends only what changed on an edit, and keeps an inactive owner selectable", async () => {
    respond({ body: task({ priority: "low" }) });
    const gone = { id: "u9", full_name: "Former Trainer", role: "trainer" };
    render(<ManagementTaskForm options={options} today="2026-10-12" task={task({ owner: gone, owner_active: false, deadline: "2026-10-01" })} />);
    expect(screen.getByRole("option", { name: "Former Trainer (Trainer) — inactive" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "low" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(calls).toEqual([{ url: "/api/v1/management/tasks/t1", method: "PATCH", body: { priority: "low" } }]);
  });
});
