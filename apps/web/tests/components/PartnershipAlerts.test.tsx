import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AlertsPage from "@/app/partnership/alerts/page";
import PartnershipDashboardPage from "@/app/partnership/dashboard/page";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { type NavItem, PARTNERSHIP_HEAD_NAV, PARTNERSHIP_NAV } from "@/lib/navigation";
import { alertsHref, chosenKind, type AlertItem, type AlertPage, withAlertBadge } from "@/lib/partnershipAlerts";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/partnership/alerts" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const manager = { id: "m1", full_name: "Rahul", role: "partnership_manager" };
const alert = (over: Partial<AlertItem> = {}): AlertItem => ({
  id: "n1", kind: "agreement_expiry", title: "Agreement expires in 30 days", read: false, created_at: "2026-10-10T03:30:00Z",
  body: "⚠️ ABC University partnership expires in 30 days. Renewal action required. MOU-000012 (MoU) expires on 09 Nov 2026.",
  action_url: "/partnership/universities/u1#uni-agreements", ...over,
});
const page = (over: Partial<AlertPage> = {}): AlertPage => ({ items: [alert()], total: 1, unread: 3, limit: 25, offset: 0, ...over });
const message = (node: unknown) => (node as { props: { message?: string } }).props.message;
const shellOf = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === PortalShell)!;
const shell = (tree: ReturnType<typeof elements>) => render(<>{shellOf(tree).props.children}</>);
const alertsBadge = (tree: ReturnType<typeof elements>) => (shellOf(tree).props.nav as NavItem[]).find((x) => x.href === "/partnership/alerts")?.badge;

function answer(routes: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const hit = Object.keys(routes).find((p) => path === p || path.startsWith(`${p}?`));
    if (!hit) throw new ApiError("unexpected", 500);
    const value = routes[hit];
    if (value instanceof Error) throw value;
    return value as never;
  });
}

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(() => cleanup());

describe("upc-015 helpers", () => {
  it("keeps a known kind from the URL and falls back to all alerts", () => {
    expect(chosenKind("milestone_delayed")).toBe("milestone_delayed");
    expect(chosenKind("bogus")).toBe("all");
    expect(chosenKind(undefined)).toBe("all");
    expect(alertsHref("all")).toBe("/partnership/alerts");
    expect(alertsHref("overdue_digest", 25)).toBe("/partnership/alerts?kind=overdue_digest&offset=25");
  });

  it("puts the unread count on the Alerts entry, and leaves the nav alone when it cannot be read", async () => {
    answer({ "/api/v1/partnership/alerts": page({ unread: 4 }) });
    const nav = await withAlertBadge(PARTNERSHIP_NAV);
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/alerts?limit=1");
    expect(nav.find((x) => x.href === "/partnership/alerts")?.badge).toBe(4);
    answer({ "/api/v1/partnership/alerts": new ApiError("down", 500) });
    expect(await withAlertBadge(PARTNERSHIP_NAV)).toBe(PARTNERSHIP_NAV);
  });
});

describe("upc-015 navigation (§32 Alerts)", () => {
  it("is live for managers and listed for heads", () => {
    expect(PARTNERSHIP_NAV).toContainEqual({ label: "Alerts", href: "/partnership/alerts" });
    expect(PARTNERSHIP_HEAD_NAV).toContainEqual({ label: "Alerts", href: "/partnership/alerts" });
  });
});

describe("upc-015 Alerts page", () => {
  it("lists the caller's alerts for the kind in the URL, with the badge and an Open link", async () => {
    answer({ "/api/v1/auth/me": manager, "/api/v1/partnership/alerts": page() });
    const tree = elements(await AlertsPage({ searchParams: Promise.resolve({ kind: "agreement_expiry" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/alerts?kind=agreement_expiry&limit=25&offset=0");
    expect(alertsBadge(tree)).toBe(3);
    shell(tree);
    expect(screen.getByRole("heading", { name: "Alerts" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Agreement expiry" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "All alerts" })).toHaveAttribute("href", "/partnership/alerts");
    const list = screen.getByRole("list", { name: "Notifications" });
    expect(within(list).getByText(/ABC University partnership expires in 30 days/)).toBeInTheDocument();
    expect(within(list).getByText("new")).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: "Open: Agreement expires in 30 days" })).toHaveAttribute("href", "/partnership/universities/u1#uni-agreements");
  });

  it("says what each kind will show when there is nothing yet", async () => {
    answer({ "/api/v1/auth/me": manager, "/api/v1/partnership/alerts": page({ items: [], total: 0, unread: 0 }) });
    shell(elements(await AlertsPage({ searchParams: Promise.resolve({ kind: "milestone_delayed" }) })));
    expect(screen.getByText("No delayed milestones. A milestone appears here the day after its target date passes without being achieved.")).toBeInTheDocument();
    cleanup();
    answer({ "/api/v1/auth/me": manager, "/api/v1/partnership/alerts": page({ items: [], total: 0, unread: 0 }) });
    shell(elements(await AlertsPage({ searchParams: Promise.resolve({}) })));
    expect(screen.getByText(/No alerts yet\./)).toBeInTheDocument();
  });

  it("pages through a long list and recovers from a page past the end", async () => {
    answer({ "/api/v1/auth/me": manager, "/api/v1/partnership/alerts": page({ total: 30, offset: 25 }) });
    shell(elements(await AlertsPage({ searchParams: Promise.resolve({ offset: "25" }) })));
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/partnership/alerts");
    expect(screen.getByText("26–26 of 30")).toBeInTheDocument();
    cleanup();
    answer({ "/api/v1/auth/me": manager, "/api/v1/partnership/alerts": page({ items: [], total: 3, offset: 50 }) });
    shell(elements(await AlertsPage({ searchParams: Promise.resolve({ offset: "50" }) })));
    expect(screen.getByRole("link", { name: "Go to the first page" })).toHaveAttribute("href", "/partnership/alerts");
  });

  it("another role is refused before the list is asked for", async () => {
    answer({ "/api/v1/auth/me": { id: "o1", full_name: "Omar", role: "overseas_admin" } });
    expect(message(await AlertsPage({ searchParams: Promise.resolve({}) }))).toBe("Partnership alerts access required");
    expect(serverApi).toHaveBeenCalledTimes(1);
  });
});

describe("upc-015 badge on the manager dashboard", () => {
  it("shows the unread alerts on the sidebar", async () => {
    const me = { id: "m1", full_name: "Rahul", email: "r@x.in", role: "partnership_manager", partnership_profile: { employee_id: "E1", reporting_head: { id: "h1", full_name: "Hema" } } };
    answer({ "/api/v1/partnership/me": me, "/api/v1/partnership/alerts": page({ unread: 2 }) });
    const tree = elements(await PartnershipDashboardPage());
    expect(alertsBadge(tree)).toBe(2);
  });
});
