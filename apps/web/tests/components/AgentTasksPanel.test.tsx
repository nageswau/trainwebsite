import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentTasksPanel from "@/components/AgentTasksPanel";

const task = (over: Record<string, unknown> = {}) => ({
  id: "t1", title: "Call Asha", notes: "Ask for the\nCAS letter", due_at: "2026-10-05T04:00:00Z", status: "open", overdue: false,
  student: { id: "s1", full_name: "Asha Rao", status: "active" }, application: { id: "a1", university: "Leeds" },
  assigned_to: { code: "ABC-S001", full_name: "Priya", status: "active" }, created_by: "Master", closed_by: null, closed_at: null,
  created_at: "", updated_at: "", ...over,
});
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentTasksPanel (AGN-016)", () => {
  it("lists tasks with the student, assignee, application, notes and an Overdue text badge", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([task({ overdue: true })])))));
    render(<AgentTasksPanel view="open" />);
    const list = await screen.findByRole("list", { name: "Tasks" });
    const card = within(list).getByRole("listitem");
    expect(within(card).getByRole("heading", { name: "Call Asha" })).toBeInTheDocument();
    expect(within(card).getByText("Overdue")).toBeInTheDocument();
    expect(card).toHaveTextContent("Asha Rao");
    expect(card).toHaveTextContent("ABC-S001 · Priya");
    expect(card).toHaveTextContent("Leeds");
    expect(screen.getByText("Showing 1–1 of 1")).toBeInTheDocument();
  });

  it("asks the server for the view and the student", async () => {
    const fetchMock = vi.fn<(url: string) => Promise<Response>>(() => Promise.resolve(res(page([]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentTasksPanel view="all" studentId="s9" />);
    await screen.findByText("No tasks yet.");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/v1/workflows/overseas/agent/crm/tasks?view=all&limit=20&offset=0&student=s9");
  });

  it("shows the empty text of each view", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<AgentTasksPanel view="overdue" />);
    expect(await screen.findByText("Nothing overdue.")).toBeInTheDocument();
  });

  it("shows a load error with Retry", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "x" }, 500)).mockResolvedValueOnce(res(page([task()])));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentTasksPanel view="open" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The server couldn't complete this. Please try again in a moment.");
    fireEvent.click(screen.getByRole("button", { name: "Retry loading tasks" }));
    expect(await screen.findByText("Call Asha")).toBeInTheDocument();
  });

  it("marks a task done and reloads", async () => {
    let listed = [task()];
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        listed = [];
        return Promise.resolve(res({ task: task({ status: "done" }) }));
      }
      return Promise.resolve(res(page(listed)));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentTasksPanel view="open" />);
    fireEvent.click(await screen.findByRole("button", { name: "Mark “Call Asha” done" }));
    expect(await screen.findByText("No open tasks.")).toBeInTheDocument();
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(patch[0]).toBe("/api/v1/workflows/overseas/agent/crm/tasks/t1");
    expect(JSON.parse(String(patch[1]!.body))).toEqual({ status: "done" });
    expect(screen.getByText("“Call Asha” marked done.")).toBeInTheDocument();
  });

  it("cancels only after confirmation, with focus on the safe choice", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "PATCH" ? res({ task: task({ status: "cancelled" }) }) : res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentTasksPanel view="open" />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel “Call Asha”" }));
    expect(screen.getByRole("button", { name: "Keep task" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
    expect(JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")![1]!.body))).toEqual({ status: "cancelled" });
  });

  it("explains a conflict and reloads (someone else closed it)", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "PATCH" ? res({ detail: "This task is closed" }, 409) : res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentTasksPanel view="open" />);
    fireEvent.click(await screen.findByRole("button", { name: "Mark “Call Asha” done" }));
    expect(await screen.findByText("This task is closed")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => !init?.method).length).toBe(2));
  });

  it("offers no actions on a closed task or when read-only", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([task({ id: "t2", status: "done", closed_by: "Priya", closed_at: "2026-10-04T10:00:00Z" })])))));
    render(<AgentTasksPanel view="done" />);
    const card = await screen.findByRole("listitem");
    expect(card).toHaveTextContent("Done");
    expect(within(card).queryByRole("button")).toBeNull();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([task()])))));
    render(<AgentTasksPanel view="all" studentId="s1" readOnly />);
    await screen.findByText("Call Asha");
    expect(screen.queryByRole("button", { name: /Mark|Edit|Cancel/ })).toBeNull();
  });
});
