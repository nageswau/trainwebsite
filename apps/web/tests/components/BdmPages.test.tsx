import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmMyDay from "@/components/BdmMyDay";
import BdmProfileCard from "@/components/BdmProfileCard";
import BdmTeamTable from "@/components/BdmTeamTable";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import ManagerDashboard from "@/app/bdm/manager/dashboard/page";
import ManagerTeam from "@/app/bdm/manager/team/page";
import MyDay from "@/app/bdm/my-day/page";
import Profile from "@/app/bdm/profile/page";
import SignIn from "@/app/bdm/sign-in/page";
import { elements, text } from "@/tests/helpers/elementTree";

// Keep the real ApiError (accessUnavailable tells a 401 from the rest by it); only serverApi is replaced.
const { redirect } = vi.hoisted(() => ({ redirect: vi.fn((to: string) => { throw new Error(`NEXT_REDIRECT ${to}`); }) }));
vi.mock("next/navigation", () => ({ redirect, useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const me = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it",
  bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: "Kochi", reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const row = (id: string, active = true) => ({ id, full_name: `BDM ${id}`, email: `${id}@x.local`, phone: null, active, bdm_type: "agent", employee_id: `E-${id}`, designation: null, department: null, territory: null });
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });
const hrefs = (tree: ReturnType<typeof elements>) => tree.map((el) => el.props.href).filter((h): h is string => typeof h === "string");
const allText = (tree: ReturnType<typeof elements>) => tree.map((el) => text(el)).join(" ");

function answerByPath(team: unknown | unknown[]) {
  const queue = Array.isArray(team) ? [...team] : null;
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/workflows/notifications/unread-count") return { unread: 0 } as never; // bdm-010 QA10-01 sidebar badge
    return (path === "/api/v1/auth/me" ? { full_name: "Meera" } : queue ? queue.shift() : team) as never;
  });
}

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
  redirect.mockClear();
});

describe("bdm-001 BDM pages", () => {
  // bdm-014 (DEC-SCOPE-097): My Day reads its data after the profile gate and keeps a one-line profile summary (K11).
  const myDay = { today: "2026-09-13", bdm_type: "college", appointments: { count: 0, truncated: false, items: [] }, trips: { total: 0, items: [] }, follow_ups: { total: 0, groups: [] }, tiles: [] };
  function answerMyDay(data: unknown) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/workflows/notifications/unread-count") return { unread: 0 } as never;
      if (path === "/api/v1/bdm/me") return me as never;
      if (path === "/api/v1/bdm/my-day") {
        if (data instanceof Error) throw data;
        return data as never;
      }
      throw new ApiError("unexpected", 500);
    });
  }

  it("My Day renders the day's data with the profile summary (bdm-014)", async () => {
    answerMyDay(myDay);
    const tree = elements(await MyDay());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/me");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    expect(tree.find((el) => el.type === BdmMyDay)!.props.data).toEqual(myDay);
    expect(tree.some((el) => el.type === BdmProfileCard)).toBe(false);
    expect(allText(tree)).toContain("Employee ID E-1 · Kochi");
    expect(hrefs(tree)).toContain("/bdm/profile");
  });

  it("My Day shows an inline error with Try again when the day can't be read", async () => {
    answerMyDay(new ApiError("boom", 500));
    const tree = elements(await MyDay());
    expect(tree.some((el) => el.type === BdmMyDay)).toBe(false);
    expect(allText(tree)).toContain("Unable to load your day.");
    expect(hrefs(tree)).toContain("/bdm/my-day");
  });

  it("a BDM manager opening My Day is sent to the manager dashboard", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return { id: "m1", full_name: "Meera", role: "bdm_manager", division: "global" } as never;
      if (path === "/api/v1/bdm/me") throw new ApiError("BDM role required", 403);
      return { unread: 0 } as never;
    });
    await expect(MyDay()).rejects.toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenCalledWith("/bdm/manager/dashboard");
  });

  it("another role refused by My Day keeps the Access unavailable card", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return { id: "s1", full_name: "Sam", role: "student", division: "it" } as never;
      if (path === "/api/v1/bdm/me") throw new ApiError("BDM role required", 403);
      return { unread: 0 } as never;
    });
    const tree = elements(await MyDay());
    expect(tree.find((el) => typeof el.props.message === "string")!.props.message).toBe("BDM role required");
    expect(redirect).not.toHaveBeenCalled();
  });

  it("My Day shows the API's no-profile message with a link to the chooser", async () => {
    // Answered by path: the page also reads the unread badge (bdm-010), so call order is not fixed.
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/bdm/me") throw new ApiError("BDM profile not set up — contact your administrator", 403);
      throw new ApiError("x", 401);
    });
    const tree = elements(await MyDay());
    const card = tree.find((el) => typeof el.props.message === "string");
    expect(card!.props.message).toBe("BDM profile not set up — contact your administrator");
    expect(card!.props.loginHref).toBe("/bdm/sign-in");
  });

  it("Profile renders the same card read-only", async () => {
    vi.mocked(serverApi).mockResolvedValue(me);
    const tree = elements(await Profile());
    expect(tree.some((el) => el.type === BdmProfileCard)).toBe(true);
    expect(allText(tree)).toContain("Contact them to change anything");
  });
});

