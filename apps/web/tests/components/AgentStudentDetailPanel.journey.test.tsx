import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
});
