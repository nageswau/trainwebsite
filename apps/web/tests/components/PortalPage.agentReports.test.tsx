import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { serverApi } from "@/lib/api";

// AGN-020 (DEC-SCOPE-063 R8; spec §6.1): agency members get the tabbed Reports panel in place of the generic summary table; the portal
// payload is still read as the page's gate (its 403 card for staff without Reports is unchanged); a Super Admin's page is unchanged.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, useSearchParams: () => new URLSearchParams("") }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/WorkflowPanel", () => ({ default: () => null }));
vi.mock("@/components/RefreshOnHistoryNav", () => ({ default: () => null }));
vi.mock("@/components/AgentReportsPanel", () => ({ default: ({ memberRole }: { memberRole: string }) => <p>reports panel for {memberRole}</p> }));

const api = vi.mocked(serverApi);
const payload = { title: "Agent Reports", subtitle: "Application summary.", actions: [], metrics: [], columns: [{ key: "metric", label: "Metric" }, { key: "value", label: "Value" }], rows: [{ metric: "Students", value: 3 }], panels: [] };
const me = (role: string, memberRole: string | null) => ({ id: "u", role, full_name: "U", email: "u@example.local", agent_member_role: memberRole, agent_permissions: null });
const PATHS = ["/api/v1/auth/me", "/api/v1/portal/overseas/agent/reports", "/api/v1/workflows/notifications/unread-count"];

beforeEach(() => api.mockReset());
afterEach(cleanup);

describe("PortalPage agency Reports (AGN-020)", () => {
  it.each(["master", "staff"])("gives a %s the reports panel instead of the old summary table", async (memberRole) => {
    api.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? me("agent", memberRole) : path?.endsWith("unread-count") ? { unread: 0 } : payload));
    render(await PortalPage({ division: "overseas", role: "agent", section: "reports" }));
    expect(screen.getByText(`reports panel for ${memberRole}`)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Agent Reports" })).toBeNull();
    expect(screen.queryByText("Students")).toBeNull();
    expect(api.mock.calls.map(([path]) => path)).toEqual(PATHS);
  });

  it("leaves a Super Admin's Reports page as it was", async () => {
    api.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? me("super_admin", null) : payload));
    render(await PortalPage({ division: "overseas", role: "agent", section: "reports" }));
    expect(screen.queryByText(/reports panel/)).toBeNull();
    expect(screen.getByRole("heading", { name: "Agent Reports" })).toBeInTheDocument();
  });
});
