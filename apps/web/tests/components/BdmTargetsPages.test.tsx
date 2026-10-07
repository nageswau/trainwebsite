import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BdmTargetsCard from "@/components/BdmTargetsCard";
import BdmTargetsCopy from "@/components/BdmTargetsCopy";
import BdmTargetsEditor from "@/components/BdmTargetsEditor";
import PortalShell from "@/components/PortalShell";
import PortalLoading from "@/components/PortalLoading";
import MemberLoading from "@/app/bdm/manager/targets/[bdmId]/loading";
import MemberTargets from "@/app/bdm/manager/targets/[bdmId]/page";
import TeamLoading from "@/app/bdm/manager/targets/loading";
import { BDM_MANAGER_NAV } from "@/lib/navigation";
import TeamTargetsPage from "@/app/bdm/manager/targets/page";
import MyDay from "@/app/bdm/my-day/page";
import { ApiError, serverApi } from "@/lib/api";
import { currentMonth, type TargetSheet, type TeamTargets } from "@/lib/bdmTargets";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/bdm/manager/targets" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const B1 = "00000000-0000-4000-8000-0000000000b1";
const manager = { id: "m1", full_name: "Meera", role: "bdm_manager" };
const sheet: TargetSheet = { month: "2026-09", month_status: "past", editable: false, bdm: { id: B1, full_name: "Asha" }, bdm_type: "school", kpis: [] };
const team = (over: Partial<TeamTargets> = {}): TeamTargets => ({
  month: "2026-09", month_status: "past", editable: false, total: 1, limit: 50, offset: 0,
  items: [{ bdm: { id: B1, full_name: "Asha" }, bdm_type: "school", targets_set: 3, kpi_count: 15 }], ...over,
});
const text = (tree: ReturnType<typeof elements>) => tree.map((el) => (typeof el.props.children === "string" ? el.props.children : "")).join(" ");
const hrefs = (tree: ReturnType<typeof elements>) => tree.map((el) => el.props.href).filter(Boolean);

function answer(routes: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path.includes("unread")) return { unread: 0 } as never;
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
afterEach(cleanup);

describe("bdm-016 targets pages", () => {
  it("the team page reads the chosen month and links each BDM's targets; a past month is read-only, without copy", async () => {
    answer({ "/api/v1/auth/me": manager, "/api/v1/bdm/manager/targets": team() });
    const tree = elements(await TeamTargetsPage({ searchParams: Promise.resolve({ month: "2026-09" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/manager/targets?month=2026-09&limit=50&offset=0");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("BDM Manager");
    expect(hrefs(tree)).toContain(`/bdm/manager/targets/${B1}?month=2026-09`);
    expect(tree.some((el) => el.type === BdmTargetsCopy)).toBe(false);
    expect(text(tree)).toContain("Past months are read-only.");
  });

  it("an editable month offers Copy; a malformed month falls back to this month; an empty team says so", async () => {
    answer({ "/api/v1/auth/me": manager, "/api/v1/bdm/manager/targets": team({ month: currentMonth(), month_status: "current", editable: true, items: [], total: 0 }) });
    const tree = elements(await TeamTargetsPage({ searchParams: Promise.resolve({ month: "2026-13" }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/manager/targets?month=${currentMonth()}&limit=50&offset=0`);
    expect(tree.find((el) => el.type === BdmTargetsCopy)!.props.month).toBe(currentMonth());
    expect(text(tree)).toContain("No active BDMs report to you yet.");
    expect(text(tree)).toContain("That isn't a valid month — showing this month.");
  });

  it("a BDM opening the team page is refused", async () => {
    answer({ "/api/v1/auth/me": { id: B1, full_name: "Asha", role: "bdm" } });
    const tree = elements(await TeamTargetsPage({ searchParams: Promise.resolve({}) }));
    expect(tree.some((el) => typeof el.props.message === "string")).toBe(true);
  });

  it("the member page gives the editor the BDM's sheet; outside the team shows the API's reason", async () => {
    answer({ "/api/v1/auth/me": manager, [`/api/v1/bdm/manager/targets/${B1}`]: sheet });
    const tree = elements(await MemberTargets({ params: Promise.resolve({ bdmId: B1 }), searchParams: Promise.resolve({ month: "2026-09" }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/manager/targets/${B1}?month=2026-09`);
    expect(tree.find((el) => el.type === BdmTargetsEditor)!.props.initial).toEqual(sheet);
    answer({ "/api/v1/auth/me": manager, [`/api/v1/bdm/manager/targets/${B1}`]: new ApiError("BDM not found", 404) });
    const missing = elements(await MemberTargets({ params: Promise.resolve({ bdmId: B1 }), searchParams: Promise.resolve({}) }));
    expect(missing.find((el) => typeof el.props.message === "string")!.props.message).toBe("BDM not found");
  });

  it("QA16-02: both targets pages show the manager portal's loading state while they load", () => {
    for (const Loading of [TeamLoading, MemberLoading]) {
      const loading = Loading();
      expect(loading.type).toBe(PortalLoading);
      expect(loading.props.nav).toBe(BDM_MANAGER_NAV);
      expect(loading.props.label).toMatch(/targets/);
    }
  });

  it("QA16-01: a member id that isn't a UUID is 'BDM not found' without calling the API", async () => {
    answer({ "/api/v1/auth/me": manager });
    const tree = elements(await MemberTargets({ params: Promise.resolve({ bdmId: "not-a-uuid" }), searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => typeof el.props.message === "string")!.props.message).toBe("BDM not found");
    expect(serverApi).toHaveBeenCalledTimes(2); // auth/me and the nav badge only
  });

  it("My Day shows the month's targets card, and still renders when targets can't be read", async () => {
    const me = { id: B1, full_name: "Asha", bdm_profile: { bdm_type: "school", employee_id: "E-1", territory: null } };
    const myDay = { today: "2026-10-07", bdm_type: "school", appointments: { count: 0, truncated: false, items: [] }, trips: { total: 0, items: [] }, follow_ups: { total: 0, groups: [] }, tiles: [] };
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/my-day": myDay, "/api/v1/bdm/targets": sheet, "/api/v1/bdm/meeting-requests": { items: [], total: 0 } });
    let tree = elements(await MyDay());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/targets");
    expect(tree.find((el) => el.type === BdmTargetsCard)!.props.sheet).toEqual(sheet);
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/my-day": myDay, "/api/v1/bdm/targets": new ApiError("boom", 500) });
    tree = elements(await MyDay());
    expect(tree.find((el) => el.type === BdmTargetsCard)!.props.sheet).toBeNull();
  });
});
