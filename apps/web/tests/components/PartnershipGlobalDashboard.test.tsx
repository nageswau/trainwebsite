import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import GlobalDashboardPage from "@/app/partnership/head/global-dashboard/page";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { PARTNERSHIP_HEAD_NAV, SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import { GLOBAL_URL, pipelineTiles, type GlobalDashboard } from "@/lib/partnershipGlobal";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/partnership/head/global-dashboard" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const head = { id: "h1", full_name: "Hema", role: "partnership_head" };
const admin = { id: "s1", full_name: "Sam", role: "super_admin" };
const STEPS = [
  { key: "leads", label: "Leads", tracked: false }, { key: "applications", label: "Applications", tracked: true }, { key: "enrolled", label: "Enrolled", tracked: true },
] as GlobalDashboard["funnel"]["steps"];
const DATA: GlobalDashboard = {
  today: "2026-10-10", from: "2026-10-01", to: "2026-10-10",
  active: {
    count: 3, countries: [{ name: "United Kingdom", iso2: "GB", count: 2 }, { name: "Atlantis", iso2: null, count: 1 }],
    universities: [{ id: "u1", university_code: "UNV-000001", name: "Oxford Brookes", country: "United Kingdom", courses: 12 }],
    courses: [{ level: "PG", courses: 9, universities: 2 }],
  },
  in_progress: {
    count: 4, expected: { earlier: 1, this_month: 1, next_month: 1, later: 0, undated: 1 }, probability: [{ probability: 75, count: 4 }], weighted: 3,
    next_actions: [{ university: { id: "u2", university_code: "UNV-000002", name: "Monash" }, task_id: "t1", title: "Send the MoU draft", due_on: "2026-10-08", overdue: true }],
    without_action: 3,
  },
  target: { count: 0, priorities: [{ priority: "A", count: 0 }, { priority: "B", count: 0 }, { priority: "C", count: 0 }, { priority: null, count: 0 }], countries: [], course_levels: [], no_course_levels: 0 },
  pipeline: {
    steps: [
      { key: "identified", label: "Identified", count: 0 }, { key: "contacted", label: "Contacted", count: 2 }, { key: "meeting", label: "Meeting", count: 1 },
      { key: "proposal", label: "Proposal", count: 1 }, { key: "negotiation", label: "Negotiation", count: 0 }, { key: "agreement", label: "Agreement", count: 0 },
      { key: "signed", label: "Signed", count: 1 }, { key: "active_partner", label: "Active Partner", count: 2 },
    ],
    lost: 1, total: 8,
  },
  funnel: { steps: STEPS, totals: { leads: null, counselling: null, interested: 0, eligible: null, applications: 20, offers: 5, deposits: 2, visas: 1, enrolled: 7 } },
  commission: { expected: [{ currency: "GBP", amount: "1500.00" }], received: [] },
};
const message = (node: unknown) => (node as { props: { message?: string } }).props.message;
const shellOf = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === PortalShell)!;
const shell = (tree: ReturnType<typeof elements>) => render(<>{shellOf(tree).props.children}</>);
const page = (search: Record<string, string> = {}) => GlobalDashboardPage({ searchParams: Promise.resolve(search) });

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

describe("upc-029 global dashboard", () => {
  it("names the Management §19 pipeline steps, each opening its Kanban column", () => {
    expect(pipelineTiles(DATA).map((t) => [t.label, t.value, t.href])).toEqual([
      ["Identified", 0, "/partnership/pipeline?column=target"], ["Contacted", 2, "/partnership/pipeline?column=contacted"],
      ["Meeting", 1, "/partnership/pipeline?column=meeting_scheduled"], ["Proposal", 1, "/partnership/pipeline?column=proposal_sent"],
      ["Negotiation", 0, "/partnership/pipeline?column=negotiation"], ["Agreement", 0, "/partnership/pipeline?column=agreement_pending"],
      ["Signed", 1, "/partnership/pipeline?column=signed"], ["Active Partner", 2, "/partnership/pipeline?column=active_partners"],
    ]);
  });

  it("shows a head the three columns, the pipeline, the funnel and the commission in their shell", async () => {
    answer({ "/api/v1/auth/me": head, [GLOBAL_URL]: DATA });
    const tree = elements(await page());
    expect((shellOf(tree).props.nav as NavItem[]).map((n) => n.href)).toEqual(PARTNERSHIP_HEAD_NAV.map((n) => n.href));
    shell(tree);
    expect(screen.getByRole("heading", { level: 2, name: /EduSphere Global Partnerships/ })).toBeTruthy();
    const active = screen.getByRole("region", { name: "Active Partners (3)" });
    expect(within(active).getByRole("link", { name: "United Kingdom" }).getAttribute("href")).toBe("/partnership/search?partner_status=partner&iso2=GB");
    expect(within(active).getByText("Atlantis").closest("a")).toBeNull(); // no ISO code, no link
    expect(within(active).getByRole("link", { name: "Oxford Brookes" }).getAttribute("href")).toBe("/partnership/universities/u1");
    expect(within(active).getByRole("link", { name: "PG" }).getAttribute("href")).toBe("/partnership/search?partner_status=partner&level=PG");
    const progress = screen.getByRole("region", { name: "In Progress (4)" });
    expect(within(progress).getByText("Weighted forecast: 3")).toBeTruthy();
    expect(within(progress).getByRole("link", { name: "Monash" })).toBeTruthy();
    expect(within(progress).getByText(/Overdue/)).toBeTruthy();
    expect(within(progress).getByText("3 without an open task")).toBeTruthy();
    const target = screen.getByRole("region", { name: "Target List (0)" });
    expect(within(target).getByText("No universities in this column.")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Partnership Pipeline" })).toBeTruthy();
    expect(screen.getByText("Includes 1 lost / closed in the total of 8.")).toBeTruthy();
    expect(screen.getByRole("list", { name: /Student recruitment/ })).toBeTruthy();
    const money = screen.getByRole("region", { name: "University Commission" });
    expect(within(money).getByText("GBP 1,500.00")).toBeTruthy();
  });

  it("passes the period on to the API and leaves out a commission the API did not send", async () => {
    const noMoney = { ...DATA, commission: undefined };
    answer({ "/api/v1/auth/me": admin, [GLOBAL_URL]: noMoney });
    const tree = elements(await page({ from: "2026-09-01", to: "2026-09-30" }));
    expect(vi.mocked(serverApi).mock.calls.map(([p]) => p)).toContain(`${GLOBAL_URL}?from=2026-09-01&to=2026-09-30`);
    shell(tree);
    expect(screen.queryByRole("region", { name: "University Commission" })).toBeNull();
  });

  it("still renders the shell when the figures fail", async () => {
    answer({ "/api/v1/auth/me": head, [GLOBAL_URL]: new ApiError("boom", 500) });
    shell(elements(await page()));
    expect(screen.getByRole("status").textContent).toContain("The global dashboard is unavailable right now");
  });

  it("refuses a partnership manager before reading the figures", async () => {
    answer({ "/api/v1/auth/me": { id: "m1", full_name: "Rahul", role: "partnership_manager" } });
    expect(message(await page())).toBe("The global partnership dashboard is for partnership heads and super admins");
    expect(serverApi).toHaveBeenCalledTimes(1);
  });

  it("is in the super admin's nav", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Global Dashboard", href: "/partnership/head/global-dashboard" });
  });
});
