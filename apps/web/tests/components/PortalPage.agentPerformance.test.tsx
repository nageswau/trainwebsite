import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { ApiError, serverApi } from "@/lib/api";

// AGN-019 review finding #1: the Staff Performance page must open -- the portal payload is its role/approval gate (a header-only
// section, the Tasks precedent), and the page itself is AgentPerformanceSection.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: vi.fn() };
});
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, useSearchParams: () => new URLSearchParams("") }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/WorkflowPanel", () => ({ default: () => null }));
vi.mock("@/components/RefreshOnHistoryNav", () => ({ default: () => null }));
vi.mock("@/components/PortalSection", () => ({ default: () => null }));
vi.mock("@/components/AgentPerformancePanel", () => ({ default: () => <p>performance panel</p> }));

const api = vi.mocked(serverApi);
const HEADER = { title: "Staff performance", subtitle: "", metrics: [], tables: [] };

function answer(me: Record<string, unknown>) {
  api.mockImplementation((path: string) => {
    if (path === "/api/v1/auth/me") return Promise.resolve(me);
    if (path === "/api/v1/portal/overseas/agent/performance") return Promise.resolve(HEADER);
    if (path === "/api/v1/workflows/notifications/unread-count") return Promise.resolve({ unread: 0 });
    return Promise.reject(new ApiError(`unexpected ${path}`, 500));
  });
}

// A block body: a function returned from beforeEach is run by Vitest as a cleanup hook (mockReset returns the mock).
beforeEach(() => {
  api.mockReset();
});
afterEach(cleanup);

describe("PortalPage agent performance (AGN-019)", () => {
  it("opens for a Master", async () => {
    answer({ id: "m1", role: "agent", full_name: "Mia", email: "m@example.local", agent_member_role: "master" });
    render(await PortalPage({ division: "overseas", role: "agent", section: "performance" }));
    expect(screen.getByRole("heading", { level: 2, name: "Staff performance" })).toBeInTheDocument();
    expect(screen.getByText("performance panel")).toBeInTheDocument();
    expect(screen.queryByText("Workspace not found")).toBeNull();
  });

  it("tells staff it is for Masters instead of Workspace not found", async () => {
    answer({ id: "s1", role: "agent", full_name: "Sam", email: "s@example.local", agent_member_role: "staff" });
    render(await PortalPage({ division: "overseas", role: "agent", section: "performance" }));
    expect(screen.getByText("Staff performance is available to agency Masters.")).toBeInTheDocument();
    expect(screen.queryByText("performance panel")).toBeNull();
  });
});
