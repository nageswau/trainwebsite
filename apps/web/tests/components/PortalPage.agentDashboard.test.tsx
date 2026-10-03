import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { serverApi } from "@/lib/api";

// AGN-018 (DEC-SCOPE-060; spec §6.1): agents get the KPI board under the page title (the duplicate metric tiles go); the portal
// payload is still read as the page's gate; a Super Admin's dashboard is unchanged.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, useSearchParams: () => new URLSearchParams("") }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/WorkflowPanel", () => ({ default: () => null }));
vi.mock("@/components/RefreshOnHistoryNav", () => ({ default: () => null }));
vi.mock("@/components/AgentDashboardPanel", () => ({ default: () => <p>agent board</p>, AgentDashboardSkeleton: () => <p>board loading</p> }));

const api = vi.mocked(serverApi);
const payload = { title: "Agent Dashboard", subtitle: "Your students", actions: [], metrics: [{ label: "Students", value: 4 }], columns: [], rows: [], panels: [] };
const me = (role: string) => ({ id: "u", role, full_name: "U", email: "u@example.local", agent_member_role: role === "agent" ? "master" : null, agent_permissions: null });

beforeEach(() => api.mockReset());
afterEach(cleanup);

describe("PortalPage agency dashboard (AGN-018)", () => {
  it("puts the board under the title and drops the duplicate metric tiles for agents", async () => {
    api.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? me("agent") : path?.endsWith("unread-count") ? { unread: 0 } : payload));
    const { container } = render(await PortalPage({ division: "overseas", role: "agent", section: "dashboard" }));
    expect(await screen.findByText("agent board")).toBeInTheDocument();
    const heading = screen.getByRole("heading", { name: "Agent Dashboard" });
    expect(heading.compareDocumentPosition(screen.getByText("agent board")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector(".metric-grid")).toBeNull();
    expect(api.mock.calls.map(([path]) => path)).toEqual(["/api/v1/auth/me", "/api/v1/portal/overseas/agent/dashboard", "/api/v1/workflows/notifications/unread-count"]);
  });

  it("leaves a Super Admin's dashboard as it was", async () => {
    api.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? me("super_admin") : payload));
    const { container } = render(await PortalPage({ division: "overseas", role: "agent", section: "dashboard" }));
    expect(screen.queryByText("agent board")).toBeNull();
    expect(container.querySelector(".metric-grid")).not.toBeNull();
  });
});