describe("bdm-001 manager pages", () => {
  it("dashboard counts active and inactive and links to the team (AC05)", async () => {
    answerByPath(page([row("a"), row("b", false)]));
    const tree = elements(await ManagerDashboard());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/auth/me");
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/manager/team?limit=50");
    expect(tree.find((el) => el.type === PortalShell)!.props.userName).toBe("Meera");
    expect(allText(tree)).toContain("2 BDMs report to you: 1 active, 1 inactive.");
    expect(hrefs(tree)).toContain("/bdm/manager/team");
  });

  it("dashboard says so when nobody reports yet, with no team link", async () => {
    answerByPath(page([]));
    const tree = elements(await ManagerDashboard());
    expect(allText(tree)).toContain("No BDMs report to you yet.");
    expect(hrefs(tree)).not.toContain("/bdm/manager/team");
  });

  it("team page passes the offset and renders the table; empty state when none (AC06)", async () => {
    answerByPath([page([row("a")], 51, 50), page([])]);
    let tree = elements(await ManagerTeam({ searchParams: Promise.resolve({ offset: "50" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/manager/team?limit=50&offset=50");
    expect(tree.some((el) => el.type === BdmTeamTable)).toBe(true);
    tree = elements(await ManagerTeam({ searchParams: Promise.resolve({}) }));
    expect(allText(tree)).toContain("No BDMs report to you yet.");
  });

  it("team page clamps a junk offset to 0", async () => {
    answerByPath(page([]));
    await ManagerTeam({ searchParams: Promise.resolve({ offset: "-5abc" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/manager/team?limit=50&offset=0");
  });

  it("a refused manager page sends sign-in to the admin portal", async () => {
    vi.mocked(serverApi).mockRejectedValue(new ApiError("BDM manager role required", 403));
    const tree = elements(await ManagerTeam({ searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => typeof el.props.message === "string")!.props.loginHref).toBe("/admin/login");
  });
});

describe("bdm-001 sign-in chooser (AC12)", () => {
  it("carries a safe next to both portals", async () => {
    const tree = elements(await SignIn({ searchParams: Promise.resolve({ next: "/bdm/my-day" }) }));
    expect(hrefs(tree)).toEqual(expect.arrayContaining(["/it/login?next=%2Fbdm%2Fmy-day", "/overseas/login?next=%2Fbdm%2Fmy-day", "/admin/login?next=%2Fbdm%2Fmy-day"]));
  });

  it("drops an unsafe next", async () => {
    const tree = elements(await SignIn({ searchParams: Promise.resolve({ next: "//evil.example" }) }));
    expect(hrefs(tree)).toEqual(expect.arrayContaining(["/it/login", "/overseas/login", "/admin/login"]));
    expect(hrefs(tree).some((h) => h.includes("evil"))).toBe(false);
  });
});
