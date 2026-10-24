import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CounselorTaskForm from "@/components/CounselorTaskForm";
import CounselorTaskList from "@/components/CounselorTaskList";
import { adminFilters, adminTasksUrl, linkHref, parseLink, type CounselorTask, type CounselorTaskOptions } from "@/lib/counselorTasks";
import { PORTAL_NAV } from "@/lib/navigation";

const router = { replace: vi.fn(), refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, redirect: vi.fn(), usePathname: () => "/overseas/counselor/tasks" }));

const ME = { id: "c1", full_name: "Asha Counselor" };
const ADMIN = { id: "a1", full_name: "Ravi Admin" };
const TODAY = "2026-10-24";
const options: CounselorTaskOptions = {
  counselors: [],
  links: { leads: [{ id: "l1", label: "LD-000001 · Priya" }], students: [{ id: "s1", label: "Kiran · AB12CD34" }], applications: [] },
};

function task(overrides: Partial<CounselorTask> = {}): CounselorTask {
  return {
    id: "t1", title: "Call the bank", due_on: TODAY, priority: "high", status: "open", band: "today", source: "manual", completed_at: null, link: null,
    counselor: ME, created_by: ME, created_at: "2026-10-20T04:30:00Z", updated_at: "2026-10-20T04:30:00Z", can_edit: true, ...overrides,
  };
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
  router.refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ccrm-029 counselor tasks", () => {
  it("lists tasks under their bands in order, with the link and who gave the task", () => {
    render(<CounselorTaskList today={TODAY} options={options} empty="none" items={[
      task({ id: "t2", title: "Send shortlist", band: "upcoming", due_on: "2026-10-30" }),
      task({ id: "t1", title: "Chase offer", band: "overdue", due_on: "2026-10-20", link: { type: "lead", id: "l1", label: "LD-000001 · Priya" } }),
      task({ id: "t3", title: "From admin", band: "today", created_by: ADMIN, can_edit: false }),
    ]} />);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Overdue (1)", "Today (1)", "Upcoming (1)"]);
    expect(screen.getByRole("link", { name: "LD-000001 · Priya" })).toHaveAttribute("href", "/overseas/counselor/leads/l1");
    const fromAdmin = screen.getByText(/From admin/).closest("li")!;
    expect(within(fromAdmin).getByText(/Given by Ravi Admin/)).toBeInTheDocument();
    expect(within(fromAdmin).queryByRole("button", { name: "Edit" })).toBeNull();
    expect(within(fromAdmin).getByRole("button", { name: "Mark done" })).toBeInTheDocument();
  });

  it("QA-01: names the priority once, as the badge", () => {
    render(<CounselorTaskList today={TODAY} options={options} empty="none" items={[task()]} />);
    expect(screen.getByText("Call the bank — due 24 Oct 2026")).toBeInTheDocument();
    expect(screen.getAllByText(/High priority/)).toHaveLength(1);
  });

  it("QA-02: the 'Task added.' message clears once the next task is typed", async () => {
    respond({ status: 201, body: task() });
    render(<CounselorTaskForm options={options} today={TODAY} />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Call the bank" } });
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(await screen.findByText("Task added.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Next one" } });
    expect(screen.queryByText("Task added.")).toBeNull();
  });

  it("shows the empty message", () => {
    render(<CounselorTaskList today={TODAY} options={options} items={[]} empty="You have no open tasks." />);
    expect(screen.getByRole("status")).toHaveTextContent("You have no open tasks.");
  });

  it("marks a task done and refreshes", async () => {
    respond({ body: task({ status: "done", band: "done" }) });
    render(<CounselorTaskList today={TODAY} options={options} empty="none" items={[task()]} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark done" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls).toEqual([{ url: "/api/v1/counselor/tasks/t1", method: "PATCH", body: { status: "done" } }]);
  });

  it("asks once more before cancelling, and shows a refusal", async () => {
    respond({ status: 409, body: { detail: "This task was cancelled; it can't be changed" } });
    render(<CounselorTaskList today={TODAY} options={options} empty="none" items={[task()]} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel task" }));
    expect(calls).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Yes, cancel it" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This task was cancelled");
    expect(calls[0].body).toEqual({ status: "cancelled" });
  });

  it("reopens a done task", async () => {
    respond({ body: task() });
    render(<CounselorTaskList today={TODAY} options={options} empty="none" items={[task({ status: "done", band: "done" })]} />);
    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));
    await waitFor(() => expect(calls[0]?.body).toEqual({ status: "open" }));
  });

  it("adds a task with a link, trimmed, and resets", async () => {
    respond({ status: 201, body: task() });
    render(<CounselorTaskForm options={options} today={TODAY} />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "  Call   the bank " } });
    fireEvent.change(screen.getByLabelText("About (optional)"), { target: { value: "student:s1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Task added.");
    expect(calls[0]).toEqual({ url: "/api/v1/counselor/tasks", method: "POST", body: { title: "Call the bank", due_on: TODAY, priority: "medium", link: { type: "student", id: "s1" } } });
    expect(screen.getByLabelText("Title")).toHaveValue("");
  });

  it("checks the title and past due dates before sending, and places API field errors", async () => {
    render(<CounselorTaskForm options={options} today={TODAY} />);
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-10-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(screen.getByText("Give the title (2-200 characters)")).toBeInTheDocument();
    expect(screen.getByText("The due date can't be in the past")).toBeInTheDocument();
    respond({ status: 422, body: { detail: [{ loc: ["body", "link"], msg: "Choose a lead, student or application of this counselor", type: "value_error" }] } });
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Valid title" } });
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: TODAY } });
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(await screen.findByText("Choose a lead, student or application of this counselor")).toBeInTheDocument();
  });

  it("an edit sends only what changed", async () => {
    respond({ body: task({ title: "Renamed" }) });
    const onClose = vi.fn();
    render(<CounselorTaskForm options={options} today={TODAY} task={task()} onClose={onClose} />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(calls[0]).toEqual({ url: "/api/v1/counselor/tasks/t1", method: "PATCH", body: { title: "Renamed" } });
  });

  it("the admin picks a counselor, whose links are then loaded", async () => {
    respond({ body: { counselors: [], links: { leads: [], students: [], applications: [{ id: "p1", label: "APP-000001 · Oxford" }] } } });
    render(<CounselorTaskForm options={{ ...options, counselors: [ME], links: { leads: [], students: [], applications: [] } }} today={TODAY} admin />);
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(screen.getByText("Choose the counselor")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Counselor"), { target: { value: "c1" } });
    expect(await screen.findByRole("option", { name: "APP-000001 · Oxford" })).toBeInTheDocument();
    expect(calls[0].url).toBe("/api/v1/counselor/tasks/options?counselor_id=c1");
  });
});

