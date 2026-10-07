import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmManagerDashboard from "@/components/BdmManagerDashboard";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import ManagerDashboard from "@/app/bdm/manager/dashboard/page";
import { elements, text } from "@/tests/helpers/elementTree";

// bdm-023 (DEC-SCOPE-104): the management dashboard page -- the manager's team, super_admin's all-teams view with a manager filter (R2),
// the inline error when the dashboard can't be read after the gate.
vi.mock("next/navigation", () => ({ redirect: vi.fn(), useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const M1 = "11111111-1111-4111-8111-111111111111";
const dashboard = (manager: { id: string; full_name: string } | null = null) => ({
  today: "2026-10-07", month: "2026-10-01", manager, tiles: [{ key: "T-M01", label: "Total BDMs", definition: "Active BDMs.", value: 2 }], alerts: [],
});
const team = { items: [{ id: "b1", active: true }, { id: "b2", active: false }], total: 2, limit: 50, offset: 0 };

function answer(map: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path in map) {
      const value = map[path];
      if (value instanceof Error) throw value;
      return value as never;
    }
    if (path === "/api/v1/workflows/notifications/unread-count") return { unread: 0 } as never;
    throw new ApiError("Not found", 404);
  });
}
const render = async (sp: { manager?: string } = {}) => elements(await ManagerDashboard({ searchParams: Promise.resolve(sp) }));
const allText = (tree: ReturnType<typeof elements>) => tree.map((el) => text(el)).join(" ");

describe("bdm-023 management dashboard page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });

  it("a manager sees the team summary and the dashboard of their team", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Meera", role: "bdm_manager" }, "/api/v1/bdm/manager/team?limit=50": team, "/api/v1/bdm/manager/dashboard": dashboard() });
    const tree = await render({ manager: M1 }); // a manager's filter is ignored, never sent (R2)
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/manager/dashboard");
    expect(allText(tree)).toContain("2 BDMs report to you: 1 active, 1 inactive.");
    expect(tree.find((el) => el.type === BdmManagerDashboard)!.props.superAdmin).toBe(false);
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("BDM Manager");
    expect(tree.some((el) => el.type === "select")).toBe(false);
  });

  it("super_admin sees all teams with a manager picker and the admin navigation", async () => {
    answer({
      "/api/v1/auth/me": { full_name: "Root", role: "super_admin" }, "/api/v1/bdm/manager/dashboard": dashboard(),
      "/api/v1/admin/bdm-managers?limit=100": { items: [{ id: M1, full_name: "Meera", email: "m@x.local" }], total: 1, limit: 100, offset: 0 },
    });
    const tree = await render();
    expect(allText(tree)).toContain("All BDM teams");
    expect(allText(tree)).toContain("Meera (m@x.local)");
    expect(tree.find((el) => el.type === "select")!.props.name).toBe("manager");
    const shell = tree.find((el) => el.type === PortalShell)!;
    expect(shell.props.nav).toBe(SUPER_ADMIN_NAV);
    expect(shell.props.roleLabel).toBe("Super Administrator");
    expect(serverApi).not.toHaveBeenCalledWith("/api/v1/bdm/manager/team?limit=50");
  });

  it("super_admin's chosen manager is sent to the API and named in the heading; a junk id is dropped", async () => {
    answer({
      "/api/v1/auth/me": { full_name: "Root", role: "super_admin" }, "/api/v1/admin/bdm-managers?limit=100": { items: [], total: 0, limit: 100, offset: 0 },
      [`/api/v1/bdm/manager/dashboard?manager_user_id=${M1}`]: dashboard({ id: M1, full_name: "Meera" }), "/api/v1/bdm/manager/dashboard": dashboard(),
    });
    expect(allText(await render({ manager: M1 }))).toContain("Meera's team");
    expect(allText(await render({ manager: "not-an-id" }))).toContain("All BDM teams");
  });

  it("shows the failure inline with Try again when the dashboard can't be read", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Meera", role: "bdm_manager" }, "/api/v1/bdm/manager/team?limit=50": team, "/api/v1/bdm/manager/dashboard": new ApiError("boom", 500) });
    const tree = await render();
    expect(allText(tree)).toContain("Unable to load the dashboard.");
    expect(tree.find((el) => el.props.role === "alert")).toBeTruthy();
    expect(tree.some((el) => el.props.href === "/bdm/manager/dashboard")).toBe(true);
  });

  it("a super_admin whose chosen manager can't be read gets a way back to all teams (QA23-02)", async () => {
    answer({
      "/api/v1/auth/me": { full_name: "Root", role: "super_admin" }, "/api/v1/admin/bdm-managers?limit=100": { items: [], total: 0, limit: 100, offset: 0 },
      [`/api/v1/bdm/manager/dashboard?manager_user_id=${M1}`]: new ApiError("Manager not found", 404),
    });
    const tree = await render({ manager: M1 });
    expect(allText(tree)).toContain("Unable to load the dashboard.");
    const back = tree.find((el) => text(el) === "Show all teams");
    expect(back!.props.href).toBe("/bdm/manager/dashboard");
  });

  it("another role keeps the Access unavailable card", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Asha", role: "bdm" }, "/api/v1/bdm/manager/team?limit=50": new ApiError("BDM manager role required", 403) });
    const card = (await render()).find((el) => typeof el.props.message === "string");
    expect(card!.props.message).toBe("BDM manager role required");
  });
});
