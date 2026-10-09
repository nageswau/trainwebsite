import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PartnershipTasksPanel from "@/components/PartnershipTasksPanel";

const push = vi.fn();
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }), usePathname: () => "/partnership/tasks", useSearchParams: () => search }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const counts = { overdue: 2, today: 1, tomorrow: 0, upcoming: 3, done: 4, cancelled: 0 };
const item = {
  id: "t1", university: { id: "u1", university_code: "UNV-1", name: "XYZ University" }, kind: "follow_up", title: "Follow-up call", notes: null,
  due_on: "2030-01-07", priority: "high", status: "open", band: "today", overdue: false, source: "manual", assignee: { id: "p", full_name: "Rahul", active: true },
  created_by: { id: "p", full_name: "Rahul", active: true }, completed_at: null, cancelled_at: null, cancel_reason: null, created_at: "", updated_at: "",
  permissions: { can_edit: true, can_reschedule: true, can_complete: true, can_cancel: true },
};
const page = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0, today: "2030-01-07", counts });

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
beforeEach(() => {
  search = new URLSearchParams();
  fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(page([item]))));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("PartnershipTasksPanel (upc-020)", () => {
  it("lists today's items by default with every band's count, and the manager's own items", async () => {
    render(<PartnershipTasksPanel role="partnership_manager" />);
    expect(await screen.findByText("Follow-up call")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/tasks?band=today&limit=50&offset=0&assignee=me");
    expect(screen.getByRole("button", { name: "Overdue (2)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Due today (1)" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("button", { name: "Upcoming (3)" }));
    expect(push).toHaveBeenCalledWith("/partnership/tasks?band=upcoming", { scroll: false });
  });

  it("offers a head their team and everyone, and reads the filter from the URL", async () => {
    search = new URLSearchParams("band=overdue&assignee=team");
    render(<PartnershipTasksPanel role="partnership_head" />);
    await screen.findByText("Follow-up call");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/tasks?band=overdue&limit=50&offset=0&assignee=team");
    expect(screen.getByLabelText("Show")).toHaveValue("team");
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "all" } });
    expect(push).toHaveBeenCalledWith("/partnership/tasks?band=overdue&assignee=all", { scroll: false });
  });

  it("a super admin sees everyone's items and cannot add", async () => {
    render(<PartnershipTasksPanel role="super_admin" />);
    await screen.findByText("Follow-up call");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/tasks?band=today&limit=50&offset=0");
    expect(screen.queryByRole("button", { name: "Add follow-up or task" })).toBeNull();
  });

  it("on a university page lists its open items without tabs", async () => {
    render(<PartnershipTasksPanel role="partnership_manager" university={{ id: "u1", name: "XYZ University" }} canAdd />);
    await screen.findByText("Follow-up call");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/tasks?band=open&limit=50&offset=0&university_id=u1");
    expect(screen.queryByRole("button", { name: /Overdue/ })).toBeNull();
    expect(screen.queryByRole("link", { name: "XYZ University" })).toBeNull();
    expect(screen.getByRole("button", { name: "Add follow-up or task" })).toBeInTheDocument();
  });

  it("says the band is empty, and offers Retry when the list cannot load", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res(page([]))));
    render(<PartnershipTasksPanel role="partnership_manager" />);
    expect(await screen.findByText("Nothing due today.")).toBeInTheDocument();
    cleanup();
    fetchMock.mockImplementation(() => Promise.resolve(res({ detail: "down" }, 500)));
    render(<PartnershipTasksPanel role="partnership_manager" />);
    expect(await screen.findByText("Unable to load follow-ups.")).toBeInTheDocument();
    fetchMock.mockImplementation(() => Promise.resolve(res(page([item]))));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Follow-up call")).toBeInTheDocument();
  });
});
