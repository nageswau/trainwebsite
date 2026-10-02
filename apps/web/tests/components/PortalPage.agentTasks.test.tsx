import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { ApiError, serverApi } from "@/lib/api";

// AGN-016 browser QA16-01: like Applications (AGN-008 QA8-09), the agency Tasks page shows a Super Admin the section's note instead
// of "Workspace not found"; the portal payload stays the page's role/approval gate for everyone else.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: vi.fn() };
});
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, useSearchParams: () => new URLSearchParams("") }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/WorkflowPanel", () => ({ default: () => null }));
vi.mock("@/components/RefreshOnHistoryNav", () => ({ default: () => null }));
vi.mock("@/components/PortalSection", () => ({ default: () => null }));

const api = vi.mocked(serverApi);

function answer(me: Record<string, unknown>, message: string, status: number) {
  api.mockImplementation((path: string) => (path === "/api/v1/auth/me" ? Promise.resolve(me) : Promise.reject(new ApiError(message, status))));
}

// A default answer in beforeEach (the PortalPage.agentApplications.test.tsx shape): without one, the rejected payload promise of a
// mock installed inside the test is reported by Vitest as unhandled even though the page handles it.
beforeEach(() => {
  api.mockReset();
  api.mockImplementation((path: string) =>
    path === "/api/v1/auth/me" ? Promise.resolve({ id: "s1", role: "super_admin", full_name: "Root", email: "root@example.local" }) : Promise.reject(new ApiError("Workspace not found", 404)),
  );
});
afterEach(cleanup);

describe("PortalPage agent tasks (QA16-01)", () => {
  it("shows a Super Admin the Tasks note instead of Workspace not found", async () => {
    answer({ id: "s1", role: "super_admin", full_name: "Root", email: "root@example.local" }, "Workspace not found", 404);
    render(await PortalPage({ division: "overseas", role: "agent", section: "tasks" }));
    expect(screen.getByRole("heading", { level: 2, name: "Tasks & follow-ups" })).toBeInTheDocument();
    expect(screen.getByText("Agency tasks are managed by the agency's own Masters and Staff.")).toBeInTheDocument();
    expect(screen.queryByText("Workspace not found")).toBeNull();
  });

  it("still refuses a non-agent role with the access-unavailable card", async () => {
    answer({ id: "u1", role: "counselor", full_name: "Cou", email: "c@example.local" }, "Role/division mismatch", 403);
    render(await PortalPage({ division: "overseas", role: "agent", section: "tasks" }));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
    expect(screen.queryByText(/Agency tasks are managed/)).toBeNull();
  });

  it("still shows Workspace not found to a non-Super-Admin who gets a 404", async () => {
    answer({ id: "u2", role: "agent", full_name: "Agent", email: "a@example.local", agent_member_role: "master" }, "Workspace not found", 404);
    render(await PortalPage({ division: "overseas", role: "agent", section: "tasks" }));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
  });
});
