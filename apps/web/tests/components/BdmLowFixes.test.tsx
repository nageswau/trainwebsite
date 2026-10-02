import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminBdmPage from "@/components/AdminBdmPage";
import BdmTeamTable from "@/components/BdmTeamTable";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import SuperAdmin from "@/app/admin/page";
import BdmIndex from "@/app/bdm/page";
import BdmManagerIndex from "@/app/bdm/manager/page";
import ManagerDashboard from "@/app/bdm/manager/dashboard/page";
import ManagerTeam from "@/app/bdm/manager/team/page";
import { elements, text } from "@/tests/helpers/elementTree";

// bdm-001 browser QA, the Low issues (QA-09, QA-10, QA-12, QA-14, QA-16).
const { redirect } = vi.hoisted(() => ({ redirect: vi.fn((to: string) => { throw new Error(`NEXT_REDIRECT ${to}`); }) }));
vi.mock("next/navigation", () => ({ redirect, useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const manager = { id: "m1", full_name: "Meera", role: "bdm_manager", division: "global", email: "m@x", profile: {} };
const row = (id: string) => ({ id, full_name: `BDM ${id}`, email: "", phone: null, active: true, bdm_type: "agent", employee_id: `E-${id}`, designation: null, department: null, territory: null });
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });
const allText = (tree: ReturnType<typeof elements>) => tree.map((el) => text(el)).join(" ");

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
  redirect.mockClear();
});
afterEach(cleanup);

describe("QA-09: /bdm and /bdm/manager land somewhere real", () => {
  it("/bdm redirects to My Day", () => {
    expect(() => BdmIndex()).toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenCalledWith("/bdm/my-day");
  });
  it("/bdm/manager redirects to the manager dashboard", () => {
    expect(() => BdmManagerIndex()).toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenCalledWith("/bdm/manager/dashboard");
  });
});

describe("QA-10: /admin for a signed-in non-Super-Admin", () => {
  it("shows the shared access card with the user's own dashboard and the admin sign-in, not /it/login", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return manager as never;
      throw new ApiError("Admin role required", 403);
    });
    const tree = elements(await SuperAdmin());
    const card = tree.find((el) => typeof el.props.message === "string")!;
    expect(card.props.home).toBe("/bdm/manager/dashboard");
    expect(card.props.loginHref).toBe("/admin/login");
    expect(JSON.stringify(tree.map((el) => el.props.href))).not.toContain("/it/login");
  });
});

describe("QA-12: a Super Admin on a division's BDM page is labelled as Super Admin", () => {
  it("uses the Super Admin label and nav on /it/admin/bdms", async () => {
    vi.mocked(serverApi).mockResolvedValue({ id: "s", role: "super_admin", full_name: "Sam", division: "global", email: "s@x", profile: {} } as never);
    const tree = elements(await AdminBdmPage({ roles: ["it_admin", "super_admin"], nav: PORTAL_NAV["it/admin"], roleLabel: "IT Administrator" }));
    const shell = tree.find((el) => el.type === PortalShell)!;
    expect(shell.props.roleLabel).toBe("Super Administrator");
    expect(shell.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("keeps the division label for the division admin", async () => {
    vi.mocked(serverApi).mockResolvedValue({ id: "i", role: "it_admin", full_name: "Ira", division: "it", email: "i@x", profile: {} } as never);
    const tree = elements(await AdminBdmPage({ roles: ["it_admin", "super_admin"], nav: PORTAL_NAV["it/admin"], roleLabel: "IT Administrator" }));
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("IT Administrator");
  });
});

describe("QA-14: the team page past its last row", () => {
  it("says so and links back to the first page instead of an empty table", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? manager : page([], 1, 100)) as never);
    const tree = elements(await ManagerTeam({ searchParams: Promise.resolve({ offset: "100" }) }));
    expect(tree.some((el) => el.type === BdmTeamTable)).toBe(false);
    expect(allText(tree)).toContain("This page is past the end of your team.");
    expect(tree.map((el) => el.props.href)).toContain("/bdm/manager/team");
  });
});

describe("QA-16: copy", () => {
  it("says 'reports' for one BDM", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? manager : page([row("a")])) as never);
    expect(allText(elements(await ManagerDashboard()))).toContain("1 BDM reports to you: 1 active, 0 inactive.");
  });

  it("keeps the table caption for screen readers only, so the heading is not shown twice", () => {
    render(<BdmTeamTable page={{ items: [{ ...row("a"), bdm_type: "agent" as const }], total: 1, limit: 50, offset: 0 }} />);
    expect(screen.getByText("BDMs who report to you", { selector: "caption" })).toHaveClass("sr-only");
  });
});
