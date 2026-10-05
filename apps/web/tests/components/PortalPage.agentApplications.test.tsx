import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { ApiError, serverApi } from "@/lib/api";

// AGN-008 QA8-09: the agency Applications page renders AgentApplicationsSection, which reads its own API, so the generic portal
// payload is not fetched there -- a Super Admin then sees the section's note instead of "Workspace not found". Other sections and
// the session read are unchanged. The shell and the workflow panel are stubbed: this is about which server reads happen.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: vi.fn() };
});
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, useSearchParams: () => new URLSearchParams("") }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/WorkflowPanel", () => ({ default: () => null }));
vi.mock("@/components/RefreshOnHistoryNav", () => ({ default: () => null }));
vi.mock("@/components/AgentStudentsSection", () => ({ default: () => <p>students section</p> }));
vi.mock("@/components/PortalSection", () => ({ default: ({ data }: { data: { title: string } }) => <p>portal section: {data.title}</p> }));

const api = vi.mocked(serverApi);
// AGN-017 (DEC-SCOPE-059 N8): every agency page also reads the unread count for the Notifications badge (a failure only drops it).
const UNREAD = "/api/v1/workflows/notifications/unread-count";
const superAdmin ={ id: "s1", role: "super_admin", full_name: "Root", email: "root@example.local" };

beforeEach(() => {
  api.mockReset();
  api.mockImplementation((path: string) =>
    path === "/api/v1/auth/me" ? Promise.resolve(superAdmin) : Promise.reject(new ApiError("Workspace not found", 404)),
  );
});
afterEach(cleanup);

// Fix round 1: the portal payload stays the page's role/approval gate for everyone; only a Super Admin's 404 renders the section.
function refuse(me: Record<string, unknown>, message: string) {
  api.mockImplementation((path: string) => (path === "/api/v1/auth/me" ? Promise.resolve(me) : Promise.reject(new ApiError(message, 403))));
}

describe("PortalPage agent applications (QA8-09)", () => {
  it("shows a Super Admin the section's note instead of the payload's Workspace not found", async () => {
    render(await PortalPage({ division: "overseas", role: "agent", section: "applications" }));
    expect(api.mock.calls.map(([path]) => path)).toEqual(["/api/v1/auth/me", "/api/v1/portal/overseas/agent/applications", UNREAD]);
    expect(screen.getByText("Agency applications are managed by the agency's own Masters and Staff.")).toBeInTheDocument();
    expect(screen.queryByText("Workspace not found")).toBeNull();
  });

  it("still refuses a non-agent role with the access-unavailable card", async () => {
    refuse({ id: "u1", role: "overseas_student", full_name: "Stu", email: "s@example.local" }, "Role/division mismatch");
    render(await PortalPage({ division: "overseas", role: "agent", section: "applications" }));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Role/division mismatch")).toBeInTheDocument();
    expect(screen.queryByText(/Agency applications are managed/)).toBeNull();
    expect(screen.queryByRole("form", { name: "Create application" })).toBeNull();
  });

  it("still refuses a pending agent with the access-unavailable card", async () => {
    refuse({ id: "u2", role: "agent", full_name: "Pending", email: "p@example.local", agent_member_role: "master" }, "Agent registration is pending approval");
    render(await PortalPage({ division: "overseas", role: "agent", section: "applications" }));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Agent registration is pending approval")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Applications" })).toBeNull();
  });

  it("still refuses a non-Super-Admin whose payload is not found", async () => {
    api.mockImplementation((path: string) =>
      path === "/api/v1/auth/me" ? Promise.resolve({ id: "u3", role: "counselor", full_name: "C", email: "c@example.local" }) : Promise.reject(new ApiError("Workspace not found", 404)),
    );
    render(await PortalPage({ division: "overseas", role: "agent", section: "applications" }));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
  });

  it("renders the agency Documents section behind the same gate (AGN-009)", async () => {
    render(await PortalPage({ division: "overseas", role: "agent", section: "documents" }));
    expect(api.mock.calls.map(([path]) => path)).toEqual(["/api/v1/auth/me", "/api/v1/portal/overseas/agent/documents", UNREAD]);
    expect(screen.getByText("Agency documents are managed by the agency's own Masters and Staff.")).toBeInTheDocument();
    refuse({ id: "u4", role: "agent", full_name: "Pending", email: "p2@example.local", agent_member_role: "master" }, "Agent registration is pending approval");
    cleanup();
    render(await PortalPage({ division: "overseas", role: "agent", section: "documents" }));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Documents" })).toBeNull();
  });

  it("still reads the portal payload for the other agent sections", async () => {
    api.mockImplementation((path: string) =>
      Promise.resolve(path === "/api/v1/auth/me" ? { ...superAdmin, role: "agent", agent_member_role: "master", agent_permissions: [] } : { title: "Dashboard" }),
    );
    render(await PortalPage({ division: "overseas", role: "agent", section: "dashboard" }));
    expect(api.mock.calls.map(([path]) => path)).toEqual(["/api/v1/auth/me", "/api/v1/portal/overseas/agent/dashboard", UNREAD]);
    expect(screen.getByText("portal section: Dashboard")).toBeInTheDocument();
  });
});
