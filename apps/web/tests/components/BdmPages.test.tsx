import { beforeEach, describe, expect, it, vi } from "vitest";

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
  vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? { full_name: "Meera" } : queue ? queue.shift() : team) as never);
}

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("bdm-001 BDM pages", () => {
  it("My Day shows the profile summary and the neutral note (AC05)", async () => {
    vi.mocked(serverApi).mockResolvedValue(me);
    const tree = elements(await MyDay());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/me");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    expect(tree.find((el) => el.type === BdmProfileCard)!.props.me).toEqual(me);
    expect(tree.some((el) => el.type === "p" && text(el).includes("appointments, travel and follow-ups will appear here"))).toBe(true);
  });

  it("My Day shows the API's no-profile message with a link to the chooser", async () => {
    vi.mocked(serverApi).mockRejectedValueOnce(new ApiError("BDM profile not set up — contact your administrator", 403)).mockRejectedValueOnce(new ApiError("x", 401));
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
