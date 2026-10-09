import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagerTargetsPage from "@/app/partnership/targets/[managerId]/page";
import TargetsPage from "@/app/partnership/targets/page";
import PartnershipTargetsTable from "@/components/PartnershipTargetsTable";
import PortalShell from "@/components/PortalShell";
import TargetsEditor from "@/components/TargetsEditor";
import { ApiError, serverApi } from "@/lib/api";
import { currentMonth } from "@/lib/bdmTargets";
import { PARTNERSHIP_HEAD_NAV, PARTNERSHIP_MENU, PARTNERSHIP_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { ManagerTargetSheet, TeamTargets } from "@/lib/partnershipTargets";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/partnership/targets" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const M1 = "00000000-0000-4000-8000-0000000000a1";
const head = { id: "h1", full_name: "Hema", role: "partnership_head" };
const pm = { id: M1, full_name: "Rahul", role: "partnership_manager" };
const KPIS = [
  { key: "proposals", label: "Proposals", definition: "Universities moved into Proposal Sent this month", tracked: true },
  { key: "meetings", label: "Meetings", definition: "Counted once Meetings is available", tracked: false },
];
const team = (over: Partial<TeamTargets> = {}): TeamTargets => ({
  month: "2026-09", month_status: "current", editable: true, kpis: KPIS,
  managers: [{ manager: { id: M1, full_name: "Rahul" }, active: true, kpis: [{ key: "proposals", target: 4, achieved: 1, percent: 25 }, { key: "meetings", target: 2, achieved: null, percent: null }] }],
  team: [{ key: "proposals", target: 4, achieved: 1, percent: 25 }, { key: "meetings", target: 2, achieved: null, percent: null }],
  ...over,
});
const sheet = (over: Partial<ManagerTargetSheet> = {}): ManagerTargetSheet => ({
  month: "2026-09", month_status: "current", editable: true, manager: { id: M1, full_name: "Rahul" },
  kpis: [{ ...KPIS[0], target: 4, achieved: 1, percent: 25 }, { ...KPIS[1], target: null, achieved: null, percent: null }],
  ...over,
});
const text = (tree: ReturnType<typeof elements>) => tree.map((el) => (typeof el.props.children === "string" ? el.props.children : "")).join(" ");
const hrefs = (tree: ReturnType<typeof elements>) => tree.map((el) => el.props.href).filter(Boolean);
const message = (node: unknown) => (node as { props: { message?: string } }).props.message;
const tableOf = (tree: ReturnType<typeof elements>) => render(tree.find((el) => el.type === PartnershipTargetsTable)!);
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

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
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("upc-021 targets pages", () => {
  it("a head compares each manager and the team, actual / target, and opens a manager to set targets", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/targets": team() });
    const tree = elements(await TargetsPage({ searchParams: Promise.resolve({ month: "2026-09" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/targets?month=2026-09");
    expect(tree.find((el) => el.type === PortalShell)!.props.nav).toBe(PARTNERSHIP_HEAD_NAV);
    tableOf(tree);
    const row = (name: string) => screen.getByRole("rowheader", { name }).closest("tr")!;
    expect(row("Rahul").textContent).toContain("1 / 4 · 25%");
    expect(row("Rahul").textContent).toContain("Not tracked / 2");
    expect(row("Team").textContent).toContain("1 / 4 · 25%");
    expect(screen.getByRole("link", { name: "Set targets for Rahul" })).toHaveAttribute("href", `/partnership/targets/${M1}?month=2026-09`);
  });

  it("an empty team says so; a malformed month falls back to this month with a note", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/targets": team({ managers: [], month: currentMonth() }) });
    const tree = elements(await TargetsPage({ searchParams: Promise.resolve({ month: "2026-13" }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/targets?month=${currentMonth()}`);
    tableOf(tree);
    expect(screen.getByText("No partnership managers report to you yet.")).toBeTruthy();
    expect(text(tree)).toContain("That isn't a valid month — showing this month.");
  });

  it("a manager sees only their own month, read-only", async () => {
    answer({ "/api/v1/auth/me": pm, [`/api/v1/partnership/targets/${M1}`]: sheet({ editable: false }) });
    const tree = elements(await TargetsPage({ searchParams: Promise.resolve({ month: "2026-09" }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/targets/${M1}?month=2026-09`);
    expect(tree.find((el) => el.type === PortalShell)!.props.nav).toBe(PARTNERSHIP_NAV);
    const editor = tree.find((el) => el.type === TargetsEditor)!;
    expect((editor.props.initial as ManagerTargetSheet).editable).toBe(false);
  });

  it("another role is refused before the API is asked for targets", async () => {
    answer({ "/api/v1/auth/me": { id: "c1", full_name: "Cara", role: "counselor" } });
    expect(message(await TargetsPage({ searchParams: Promise.resolve({}) }))).toBe("Partnership targets access required");
    expect(serverApi).toHaveBeenCalledTimes(1);
  });

  it("one manager's page edits their month against the partnership targets API", async () => {
    answer({ "/api/v1/auth/me": head, [`/api/v1/partnership/targets/${M1}`]: sheet() });
    const tree = elements(await ManagerTargetsPage({ params: Promise.resolve({ managerId: M1 }), searchParams: Promise.resolve({ month: "2026-09" }) }));
    const editor = tree.find((el) => el.type === TargetsEditor)!;
    expect(editor.props).toMatchObject({ ownerId: M1, ownerField: "manager_user_id", saveUrl: "/api/v1/partnership/targets" });
    expect(hrefs(tree)).toContain("/partnership/targets?month=2026-09");
  });

  it("a malformed manager id is a not-found message, not an API error", async () => {
    answer({ "/api/v1/auth/me": head });
    expect(message(await ManagerTargetsPage({ params: Promise.resolve({ managerId: "nope" }), searchParams: Promise.resolve({}) }))).toBe("Partnership manager not found");
  });

  it("the menu opens Targets & Forecast for managers, heads and super_admin", () => {
    expect(PARTNERSHIP_MENU.find((e) => e.item === "upc-021")!.live).toBe(true);
    expect(PARTNERSHIP_NAV.some((n) => n.href === "/partnership/targets")).toBe(true);
    expect(PARTNERSHIP_HEAD_NAV.some((n) => n.href === "/partnership/targets")).toBe(true);
    expect(SUPER_ADMIN_NAV.some((n) => n.href === "/partnership/targets")).toBe(true);
  });
});

describe("upc-021 targets editor", () => {
  it("saves a manager's changed targets to the partnership API, then re-reads their sheet", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) =>
      url === "/api/v1/partnership/targets" ? res({ month: "2026-09", changed: 1 }) : res(sheet({ kpis: [{ ...sheet().kpis[0], target: 6, percent: 17 }, sheet().kpis[1]] })),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<TargetsEditor initial={sheet()} ownerId={M1} ownerField="manager_user_id" saveUrl="/api/v1/partnership/targets" sheetUrl={(id, month) => `/api/v1/partnership/targets/${id}?month=${month}`} />);
    fireEvent.change(screen.getByLabelText("Proposals target"), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Saved 1 target."));
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(put[1]!.body as string)).toEqual({ month: "2026-09", items: [{ manager_user_id: M1, kpi_key: "proposals", target: 6 }] });
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/partnership/targets/${M1}?month=2026-09`);
    expect((screen.getByLabelText("Proposals target") as HTMLInputElement).value).toBe("6");
  });
});
