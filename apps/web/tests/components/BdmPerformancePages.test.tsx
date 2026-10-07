import { notFound } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmHierarchy from "@/components/BdmHierarchy";
import { PerformanceFilters, PerformanceLoadError } from "@/components/BdmPerformanceControls";
import BdmPerformanceFigures from "@/components/BdmPerformanceFigures";
import BdmPerformanceTable from "@/components/BdmPerformanceTable";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import HierarchyPage from "@/app/bdm/manager/hierarchy/page";
import PerformancePage from "@/app/bdm/manager/performance/page";
import TypePage from "@/app/bdm/manager/performance/[type]/page";
import BdmPage from "@/app/bdm/manager/performance/bdms/[id]/page";
import { elements, text } from "@/tests/helpers/elementTree";

// bdm-024 (DEC-SCOPE-113): the four pages -- the role's shell and filters, what each sends to the API, and the inline failure.
vi.mock("next/navigation", () => ({
  notFound: vi.fn(() => { throw new Error("NEXT_NOT_FOUND"); }), redirect: vi.fn(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const M1 = "11111111-1111-4111-8111-111111111111";
const B1 = "22222222-2222-4222-8222-222222222222";
const MANAGER = { full_name: "Meera", role: "bdm_manager" };
const ROOT = { full_name: "Root", role: "super_admin" };
const performance = (over = {}) => ({ from: "2026-10-01", to: "2026-10-31", manager: null, type: null, rows: [], bdms: [], ...over });
const figures = { meetings: 1, trips: 1, new_organizations: 0, mous: 0, leads: 2, students: 1, revenue: "10.00" };

function answer(map: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path in map) {
      const value = map[path];
      if (value instanceof Error) throw value;
      return value as never;
    }
    if (path === "/api/v1/workflows/notifications/unread-count") return { unread: 0 } as never;
    if (path === "/api/v1/admin/bdm-managers?limit=100") return { items: [{ id: M1, full_name: "Meera", email: "m@x.local" }], total: 1 } as never;
    throw new ApiError("Not found", 404);
  });
}
const sp = <T,>(value: T) => Promise.resolve(value);
const allText = (tree: ReturnType<typeof elements>) => tree.map((el) => text(el)).join(" ");
const failure = (tree: ReturnType<typeof elements>) =>
  tree.find((el) => el.type === PerformanceLoadError)?.props as { message: string; retryHref: string; reset: { href: string; label: string } } | undefined;
const filtersOf = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === PerformanceFilters)!.props as { managers?: unknown[]; period: unknown };

