import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentDetailPanel from "@/components/AgentStudentDetailPanel";
import type { AgentStudentDetail } from "@/lib/agentStudents";

const res = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const detail: AgentStudentDetail = {
  id: "s1",
  has_login: false,
  full_name: "Asha Rao",
  email: null,
  phone: null,
  preferred_country: null,
  preferred_intake: null,
  status: "active",
  assigned_to: null,
  created_at: "2026-10-01T09:00:00Z",
  date_of_birth: null,
  highest_qualification: null,
  institution: null,
  graduation_year: null,
  preferred_course: null,
  notes: null,
  created_by: "Master",
  archived_at: null,
  archived_by: null,
  updated_at: "2026-10-01T09:00:00Z",
  counseling: null,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentStudentDetailPanel journey (AGN-015)", () => {
  it("shows the Journey and the history toggle on the record, and hides them while a form is open", async () => {
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(res(url.endsWith("/journey") ? { student: { id: "s1" }, steps: [{ key: "create", state: "done" }], applications: [] } : { items: [], total: 0, limit: 20, offset: 0 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentDetailPanel detail={detail} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByRole("region", { name: "Journey" })).toBeInTheDocument();
    expect(await screen.findByRole("list", { name: "Student steps" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show history" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/timeline"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.queryByRole("region", { name: "Journey" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Show history" })).toBeNull();
  });

  // QA15-01: a change made in the panel's own shortlist or task list must reach the tracker and an open history without reopening.
  const entry = { id: "e1", university: { source: "agency", id: "u1", name: "Agency U", slug: null, country: "Malta" }, course: { id: null, title: null }, intake: null, tuition_fee: null, entry_requirements: null, created_by: "M", created_at: "", updated_at: "" };
  const task = { id: "t1", title: "Call Asha", notes: null, due_at: "2026-10-05T04:00:00Z", status: "open", overdue: false, student: { id: "s1", full_name: "Asha Rao", status: "active" }, application: null, assigned_to: null, created_by: "Master", closed_by: null, closed_at: null, created_at: "", updated_at: "" };
  const page = (items: unknown[]) => ({ items, total: items.length, limit: 20, offset: 0 });

  function world() {
    const state = { shortlisted: true, taskOpen: true, timelineCalls: 0 };
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (init?.method === "DELETE") {
        state.shortlisted = false;
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (init?.method === "PATCH") {
        state.taskOpen = false;
        return Promise.resolve(res({ task: { ...task, status: "done" } }));
      }
      if (u.endsWith("/journey"))
        return Promise.resolve(res({ student: { id: "s1" }, steps: [{ key: "create", state: "done" }, { key: "shortlist", state: state.shortlisted ? "done" : "not_started" }], applications: [] }));
      if (u.includes("/timeline")) {
        state.timelineCalls += 1;
        return Promise.resolve(res(page([])));
      }
      if (u.includes("/shortlist")) return Promise.resolve(res(page(state.shortlisted ? [entry] : [])));
      if (u.includes("/crm/tasks")) return Promise.resolve(res(page(state.taskOpen ? [task] : [])));
      return Promise.resolve(res(page([])));
    });
    vi.stubGlobal("fetch", fetchMock);
    return state;
  }

  const shortlistStep = () => screen.getByRole("list", { name: "Student steps" }).querySelectorAll("li")[1];

  it("reloads the tracker after a shortlist entry is removed in the panel (QA15-01)", async () => {
    world();
    render(<AgentStudentDetailPanel detail={detail} onClose={() => {}} onSaved={() => {}} />);
    await screen.findByRole("list", { name: "Student steps" });
    await waitFor(() => expect(shortlistStep()).toHaveTextContent("Done"));
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await waitFor(() => expect(shortlistStep()).toHaveTextContent("Not started"));
  });

  it("reloads an open history after a task is closed in the panel (QA15-01)", async () => {
    const state = world();
    render(<AgentStudentDetailPanel detail={detail} onClose={() => {}} onSaved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    await waitFor(() => expect(state.timelineCalls).toBe(1));
    fireEvent.click(await screen.findByRole("button", { name: "Mark “Call Asha” done" }));
    await waitFor(() => expect(state.timelineCalls).toBe(2));
  });
});
