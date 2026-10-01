import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentsSection from "@/components/AgentStudentsSection";
import type { User } from "@/lib/types";

const user = (over: Partial<User>): User => ({ id: "u1", email: "u@x.com", full_name: "U", role: "agent", division: "overseas", profile: {}, ...over });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// AGN-005 browser QA (owner, 2026-10-01): the agency Students page intro follows the caller.
describe("AgentStudentsSection (AGN-005 QA5-03, QA5-05)", () => {
  it("tells a Master it lists every student of the agency and shows the students panel", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ items: [], total: 0, limit: 20, offset: 0 }))));
    render(<AgentStudentsSection user={user({ agent_member_role: "master" })} />);
    expect(screen.getByRole("heading", { name: "Students" })).toBeInTheDocument();
    expect(screen.getByText(/^Every student of your agency, with or without a login\./)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Add student" })).toBeInTheDocument();
  });

  it("tells staff it lists the students assigned to them (QA5-03)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ items: [], total: 0, limit: 20, offset: 0 }))));
    render(<AgentStudentsSection user={user({ agent_member_role: "staff" })} />);
    expect(screen.getByText(/^Students assigned to you, with or without a login\./)).toBeInTheDocument();
    expect(screen.queryByText(/Every student of your agency/)).toBeNull();
    expect(await screen.findByRole("button", { name: "Add student" })).toBeInTheDocument();
  });

  it("shows anyone outside an agency a note instead of a panel that can only fail (QA5-05)", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentsSection user={user({ role: "super_admin", division: "global", agent_member_role: null })} />);
    expect(screen.getByText("Agency student records are managed by the agency's own Masters and Staff.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add student" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
