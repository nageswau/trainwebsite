import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationTasks from "@/components/BdmOrganizationTasks";
import type { Task, TaskPage } from "@/lib/bdmTasks";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const task = (over: Partial<Task> = {}): Task => ({
  id: "t1", kind: "task", title: "Send brochure", notes: null, due_on: "2030-01-07", status: "open", source: "manual", overdue: false,
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college", archived: false }, appointment: null,
  assignee: { id: "b1", full_name: "Asha", active: true }, completed_at: null, cancelled_at: null, cancel_reason: null,
  created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z", permissions: { can_edit: true, can_complete: true, can_cancel: true }, ...over,
});
const page = (items: Task[]): TaskPage => ({ items, total: items.length, limit: 50, offset: 0, today: "2030-01-07", counts: { buckets: { today: 0, overdue: 0, upcoming: 0, done: 0, cancelled: 0 }, by_org_type: [] } });
const org = { id: "o1", name: "St Mary" };

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("BdmOrganizationTasks (bdm-008 §9)", () => {
  it("lists open items and offers Add to the BDM", () => {
    render(<BdmOrganizationTasks organization={org} initial={page([task()])} canAdd basePath="/bdm" version={0} onNotice={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Follow-ups & tasks" })).toBeInTheDocument();
    expect(screen.getByText("Send brochure")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(within(screen.getByRole("form", { name: "Add follow-up or task" })).getByText("St Mary")).toBeInTheDocument(); // fixed in the form
  });

  it("is read-only without canAdd and says when nothing is open", () => {
    render(<BdmOrganizationTasks organization={org} initial={page([])} canAdd={false} basePath="/bdm/manager" version={0} onNotice={vi.fn()} />);
    expect(screen.getByText("No open follow-ups or tasks.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add task" })).toBeNull();
  });

  it("offers Try again when the first page couldn't load, and reloads when the version changes", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<BdmOrganizationTasks organization={org} initial={null} canAdd basePath="/bdm" version={0} onNotice={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Send brochure")).toBeInTheDocument();
    rerender(<BdmOrganizationTasks organization={org} initial={null} canAdd basePath="/bdm" version={1} onNotice={vi.fn()} />);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
