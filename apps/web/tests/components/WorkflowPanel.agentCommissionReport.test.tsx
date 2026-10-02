import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const agent = (memberRole: "master" | "staff" | null) =>
  ({
    id: "u1",
    email: "a@example.local",
    full_name: "A",
    role: "agent",
    division: "overseas",
    profile: {},
    agent_member_role: memberRole,
    agent_permissions: memberRole === "staff" ? { can_verify_documents: false, can_view_reports: true } : null,
  }) as unknown as User;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WorkflowPanel agent Reports (AGN-014)", () => {
  it.each(["master", null] as const)("shows the commission report to a %s agent", (memberRole) => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<WorkflowPanel user={agent(memberRole)} section="reports" />);
    expect(screen.getByRole("heading", { name: "Commission report" })).toBeInTheDocument();
  });

  it("never shows staff the commission report, even with Reports on", () => {
    const fetchMock = vi.fn(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    render(<WorkflowPanel user={agent("staff")} section="reports" />);
    expect(screen.queryByRole("heading", { name: "Commission report" })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/commissions/report"), expect.anything());
  });

  it("does not show the report on other agent pages", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<WorkflowPanel user={agent("master")} section="dashboard" />);
    expect(screen.queryByRole("heading", { name: "Commission report" })).toBeNull();
  });
});
