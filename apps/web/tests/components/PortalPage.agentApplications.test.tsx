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
const superAdmin = { id: "s1", role: "super_admin", full_name: "Root", email: "root@example.local" };

beforeEach(() => {
  api.mockReset();
  api.mockImplementation((path: string) =>
    path === "/api/v1/auth/me" ? Promise.resolve(superAdmin) : Promise.reject(new ApiError("Workspace not found", 404)),
  );
});
afterEach(cleanup);

describe("PortalPage agent applications (QA8-09)", () => {
  it("reads only the session for the agent applications section, so a Super Admin sees the section's note", async () => {
    render(await PortalPage({ division: "overseas", role: "agent", section: "applications" }));
    expect(api.mock.calls.map(([path]) => path)).toEqual(["/api/v1/auth/me"]);
    expect(screen.getByText("Agency applications are managed by the agency's own Masters and Staff.")).toBeInTheDocument();
    expect(screen.queryByText("Workspace not found")).toBeNull();
  });

  it("still reads the portal payload for the other agent sections", async () => {
    api.mockImplementation((path: string) =>
      Promise.resolve(path === "/api/v1/auth/me" ? { ...superAdmin, role: "agent", agent_member_role: "master", agent_permissions: [] } : { title: "Dashboard" }),
    );
    render(await PortalPage({ division: "overseas", role: "agent", section: "dashboard" }));
    expect(api.mock.calls.map(([path]) => path)).toEqual(["/api/v1/auth/me", "/api/v1/portal/overseas/agent/dashboard"]);
    expect(screen.getByText("portal section: Dashboard")).toBeInTheDocument();
  });
});
