import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { ApiError, serverApi } from "@/lib/api";
import type { NavItem } from "@/lib/navigation";

// AGN-017 (DEC-SCOPE-059 N7/N8): the agency Notifications section reads the existing list; every agency page carries the unread count
// on the Notifications nav item, and a failed count never breaks the page.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: vi.fn() };
});
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, useSearchParams: () => new URLSearchParams("") }));
vi.mock("@/components/PortalShell", () => ({
  default: ({ nav, children }: { nav: NavItem[]; children: React.ReactNode }) => (
    <div>
      <ul aria-label="test nav">{nav.map((i) => <li key={i.href}>{`${i.label}:${i.badge ?? 0}`}</li>)}</ul>
      {children}
    </div>
  ),
}));
vi.mock("@/components/WorkflowPanel", () => ({ default: ({ section }: { section: string }) => <p>workflow panel: {section}</p> }));
vi.mock("@/components/RefreshOnHistoryNav", () => ({ default: () => null }));
vi.mock("@/components/PortalSection", () => ({ default: () => <p>generic section</p> }));
vi.mock("@/components/AgentTasksSection", () => ({ default: () => <p>tasks section</p> }));

const api = vi.mocked(serverApi);
const AGENT = { id: "s1", role: "agent", full_name: "Staff", email: "s@example.local", agent_member_role: "staff" };
const LIST = [{ id: "n1", title: "Student assigned to you", body: "A student is now assigned to you.", read: false, action_url: "/overseas/agent/students", created_at: "2026-10-02T04:30:00Z" }];

type Answers = { me?: unknown; payload?: unknown; unread?: unknown; list?: unknown };

// The portal payload is the page's role/approval gate: an agency member gets its header (services/portal.py), a Super Admin a 404.
function answer({ me = AGENT, payload = { title: "Notifications", subtitle: "Your own notifications.", columns: [], rows: [] }, unread = { unread: 2 }, list = LIST }: Answers) {
  const settle = (value: unknown) => (value instanceof Error ? Promise.reject(value) : Promise.resolve(value));
  api.mockImplementation((path: string) => {
    if (path === "/api/v1/auth/me") return settle(me);
    if (path === "/api/v1/workflows/notifications/unread-count") return settle(unread);
    if (path === "/api/v1/workflows/notifications") return settle(list);
    return settle(payload);
  });
}

beforeEach(() => {
  api.mockReset();
  answer({});
});
afterEach(cleanup);

describe("PortalPage agent notifications (AGN-017)", () => {
  it("renders the Notifications section from the existing list, with the badge on its nav item", async () => {
    render(await PortalPage({ division: "overseas", role: "agent", section: "notifications" }));
    expect(screen.getByRole("heading", { level: 1, name: "Notifications" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open: Student assigned to you" })).toBeInTheDocument();
    expect(screen.getByText("Notifications:2")).toBeInTheDocument();
    expect(screen.getByText("Tasks & Follow-ups:0")).toBeInTheDocument(); // AGN-018 (DEC-SCOPE-061 G4): the EVID-015 §4 label
  });

  it("carries the badge on other agency pages too", async () => {
    answer({ payload: { title: "Tasks", rows: [] } });
    render(await PortalPage({ division: "overseas", role: "agent", section: "tasks" }));
    expect(screen.getByText("Notifications:2")).toBeInTheDocument();
  });

  it("keeps the page when the count fails, without a badge", async () => {
    answer({ unread: new ApiError("Server error", 500) });
    render(await PortalPage({ division: "overseas", role: "agent", section: "notifications" }));
    expect(screen.getByText("Notifications:0")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Notifications" })).toBeInTheDocument();
  });

  it("shows the section-unavailable state when the list fails", async () => {
    answer({ list: new ApiError("Server error", 500) });
    render(await PortalPage({ division: "overseas", role: "agent", section: "notifications" }));
    expect(screen.getByRole("status")).toHaveTextContent("This section couldn't load. Refresh to try again.");
  });

  it("shows the access-unavailable card when the session has expired", async () => {
    answer({ list: new ApiError("Not authenticated", 401) });
    render(await PortalPage({ division: "overseas", role: "agent", section: "notifications" }));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
  });

  it("shows a Super Admin the section's note instead of Workspace not found, without an agency badge", async () => {
    answer({ me: { id: "r1", role: "super_admin", full_name: "Root", email: "r@example.local" }, payload: new ApiError("Workspace not found", 404) });
    render(await PortalPage({ division: "overseas", role: "agent", section: "notifications" }));
    expect(screen.getByText("Agency notifications go to the agency's own Masters and Staff.")).toBeInTheDocument();
    expect(screen.getByText("Notifications:0")).toBeInTheDocument();
    // Browser QA QA17-06: the generic admin "Send notification" form is not this page's; other sections keep their panel.
    expect(screen.queryByText(/workflow panel/)).toBeNull();
  });

  it("keeps the workflow panel on the other agency sections", async () => {
    answer({ payload: { title: "Tasks", rows: [] } });
    render(await PortalPage({ division: "overseas", role: "agent", section: "tasks" }));
    expect(screen.getByText("workflow panel: tasks")).toBeInTheDocument();
  });

  it("still refuses a non-agent role with the access-unavailable card", async () => {
    answer({ me: { id: "c1", role: "counselor", full_name: "Cou", email: "c@example.local" }, payload: new ApiError("Role/division mismatch", 403) });
    render(await PortalPage({ division: "overseas", role: "agent", section: "notifications" }));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
  });
});
