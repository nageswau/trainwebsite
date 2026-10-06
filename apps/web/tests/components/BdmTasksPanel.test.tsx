import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmTasksPanel from "@/components/BdmTasksPanel";
import type { Task, TaskPage } from "@/lib/bdmTasks";

const router = vi.hoisted(() => ({ push: vi.fn() }));
const search = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/bdm/follow-ups", useSearchParams: () => new URLSearchParams(search.value) }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const task = (over: Partial<Task> = {}): Task => ({
  id: "t1", kind: "follow_up", title: "Call the principal", notes: null, due_on: "2030-01-07", status: "open", source: "manual", overdue: false,
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college", archived: false }, appointment: null,
  assignee: { id: "b1", full_name: "Asha", active: true }, completed_at: null, cancelled_at: null, cancel_reason: null,
  created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z", permissions: { can_edit: true, can_complete: true, can_cancel: true }, ...over,
});
const page = (items: Task[], over: Partial<TaskPage> = {}): TaskPage => ({
  items, total: items.length, limit: 50, offset: 0, today: "2030-01-07",
  counts: { buckets: { today: items.length, overdue: 2, upcoming: 0, done: 0, cancelled: 0 }, by_org_type: [{ org_type: "college", count: items.length }, { org_type: null, count: 0 }].filter((c) => c.count) },
  ...over,
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); router.push.mockClear(); search.value = ""; });

describe("BdmTasksPanel (bdm-008 §9)", () => {
  it("asks for today and shows tabs with counts, type chips and rows", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTasksPanel isBdm />);
    expect(await screen.findByText("Call the principal")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/v1/bdm/tasks?bucket=today&limit=50&offset=0");
    const tabs = screen.getByRole("navigation", { name: "Follow-up lists" });
    expect(within(tabs).getByRole("button", { name: "Today (1)" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(within(tabs).getByRole("button", { name: "Overdue (2)" }));
    expect(router.push).toHaveBeenCalledWith("/bdm/follow-ups?bucket=overdue", { scroll: false });
    fireEvent.click(screen.getByRole("button", { name: "College 1" }));
    expect(router.push).toHaveBeenLastCalledWith("/bdm/follow-ups?org_type=college", { scroll: false });
  });

  it("marks the pressed chip and ignores bad URL values", async () => {
    search.value = "org_type=college&bucket=soon&kind=meeting";
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTasksPanel isBdm />);
    expect(await screen.findByRole("button", { name: "College 1" })).toHaveAttribute("aria-pressed", "true");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/v1/bdm/tasks?bucket=today&limit=50&offset=0&org_type=college");
  });

  it("shows the tab's empty text with Add, and retries after a failure", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(page([])));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTasksPanel isBdm />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Nothing due today.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add follow-up or task" }).length).toBeGreaterThan(0);
  });

  it("after Done says so with next-step links and reloads", async () => {
    const fetchMock = vi.fn<typeof fetch>((url) => Promise.resolve(String(url).endsWith("/complete") ? res(task({ status: "done" })) : res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTasksPanel isBdm />);
    await screen.findByText("Call the principal"); // before the first page the tabs carry no counts, so the Done tab is also "Done"
    fireEvent.click(within(screen.getByRole("list", { name: "Today" })).getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.getByText("Marked done.")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Log activity" })).toHaveAttribute("href", "/bdm/organizations/o1#org-o1-activity");
    expect(screen.getByRole("link", { name: "Book appointment" })).toHaveAttribute("href", "/bdm/appointments/new?organization=o1");
    expect(fetchMock.mock.calls.filter((c) => String(c[0]).startsWith("/api/v1/bdm/tasks?")).length).toBe(2);
  });

  it("reads only for managers, with a BDM filter and no Add", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([task({ permissions: { can_edit: false, can_complete: false, can_cancel: false } })])))));
    render(<BdmTasksPanel isBdm={false} />);
    expect(await screen.findByText("Asha")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add follow-up or task" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Done" })).toBeNull();
    expect(screen.getByLabelText("BDM", { selector: "input" })).toBeInTheDocument();
  });
});
