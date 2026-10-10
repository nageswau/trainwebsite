import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PartnershipDashboardPage from "@/app/partnership/dashboard/page";
import PartnershipDashboardTiles from "@/components/PartnershipDashboardTiles";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { PARTNERSHIP_HEAD_NAV, type NavItem } from "@/lib/navigation";
import { followupTiles, monthTiles, overviewTiles, type PartnershipDashboard } from "@/lib/partnershipDashboard";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/partnership/dashboard" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const manager = { id: "m1", full_name: "Rahul", role: "partnership_manager" };
const head = { id: "h1", full_name: "Hema", role: "partnership_head" };
const me = { ...manager, email: "r@x.in", phone: null, active: true, division: "overseas", partnership_profile: { employee_id: "E1", reporting_head: { id: "h1", full_name: "Hema" } } };
const DATA: PartnershipDashboard = {
  today: "2026-10-10", month: { first: "2026-10-01", last: "2026-10-31" },
  overview: { total: 1250, partners: 85, in_progress: 65, targets: 1050, at_risk: 12, lost: 50 },
  this_month: { contacted: 40, meetings: 18, visits: 4, proposals: 10, mous_negotiating: 6, mous_signed: 3, activated: 2, expected_count: 10, expected_weighted: 8 },
  followups: { overdue: 5, today: 3, tomorrow: 2, upcoming: 9 },
};
const message = (node: unknown) => (node as { props: { message?: string } }).props.message;
const shellOf = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === PortalShell)!;
const shell = (tree: ReturnType<typeof elements>) => render(<>{shellOf(tree).props.children}</>);

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

describe("upc-022 tiles", () => {
  it("names D1-D14 and the §20 bands, each linked to its list", () => {
    expect(followupTiles(DATA).map((t) => [t.label, t.value, t.href])).toEqual([
      ["Overdue", 5, "/partnership/tasks?band=overdue"], ["Due Today", 3, "/partnership/tasks?band=today"],
      ["Due Tomorrow", 2, "/partnership/tasks?band=tomorrow"], ["Upcoming", 9, "/partnership/tasks?band=upcoming"],
    ]);
    expect(overviewTiles(DATA, "partnership_manager").map((t) => t.value)).toEqual([1250, 85, 65, 1050, 12]);
    expect(monthTiles(DATA).map((t) => t.label)).toEqual([
      "New universities contacted", "Meetings", "University visits", "Proposals sent", "MoUs under negotiation", "MoUs signed",
      "New partnerships activated", "Expected partnerships", "Overdue follow-ups",
    ]);
    const expected = monthTiles(DATA).find((t) => t.key === "expected")!;
    expect([expected.value, expected.note, expected.href]).toEqual([10, "Weighted forecast: 8", "/partnership/expected?window=this_month"]);
    expect(monthTiles(DATA).at(-1)!.value).toBe(5); // D14 = the overdue band
  });

  it("opens a manager's own universities, and the whole list for a head", () => {
    const [total, , , , atRisk] = overviewTiles(DATA, "partnership_manager");
    expect(total.href).toBe("/partnership/universities?manager=me");
    expect(atRisk.href).toBe("/partnership/universities?relationship_strength=at_risk&manager=me");
    expect(total.note).toBe("Includes 50 lost / closed");
    const [headTotal, , , , headRisk] = overviewTiles(DATA, "partnership_head");
    expect(headTotal.href).toBe("/partnership/universities");
    expect(headRisk.href).toBe("/partnership/universities?relationship_strength=at_risk");
    expect(overviewTiles({ ...DATA, overview: { ...DATA.overview, lost: 0 } }, "partnership_head")[0].note).toBeUndefined();
  });

  it("renders a labelled group of figures with accessible links", () => {
    render(<PartnershipDashboardTiles id="f" title="Follow-ups" tiles={followupTiles(DATA)} />);
    const group = screen.getByRole("region", { name: "Follow-ups" });
    expect(within(group).getByText("5")).toBeTruthy();
    expect(within(group).getByRole("link", { name: "View overdue" }).getAttribute("href")).toBe("/partnership/tasks?band=overdue");
  });
});

describe("upc-022 dashboard page", () => {
  it("shows a manager the three groups, their profile and the coming-soon card", async () => {
    answer({ "/api/v1/auth/me": manager, "/api/v1/partnership/me": me, "/api/v1/partnership/dashboard": DATA });
    shell(elements(await PartnershipDashboardPage()));
    expect(screen.getByRole("heading", { name: "Welcome, Rahul" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Follow-ups" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Global Partnership Overview" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "This Month — October 2026" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Coming soon to your CRM" })).toBeTruthy();
    expect(screen.getByText("E1")).toBeTruthy();
  });

  it("gives a head their shell and no profile card", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/dashboard": DATA });
    const tree = elements(await PartnershipDashboardPage());
    expect((shellOf(tree).props.nav as NavItem[]).map((n) => n.href)).toEqual(PARTNERSHIP_HEAD_NAV.map((n) => n.href));
    shell(tree);
    expect(screen.getByText(/Your team's universities/)).toBeTruthy();
    expect(screen.queryByText("Coming soon to your CRM")).toBeNull();
    expect(vi.mocked(serverApi).mock.calls.map(([p]) => p)).not.toContain("/api/v1/partnership/me");
  });

  it("still renders when only the figures fail", async () => {
    answer({ "/api/v1/auth/me": manager, "/api/v1/partnership/me": me, "/api/v1/partnership/dashboard": new ApiError("boom", 500) });
    shell(elements(await PartnershipDashboardPage()));
    expect(screen.getByRole("status").textContent).toContain("The dashboard figures are unavailable right now");
    expect(screen.getByText("E1")).toBeTruthy();
  });

  it("refuses another role before reading the figures", async () => {
    answer({ "/api/v1/auth/me": { id: "c1", full_name: "Chitra", role: "counselor" } });
    expect(message(await PartnershipDashboardPage())).toBe("The partnership dashboard is for partnership managers and heads");
    expect(serverApi).toHaveBeenCalledTimes(1);
  });

  it("shows the API's 403 for a manager without a profile", async () => {
    answer({ "/api/v1/auth/me": manager, "/api/v1/partnership/me": new ApiError("Partnership profile not set up — contact your administrator", 403) });
    expect(message(await PartnershipDashboardPage())).toBe("Partnership profile not set up — contact your administrator");
  });
});
