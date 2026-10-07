import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BdmDailyReport from "@/components/BdmDailyReport";
import PortalShell from "@/components/PortalShell";
import ManagerReport from "@/app/bdm/manager/daily-reports/[bdmId]/page";
import ManagerReports from "@/app/bdm/manager/daily-reports/page";
import MyReport from "@/app/bdm/daily-report/page";
import { serverApi } from "@/lib/api";
import type { DailyReport, TeamGrid } from "@/lib/bdmDailyReports";
import { indiaToday } from "@/lib/bdmTravel";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/bdm/manager/daily-reports" }));
vi.mock("@/lib/api",async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const B1 = "00000000-0000-4000-8000-0000000000b1";
const me = {
  id: B1, full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it",
  bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const manager = { id: "m1", full_name: "Meera", role: "bdm_manager" };
const report: DailyReport = {
  report_date: "2026-10-05", bdm: { id: B1, full_name: "Asha" }, bdm_type: "college", status: "draft", submitted_at: null, note: null,
  counts: [], can_submit: true, submit_window_days: 7, manager_comment: null,
};
const dates = ["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"];
const grid: TeamGrid = {
  dates, total: 1, limit: 50, offset: 0,
  items: [{ bdm: { id: B1, full_name: "Asha" }, bdm_type: "school", days: dates.map((d, i) => ({
    report_date: d, status: i === 0 ? "not_started" : i === 6 ? "submitted" : "missing", submitted_at: i === 6 ? "2026-10-05T13:00:00Z" : null })) }],
};

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(cleanup);

describe("bdm-015 daily report pages", () => {
  it("My daily report reads the chosen IST day and replaces a malformed one with today", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/bdm/me" ? me : p.includes("unread") ? { unread: 0 } : report));
    const tree = elements(await MyReport({ searchParams: Promise.resolve({ date: "2026-10-05" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/daily-reports/2026-10-05");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    expect(tree.find((el) => el.type === BdmDailyReport)!.props.mode).toBe("bdm");
    vi.mocked(serverApi).mockClear();
    await MyReport({ searchParams: Promise.resolve({ date: "2026-02-30" }) });
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/daily-reports/${indiaToday()}`);
  });

  it("the team grid shows each day as a word linking to that report; days before the BDM started are a dash", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/auth/me" ? manager : p.includes("unread") ? { unread: 0 } : grid));
    render(await ManagerReports({ searchParams: Promise.resolve({ date: "2026-10-05" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/manager/daily-reports?date=2026-10-05&limit=50&offset=0");
    const submitted = screen.getByRole("link", { name: /Submitted/ });
    expect(submitted.getAttribute("href")).toBe(`/bdm/manager/daily-reports/${B1}?date=2026-10-05`);
    expect(screen.getAllByRole("link", { name: "Missing" })).toHaveLength(5);
    expect(screen.getByLabelText("Not started").textContent).toBe("—");
    expect(screen.getByText("School BDM")).toBeTruthy();
  });

  it("an empty team says so; a BDM is refused the team pages", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/auth/me" ? manager : p.includes("unread") ? { unread: 0 } : { ...grid, items: [], total: 0 }));
    render(await ManagerReports({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText("No active BDMs report to you yet.")).toBeTruthy();
    cleanup();
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/auth/me" ? { id: B1, full_name: "Asha", role: "bdm" } : { unread: 0 }));
    render(await ManagerReports({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText("This page is for BDM managers.")).toBeTruthy();
    cleanup();
    render(await ManagerReport({ params: Promise.resolve({ bdmId: B1 }), searchParams: Promise.resolve({}) }));
    expect(screen.getByText("This page is for BDM managers.")).toBeTruthy();
  });

  it("a team report is read for that BDM and day in manager mode; a non-UUID id is never sent", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/auth/me" ? manager : p.includes("unread") ? { unread: 0 } : report));
    const tree = elements(await ManagerReport({ params: Promise.resolve({ bdmId: B1 }), searchParams: Promise.resolve({ date: "2026-10-05" }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/manager/daily-reports/${B1}/2026-10-05`);
    expect(tree.find((el) => el.type === BdmDailyReport)!.props.mode).toBe("manager");
    vi.mocked(serverApi).mockClear();
    render(await ManagerReport({ params: Promise.resolve({ bdmId: "../../admin" }), searchParams: Promise.resolve({}) }));
    expect(vi.mocked(serverApi).mock.calls.some(([p]) => String(p).includes("admin"))).toBe(false);
    expect(screen.getByText("BDM not found")).toBeTruthy();
  });
});