describe("bdm-024 performance pages", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });

  it("a manager reads their team's table for the requested period; no team picker", async () => {
    answer({ "/api/v1/auth/me": MANAGER, "/api/v1/bdm/manager/performance?from=2026-09-01&to=2026-09-30": performance({ from: "2026-09-01", to: "2026-09-30" }) });
    const tree = elements(await PerformancePage({ searchParams: sp({ from: "2026-09-01", to: "2026-09-30", manager: M1 }) }));
    expect(tree.find((el) => el.type === BdmPerformanceTable)).toBeTruthy();
    expect(allText(tree)).toContain("Your team");
    expect(filtersOf(tree).managers).toBeUndefined();
    expect(filtersOf(tree).period).toEqual({ from: "2026-09-01", to: "2026-09-30" });
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("BDM Manager");
  });

  it("super_admin keeps the admin navigation and may narrow to one manager's team", async () => {
    answer({ "/api/v1/auth/me": ROOT, [`/api/v1/bdm/manager/performance?manager_user_id=${M1}`]: performance({ manager: { id: M1, full_name: "Meera" } }) });
    const tree = elements(await PerformancePage({ searchParams: sp({ manager: M1 }) }));
    expect(tree.find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
    expect(allText(tree)).toContain("Meera's team");
    expect(filtersOf(tree).managers).toEqual([{ id: M1, full_name: "Meera", email: "m@x.local" }]);
  });

  it("shows the API's reason inline when the period is refused, with Try again and Show this month", async () => {
    answer({ "/api/v1/auth/me": MANAGER, "/api/v1/bdm/manager/performance?from=2026-10-31&to=2026-10-01": new ApiError("The period must start on or before its end", 422) });
    const tree = elements(await PerformancePage({ searchParams: sp({ from: "2026-10-31", to: "2026-10-01" }) }));
    expect(failure(tree)).toEqual({ message: "The period must start on or before its end",
      retryHref: "/bdm/manager/performance?from=2026-10-31&to=2026-10-01", reset: { href: "/bdm/manager/performance", label: "Show this month" } });
    expect(filtersOf(tree).period).toBeNull();
  });

  it("a server failure is the generic message; a refused role gets the access card", async () => {
    answer({ "/api/v1/auth/me": MANAGER, "/api/v1/bdm/manager/performance": new ApiError("boom", 500) });
    expect(failure(elements(await PerformancePage({ searchParams: sp({}) })))!.message).toBe("Unable to load the performance figures.");
    answer({ "/api/v1/auth/me": { full_name: "Asha", role: "bdm" }, "/api/v1/bdm/manager/performance": new ApiError("BDM manager role required", 403) });
    const card = (await PerformancePage({ searchParams: sp({}) })) as { props: { message: string } };
    expect(card.props.message).toBe("BDM manager role required"); // the access card, not an inline error
  });

  it("super_admin with a team that can't be read is offered all teams (QA24-03)", async () => {
    answer({ "/api/v1/auth/me": ROOT, [`/api/v1/bdm/manager/performance?manager_user_id=${M1}`]: new ApiError("Manager not found", 404) });
    expect(failure(elements(await PerformancePage({ searchParams: sp({ manager: M1 }) })))).toEqual({
      message: "Manager not found", retryHref: `/bdm/manager/performance?manager=${M1}`, reset: { href: "/bdm/manager/performance", label: "Show all teams" } });
    answer({ "/api/v1/auth/me": ROOT, [`/api/v1/bdm/manager/hierarchy?manager_user_id=${M1}`]: new ApiError("Manager not found", 404) });
    expect(failure(elements(await HierarchyPage({ searchParams: sp({ manager: M1 }) })))!.reset).toEqual({ href: "/bdm/manager/hierarchy", label: "Show all teams" });
  });

  it("the type page asks for that type's BDMs and refuses an unknown type", async () => {
    answer({
      "/api/v1/auth/me": MANAGER,
      "/api/v1/bdm/manager/performance?type=agent": performance({ type: "agent", bdms: [{ id: B1, full_name: "Asha", active: false, figures }] }),
    });
    const tree = elements(await TypePage({ params: sp({ type: "agent" }), searchParams: sp({}) }));
    const table = tree.find((el) => el.type === BdmPerformanceFigures)!;
    expect(table.props.rows).toEqual([{ key: B1, name: "Asha", href: `/bdm/manager/performance/bdms/${B1}`, note: "Inactive", figures }]);
    expect(allText(tree)).toContain("Agent BDMs");
    await expect(TypePage({ params: sp({ type: "telecaller" }), searchParams: sp({}) })).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
  });

  it("the BDM page lists organizations linking to their pages, and trips linking to theirs", async () => {
    answer({
      "/api/v1/auth/me": MANAGER,
      [`/api/v1/bdm/manager/performance/bdms/${B1}?from=2026-10-01`]: {
        from: "2026-10-01", to: "2026-10-31", bdm: { id: B1, full_name: "Asha", active: true, bdm_type: "college" }, totals: figures,
        organizations: [{ id: "o1", code: "ORG-1", name: "ABC College", figures: { ...figures, trips: null } }],
        trips: [{ id: "t1", code: "TRV-1", from_place: "Hyderabad", to_place: "Vijayawada", travel_date: "2026-10-05", approval_status: "approved", travel_status: "planned" }],
      },
    });
    const tree = elements(await BdmPage({ params: sp({ id: B1 }), searchParams: sp({ from: "2026-10-01" }) }));
    const rows = tree.find((el) => el.type === BdmPerformanceFigures)!.props.rows as { href: string }[];
    expect(rows[0].href).toBe("/bdm/manager/organizations/o1");
    expect(tree.some((el) => el.props.href === "/bdm/manager/trips/t1")).toBe(true);
    expect(allText(tree)).toContain("Travel trips: 1");
    expect(tree.some((el) => el.props.href === "/bdm/manager/performance/college?from=2026-10-01")).toBe(true); // breadcrumb keeps the period
    await expect(BdmPage({ params: sp({ id: "not-an-id" }), searchParams: sp({}) })).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("the BDM page says when the BDM is not in the team", async () => {
    answer({ "/api/v1/auth/me": MANAGER, [`/api/v1/bdm/manager/performance/bdms/${B1}`]: new ApiError("BDM not found", 404) });
    expect(failure(elements(await BdmPage({ params: sp({ id: B1 }), searchParams: sp({}) })))!.message).toBe("BDM not found");
  });

  it("the master view renders the hierarchy; super_admin gets the team picker but no period", async () => {
    answer({ "/api/v1/auth/me": ROOT, "/api/v1/bdm/manager/hierarchy": { manager: null, as_of: "2026-10-07T05:00:00Z", types: [] } });
    const tree = elements(await HierarchyPage({ searchParams: sp({}) }));
    expect(tree.find((el) => el.type === BdmHierarchy)).toBeTruthy();
    expect(allText(tree)).toContain("All BDM teams");
    expect(filtersOf(tree)).toMatchObject({ period: null, managers: [{ id: M1 }] });
  });
});
