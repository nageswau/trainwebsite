import { beforeEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";
import SchoolNotificationList from "@/components/SchoolNotificationList";
import ManagerNotifications from "@/app/bdm/manager/notifications/page";
import ManagerDashboard from "@/app/bdm/manager/dashboard/page";
import BdmNotifications from "@/app/bdm/notifications/page";
import MyTrips from "@/app/bdm/travel/page";
import MyDay from "@/app/bdm/my-day/page";
import { ApiError, serverApi } from "@/lib/api";
import { bdmManagerNav, bdmNav } from "@/lib/bdmNav";
import { BDM_MANAGER_NOTIFICATIONS_HREF, BDM_NOTIFICATIONS_HREF } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const me = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it",
  bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const notice = { id: "n1", title: "Trip approved", body: "TRV-000001: Hyderabad → Vijayawada, 03 Oct 2026", read: false, action_url: "/bdm/travel/t1", created_at: "2026-10-03T05:00:00Z" };

function answer(byPath: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const key = Object.keys(byPath).find((k) => path.startsWith(k));
    if (!key) throw new Error(`unexpected ${path}`);
    const value = byPath[key];
    if (value instanceof Error) throw value;
    return value as never;
  });
}
const badgeOn = (tree: ReturnType<typeof elements>, href: string) =>
  (tree.find((el) => el.type === PortalShell)!.props.nav as { href: string; badge?: number }[]).find((i) => i.href === href)?.badge;

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("bdm-010 QA10-01 notifications for BDMs and managers", () => {
  it("the nav helpers put the unread count on Notifications, and leave it off when the count can't be read", async () => {
    answer({ "/api/v1/workflows/notifications/unread-count": { unread: 3 } });
    expect((await bdmNav()).find((i) => i.href === BDM_NOTIFICATIONS_HREF)!.badge).toBe(3);
    expect((await bdmManagerNav()).find((i) => i.href === BDM_MANAGER_NOTIFICATIONS_HREF)!.badge).toBe(3);
    answer({ "/api/v1/workflows/notifications/unread-count": new ApiError("boom", 500) });
    expect((await bdmNav()).find((i) => i.href === BDM_NOTIFICATIONS_HREF)!.badge).toBeUndefined();
  });

  it("the BDM's notifications page lists their notices, opening one marks it read", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/workflows/notifications/unread-count": { unread: 1 }, "/api/v1/workflows/notifications": [notice] });
    const tree = elements(await BdmNotifications());
    const list = tree.find((el) => el.type === SchoolNotificationList)!;
    expect(list.props.notifications).toEqual([notice]);
    expect(list.props.readBeforeOpen).toBe(true);
    expect(badgeOn(tree, BDM_NOTIFICATIONS_HREF)).toBe(1);
    expect(list.props.emptyText).toMatch(/reminders/); // bdm-012: reminders land here too
  });

  it("the manager's notifications page is for BDM managers", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Meera", role: "bdm_manager" }, "/api/v1/workflows/notifications/unread-count": { unread: 0 }, "/api/v1/workflows/notifications": [] });
    const tree = elements(await ManagerNotifications());
    expect(tree.find((el) => el.type === SchoolNotificationList)!.props.emptyText).toMatch(/No notifications yet/);
    answer({ "/api/v1/auth/me": { full_name: "Asha", role: "bdm" } });
    const denied = elements(await ManagerNotifications()).find((el) => typeof el.props.message === "string")!;
    expect(denied.props.message).toBe("BDM manager role required");
  });

  it("every BDM and manager page shows the badge, not only the notifications page", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/workflows/notifications/unread-count": { unread: 2 }, "/api/v1/bdm/trips": { items: [], total: 0, limit: 50, offset: 0 } });
    expect(badgeOn(elements(await MyTrips({ searchParams: Promise.resolve({}) })), BDM_NOTIFICATIONS_HREF)).toBe(2);
    expect(badgeOn(elements(await MyDay()), BDM_NOTIFICATIONS_HREF)).toBe(2);
    answer({ "/api/v1/auth/me": { full_name: "Meera" }, "/api/v1/workflows/notifications/unread-count": { unread: 4 }, "/api/v1/bdm/manager/team": { items: [], total: 0, limit: 50, offset: 0 } });
    expect(badgeOn(elements(await ManagerDashboard({ searchParams: Promise.resolve({}) })), BDM_MANAGER_NOTIFICATIONS_HREF)).toBe(4);
  });
});
