import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

// AGN-014's commission report is now the Commission tab of the AGN-020 Reports panel (DEC-SCOPE-066 R1; spec §6.2), so the actions area
// under the page no longer mounts a second copy. Its own behaviour is covered by AgentCommissionReportPanel.test.tsx and the
// Master-only tab by AgentReportsPanel.test.tsx / agentReports.test.ts.

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

describe("WorkflowPanel agent Reports (AGN-014 → AGN-020)", () => {
  it.each(["master", null, "staff"] as const)("no longer mounts the commission report under a %s agent's Reports page", (memberRole) => {
    const fetchMock = vi.fn(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    render(<WorkflowPanel user={agent(memberRole)} section="reports" />);
    expect(screen.queryByRole("heading", { name: "Commission report" })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/commissions/report"), expect.anything());
  });

  it("does not show the report on other agent pages", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<WorkflowPanel user={agent("master")} section="dashboard" />);
    expect(screen.queryByRole("heading", { name: "Commission report" })).toBeNull();
  });
});
