import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OpportunitiesPage from "@/app/partnership/opportunities/page";
import PerformancePage from "@/app/partnership/performance/page";
import PartnershipFunnel from "@/components/PartnershipFunnel";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { PARTNERSHIP_HEAD_NAV, PARTNERSHIP_MENU, PARTNERSHIP_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { chosenPeriod, istToday, type PerformanceCounts, type PerformancePage as Page, type PerformanceStep, periodLabel, type UniversityPerformance } from "@/lib/partnershipPerformance";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/partnership/performance" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const U1 = "00000000-0000-4000-8000-0000000000u1";
const head = { id: "h1", full_name: "Hema", role: "partnership_head" };
const STEPS: PerformanceStep[] = [
  { key: "leads", label: "Leads", tracked: false }, { key: "counselling", label: "Counselling", tracked: false },
  { key: "interested", label: "Students interested", tracked: true }, { key: "eligible", label: "Profiles eligible", tracked: false },
  { key: "applications", label: "Applications", tracked: true }, { key: "offers", label: "Offers", tracked: true },
  { key: "deposits", label: "Deposits", tracked: true }, { key: "visas", label: "Visa approvals", tracked: true }, { key: "enrolled", label: "Enrolled", tracked: true },
];
const counts = (over: Partial<PerformanceCounts> = {}): PerformanceCounts => ({
  leads: null, counselling: null, eligible: null, interested: 45, applications: 12, offers: 8, deposits: 6, visas: 5, enrolled: 4, ...over,
});
const university = { id: U1, university_code: "UNV-000001", name: "ABC University", country: "United Kingdom", stage: "active_partner", stage_label: "Active Partner", partner: true };
const JUNE = { from: "2024-06-01", to: "2024-06-30" };
const page = (over: Partial<Page> = {}): Page => ({ ...JUNE, steps: STEPS, totals: counts(), items: [{ rank: 1, university, counts: counts() }], total: 1, limit: 25, offset: 0, ...over });
const one = (over: Partial<UniversityPerformance> = {}): UniversityPerformance => ({ ...JUNE, steps: STEPS, university, counts: counts(), ...over });
const message = (node: unknown) => (node as { props: { message?: string } }).props.message;

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

describe("upc-018 period", () => {
  it("defaults to this IST month to date and falls back on a bad URL value with a note", () => {
    expect(chosenPeriod(undefined, undefined, "2026-10-09")).toEqual({ period: { from: "2026-10-01", to: "2026-10-09" }, note: null });
    expect(chosenPeriod("2024-06-01", "2024-06-30", "2026-10-09")).toEqual({ period: JUNE, note: null });
    expect(chosenPeriod("2024-06-01", undefined, "2026-10-09").note).toMatch(/at most 366 days/);
    for (const [from, to] of [["2025-02-30", "2025-03-01"], ["June", "2024-06-30"]]) expect(chosenPeriod(from, to, "2026-10-09").note).toMatch(/valid date/);
    expect(chosenPeriod("2024-06-30", "2024-06-01", "2026-10-09").note).toMatch(/start on or before/);
    expect(chosenPeriod("2024-01-01", "2024-12-31", "2026-10-09").note).toBeNull(); // 366 days (leap year)
  });

  it("reads IST, not UTC, and labels the period", () => {
    expect(istToday(Date.parse("2026-10-08T19:00:00Z"))).toBe("2026-10-09");
    expect(periodLabel(JUNE)).toBe("1 Jun 2024 – 30 Jun 2024");
    expect(periodLabel({ from: "2024-06-01", to: "2024-06-01" })).toBe("1 Jun 2024");
  });
});

describe("upc-018 funnel", () => {
  it("lists the steps in source order and shows the untracked ones as Not tracked", () => {
    render(<PartnershipFunnel steps={STEPS} counts={counts()} label="Student funnel: ABC University" />);
    const list = screen.getByRole("list", { name: "Student funnel: ABC University" });
    const rows = within(list).getAllByRole("listitem").map((li) => li.textContent);
    expect(rows).toHaveLength(9);
    expect(rows[0]).toContain("Leads");
    expect(rows[0]).toContain("Not tracked");
    expect(rows[2]).toContain("Students interested");
    expect(rows[2]).toContain("45");
    expect(rows[8]).toContain("Enrolled");
    expect(rows[8]).toContain("4");
  });

  it("QA18-01: an untracked step reads differently from a count -- muted, and no bar track that suggests a measured zero", () => {
    render(<PartnershipFunnel steps={STEPS} counts={counts()} label="Funnel" />);
    const leads = screen.getByText("Leads").closest("li")!;
    expect(leads.querySelector(".funnel-track")).toBeNull();
    expect(within(leads).getByText("Not tracked")).toHaveClass("funnel-untracked");
    const enrolled = screen.getByText("Enrolled").closest("li")!;
    expect(enrolled.querySelector(".funnel-track")).not.toBeNull();
    expect(within(enrolled).getByText("4")).not.toHaveClass("funnel-untracked");
  });

  it("draws no bar for a zero or untracked step", () => {
    const { container } = render(<PartnershipFunnel steps={STEPS} counts={counts({ interested: 0, applications: 0, offers: 0, deposits: 0, visas: 0, enrolled: 0 })} label="Funnel" />);
    expect(container.querySelectorAll(".funnel-fill")).toHaveLength(0);
  });
});

describe("upc-018 University Performance page", () => {
  it("ranks the head's universities for the period, with a Total row", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/performance": page() });
    const tree = elements(await PerformancePage({ searchParams: Promise.resolve(JUNE) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/performance?from=2024-06-01&to=2024-06-30&limit=25&offset=0");
    expect(tree.find((el) => el.type === PortalShell)!.props.nav).toBe(PARTNERSHIP_HEAD_NAV);
    render(await PerformancePage({ searchParams: Promise.resolve(JUNE) }));
    const row = screen.getByRole("rowheader", { name: /ABC University/ }).closest("tr")!;
    expect(row.textContent).toContain("1");
    expect(row.textContent).toContain("United Kingdom");
    expect(within(row).getByRole("link", { name: "ABC University" })).toHaveAttribute("href", `/partnership/universities/${U1}`);
    expect(screen.getByRole("rowheader", { name: "Total" }).closest("tr")!.textContent).toContain("45");
    expect(screen.getByText(/Leads, Counselling and Profiles eligible are not tracked/)).toBeInTheDocument();
  });

  it("shows the empty state, and pages when there are more rows", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/performance": page({ items: [], total: 0 }) });
    render(await PerformancePage({ searchParams: Promise.resolve(JUNE) }));
    expect(screen.getByText("No student activity for these universities in this period.")).toBeInTheDocument();
    cleanup();
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/performance": page({ total: 26, items: [{ rank: 26, university, counts: counts() }], offset: 25 }) });
    render(await PerformancePage({ searchParams: Promise.resolve({ ...JUNE, offset: "25" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/performance?from=2024-06-01&to=2024-06-30&limit=25&offset=25");
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/partnership/performance?from=2024-06-01&to=2024-06-30&offset=0");
    expect(screen.queryByRole("link", { name: "Next" })).toBeNull();
    expect(screen.getByText("26–26 of 26")).toBeInTheDocument();
    cleanup();
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/performance": page({ total: 26, items: Array.from({ length: 25 }, (_, i) => ({ rank: i + 1, university: { ...university, id: `u${i}` }, counts: counts() })) }) });
    render(await PerformancePage({ searchParams: Promise.resolve(JUNE) }));
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("href", "/partnership/performance?from=2024-06-01&to=2024-06-30&offset=25");
    expect(screen.queryByRole("link", { name: "Previous" })).toBeNull();
  });

  it("upc-019: shows Commission expected / received (F10 / F11) per currency only when the API sent them", async () => {
    const commission = { expected: [{ currency: "GBP", amount: "5400.00" }], received: [] };
    answer({
      "/api/v1/auth/me": head,
      "/api/v1/partnership/performance": page({ items: [{ rank: 1, university, counts: counts(), commission }], commission: { expected: [{ currency: "GBP", amount: "5400.00" }, { currency: "USD", amount: "50.00" }], received: [{ currency: "GBP", amount: "1000.00" }] } }),
    });
    render(await PerformancePage({ searchParams: Promise.resolve(JUNE) }));
    expect(screen.getByRole("columnheader", { name: "Commission expected" })).toBeInTheDocument();
    const row = screen.getByRole("rowheader", { name: /ABC University/ }).closest("tr")!;
    expect(row.textContent).toContain("GBP 5,400.00");
    expect(row.textContent).toContain("—");
    expect(screen.getByRole("rowheader", { name: "Total" }).closest("tr")!.textContent).toContain("GBP 5,400.00 · USD 50.00");
    cleanup();
    answer({ "/api/v1/auth/me": { ...head, role: "overseas_admin" }, "/api/v1/partnership/performance": page() }); // U2: no key, no columns
    render(await PerformancePage({ searchParams: Promise.resolve(JUNE) }));
    expect(screen.queryByRole("columnheader", { name: /Commission/ })).toBeNull();
    expect(screen.getByText(/Leads, Counselling and Profiles eligible/).textContent).not.toMatch(/commission/i);
  });

  it("refuses other roles before calling the API, and reports a bad period", async () => {
    answer({ "/api/v1/auth/me": { ...head, role: "counselor" } });
    expect(message(await PerformancePage({ searchParams: Promise.resolve({}) }))).toBe("University performance access required");
    expect(serverApi).toHaveBeenCalledTimes(1);
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/performance": page() });
    render(await PerformancePage({ searchParams: Promise.resolve({ from: "2024-06-30", to: "2024-06-01" }) }));
    expect(screen.getByText(/must start on or before its end/)).toBeInTheDocument();
  });
});

describe("upc-018 Student Opportunities page", () => {
  it("shows the funnel for every university in scope by default", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/performance": page() });
    render(await OpportunitiesPage({ searchParams: Promise.resolve(JUNE) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/performance?from=2024-06-01&to=2024-06-30&limit=1&offset=0");
    expect(screen.getByRole("list", { name: /Student funnel: all your universities/ })).toBeInTheDocument();
    expect(screen.getByText(/1 university/)).toBeInTheDocument();
  });

  it("narrows to one university", async () => {
    answer({ "/api/v1/auth/me": head, [`/api/v1/partnership/universities/${U1}/performance`]: one() });
    render(await OpportunitiesPage({ searchParams: Promise.resolve({ ...JUNE, university_id: U1 }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/universities/${U1}/performance?from=2024-06-01&to=2024-06-30`);
    expect(screen.getByRole("heading", { name: /ABC University/ })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Student funnel: ABC University" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All universities" })).toHaveAttribute("href", "/partnership/opportunities?from=2024-06-01&to=2024-06-30");
  });

  it("refuses other roles", async () => {
    answer({ "/api/v1/auth/me": { ...head, role: "bdm" } });
    expect(message(await OpportunitiesPage({ searchParams: Promise.resolve({}) }))).toBe("University performance access required");
  });
});

describe("upc-018 menu", () => {
  it("makes Student Opportunities and University Performance live for managers, heads and super admin", () => {
    const live = PARTNERSHIP_MENU.filter((e) => e.item === "upc-018");
    expect(live.map((e) => [e.label, e.href, e.live])).toEqual([["Student Opportunities", "/partnership/opportunities", true], ["University Performance", "/partnership/performance", true]]);
    for (const nav of [PARTNERSHIP_NAV, PARTNERSHIP_HEAD_NAV]) expect(nav.map((n) => n.href)).toEqual(expect.arrayContaining(["/partnership/opportunities", "/partnership/performance"]));
    expect(SUPER_ADMIN_NAV.map((n) => n.href)).toEqual(expect.arrayContaining(["/partnership/opportunities", "/partnership/performance"]));
  });
});
