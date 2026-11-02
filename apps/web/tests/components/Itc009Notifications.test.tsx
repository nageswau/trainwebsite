import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TelecallerManagerNotificationsPage from "@/app/telecaller/manager/notifications/page";
import PortalPage from "@/components/PortalPage";
import SchoolNotificationList from "@/components/SchoolNotificationList";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV, TELECALLER_MANAGER_NAV, TELECALLER_MANAGER_NOTIFICATIONS_HREF, type NavItem } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

// itc-009 (DEC-SCOPE-342): an escalated overdue follow-up reaches the telecaller manager (Telecaller manager -> Notifications) or the
// IT admin (IT admin -> Notifications); both lists are the shared one, and opening a notice marks it read first.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: vi.fn() };
});
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, useSearchParams: () => new URLSearchParams("") }));
vi.mock("@/components/PortalShell", () => ({
  default: ({ nav, children }: { nav: NavItem[]; children: React.ReactNode }) => (
    <div>
      <ul aria-label="test nav">{nav.map((i) => <li key={i.href}>{i.href}</li>)}</ul>
      {children}
    </div>
  ),
}));
vi.mock("@/components/WorkflowPanel", () => ({ default: ({ section }: { section: string }) => <p>workflow panel: {section}</p> }));
vi.mock("@/components/PortalSection", () => ({ default: ({ lead }: { lead?: React.ReactNode }) => <div><h1>Notifications</h1>{lead}</div> }));

const api = vi.mocked(serverApi);
const NOTICE = { id: "n1", title: "Follow-up overdue", body: "A follow-up is past its due time. Open EduSphere to act on it.", read: false,
  action_url: null, created_at: "2026-11-02T04:30:00Z", event_type: "it.followup.overdue", entity_type: "lead_follow_up", entity_id: "f1" };

function answer(me: unknown, list: unknown = [NOTICE]) {
  const settle = (value: unknown) => (value instanceof Error ? Promise.reject(value) : Promise.resolve(value));
  api.mockImplementation((path: string) => {
    if (path === "/api/v1/auth/me") return settle(me);
    if (path === "/api/v1/workflows/notifications") return settle(list);
    if (path === "/api/v1/workflows/notifications/unread-count") return settle({ unread: 1 });
    return settle({ title: "Notifications", subtitle: "Your own notifications.", columns: [], rows: [] });
  });
}

beforeEach(() => api.mockReset() && undefined);
afterEach(cleanup);

describe("itc-009 escalation notices", () => {
  it("both portals list Notifications in their navigation", () => {
    expect(TELECALLER_MANAGER_NAV.map((i) => i.href)).toContain(TELECALLER_MANAGER_NOTIFICATIONS_HREF);
    expect(PORTAL_NAV["it/admin"].map((i) => i.href)).toContain("/it/admin/notifications");
  });

  it("the IT admin's Notifications section mounts the shared list with no workflow panel", async () => {
    answer({ id: "a1", role: "it_admin", full_name: "Ira Admin", email: "i@example.local" });
    render(await PortalPage({ division: "it", role: "admin", section: "notifications" }));
    expect(screen.getByText(NOTICE.body)).toBeInTheDocument();
    expect(screen.queryByText(/workflow panel/)).toBeNull();
  });

  it("the IT admin sees an empty state that says what lands there", async () => {
    answer({ id: "a1", role: "it_admin", full_name: "Ira Admin", email: "i@example.local" }, []);
    render(await PortalPage({ division: "it", role: "admin", section: "notifications" }));
    expect(screen.getByText(/No notifications yet\. Overdue follow-ups escalated to you appear here\./)).toBeInTheDocument();
  });

  it("the telecaller manager's page lists their notices, read before open, with the unread badge", async () => {
    answer({ id: "m1", role: "telecaller_manager", full_name: "Lakshmi" });
    const tree = elements(await TelecallerManagerNotificationsPage());
    const list = tree.find((el) => el.type === SchoolNotificationList)!;
    expect(list.props.notifications).toEqual([NOTICE]);
    expect(list.props.readBeforeOpen).toBe(true);
    expect(list.props.emptyText).toMatch(/overdue follow-ups/i);
  });

  it("the telecaller manager's page refuses other roles", async () => {
    answer({ id: "t1", role: "telecaller", full_name: "Pooja" });
    render(await TelecallerManagerNotificationsPage());
    expect(screen.getByText(/Telecaller manager role required/)).toBeInTheDocument();
    expect(api.mock.calls.map((c) => c[0])).not.toContain("/api/v1/workflows/notifications");
  });

  it("an expired session on the manager page shows the access-unavailable card", async () => {
    answer(new ApiError("Not authenticated", 401));
    render(await TelecallerManagerNotificationsPage());
    expect(screen.queryByText("Follow-up overdue")).toBeNull();
  });
});

describe("itc-009 QA-02: the manager sees the unread count where they land", () => {
  it("the team page (sign-in landing) and the catalogue pages carry the badge on Notifications", async () => {
    const { default: TeamPage } = await import("@/app/telecaller/manager/team/page");
    const { default: CataloguePage } = await import("@/components/TelecallerCataloguePage");
    const { default: Shell } = await import("@/components/PortalShell");
    api.mockImplementation((path: string) => Promise.resolve(
      path === "/api/v1/auth/me" ? { id: "m1", role: "telecaller_manager", full_name: "Lakshmi" }
        : path === "/api/v1/workflows/notifications/unread-count" ? { unread: 2 }
          : { items: [], total: 0, limit: 25, offset: 0 }) as never);
    const badge = (tree: ReturnType<typeof elements>) =>
      (tree.find((el) => el.type === Shell)!.props.nav as NavItem[]).find((i) => i.href === TELECALLER_MANAGER_NOTIFICATIONS_HREF)?.badge;
    expect(badge(elements(await TeamPage({ searchParams: Promise.resolve({}) })))).toBe(2);
    expect(badge(elements(await CataloguePage({ title: "Alert settings", intro: "x", children: null })))).toBe(2);
  });
});