describe("ccrm-029 helpers and navigation", () => {
  it("parses links and builds the admin's URL from safe filters only", () => {
    expect(parseLink("lead:l1")).toEqual({ type: "lead", id: "l1" });
    expect(parseLink("bogus:1")).toBeNull();
    expect(parseLink("")).toBeNull();
    expect(linkHref({ type: "student", id: "s1" })).toBe("/overseas/counselor/students/s1/notes");
    const id = "0b9e5c1e-1111-4222-8333-444455556666";
    expect(adminFilters({ counselor: id, band: "overdue" })).toEqual({ counselor: id, band: "overdue" });
    expect(adminFilters({ counselor: "x';drop", band: "everything" })).toEqual({ counselor: "", band: "" });
    expect(adminTasksUrl({ counselor: id, band: "done" })).toBe(`/api/v1/counselor/tasks?limit=200&counselor_id=${id}&band=done`);
  });

  it("links the counselor's Tasks and the admin's Counselor tasks", () => {
    expect(PORTAL_NAV["overseas/counselor"][1]).toEqual({ label: "Tasks", href: "/overseas/counselor/tasks" });
    expect(PORTAL_NAV["overseas/admin"].find((i) => i.href === "/overseas/admin/counselor-tasks")?.label).toBe("Counselor tasks");
  });
});
