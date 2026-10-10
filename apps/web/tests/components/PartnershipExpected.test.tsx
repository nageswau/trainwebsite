import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ExpectedPartnershipsPage from "@/app/partnership/expected/page";
import TargetsPage from "@/app/partnership/targets/page";
import ExpectedForecastCards from "@/components/ExpectedForecastCards";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { PARTNERSHIP_HEAD_NAV } from "@/lib/navigation";
import { chosenWindow, type ExpectedPage, type ExpectedRow, expectedHref, type ForecastWindow, probabilityText, weightedText } from "@/lib/partnershipExpected";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/partnership/expected" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const head = { id: "h1", full_name: "Hema", role: "partnership_head" };
const WINDOWS: ForecastWindow[] = [
  { key: "this_month", label: "Expected Partnerships This Month", first: "2026-10-01", last: "2026-10-31", count: 10, weighted: 8 },
  { key: "next_month", label: "Expected Next Month", first: "2026-11-01", last: "2026-11-30", count: 3, weighted: 1.4 },
  { key: "this_quarter", label: "Expected This Quarter", first: "2026-10-01", last: "2026-12-31", count: 13, weighted: 9.4 },
];
const row = (over: Partial<ExpectedRow> = {}): ExpectedRow => ({
  university: { id: "u1", university_code: "UNV-000001", name: "ABC University" }, country: "United Kingdom", stage: "commercial_discussion",
  stage_label: "Commercial Discussion", expected_agreement_date: "2026-10-30", owner: { id: "m1", full_name: "Rahul" }, probability: 75,
  stage_probability: 75, override_reason: null, ...over,
});
const page = (over: Partial<ExpectedPage> = {}): ExpectedPage => ({
  today: "2026-10-10", window: "all", windows: WINDOWS, undated_count: 2, total: 1, limit: 25, offset: 0, items: [row()], ...over,
});
const message = (node: unknown) => (node as { props: { message?: string } }).props.message;
const shell = (tree: ReturnType<typeof elements>) => render(<>{tree.find((el) => el.type === PortalShell)!.props.children}</>);

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

describe("upc-023 helpers", () => {
  it("keeps a known window from the URL and falls back to the full dated list", () => {
    expect(chosenWindow("next_month")).toBe("next_month");
    expect(chosenWindow("this_year")).toBe("all");
    expect(chosenWindow(undefined)).toBe("all");
    expect(expectedHref("all")).toBe("/partnership/expected");
    expect(expectedHref("undated", 25)).toBe("/partnership/expected?window=undated&offset=25");
  });

  it("words the weighted forecast and an override (AC1: 10 × 80% = 8)", () => {
    expect(weightedText(8)).toBe("8");
    expect(weightedText(9.4)).toBe("9.4");
    expect(probabilityText(40, 40, false)).toBe("40%");
    expect(probabilityText(70, 40, true)).toBe("70% (override; stage 40%)");
    expect(probabilityText(0, 75, true)).toBe("0% (override; stage 75%)");
  });
});

describe("upc-023 forecast cards", () => {
  it("shows each window's count and weighted forecast, each opening its list", () => {
    render(<ExpectedForecastCards windows={WINDOWS} undatedCount={2} />);
    const tile = screen.getByText("Expected Partnerships This Month").closest("div")!;
    expect(within(tile).getByText("10")).toBeInTheDocument();
    expect(tile.textContent).toContain("Weighted forecast: 8");
    expect(within(tile).getByRole("link", { name: "View expected partnerships this month" })).toHaveAttribute("href", "/partnership/expected?window=this_month");
    expect(screen.getByText(/2 without an expected date are not counted/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "see them" })).toHaveAttribute("href", "/partnership/expected?window=undated");
    expect(screen.getByRole("link", { name: "see them" })).toHaveClass("kpi-link"); // QA23-02: styled as a link, not only by position
  });
});

describe("upc-023 Expected University Partnerships page", () => {
  it("lists the §23 columns for the window in the URL, with the forecast", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/expected": page({ window: "this_month" }) });
    const tree = elements(await ExpectedPartnershipsPage({ searchParams: Promise.resolve({ window: "this_month" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/expected?window=this_month&limit=25&offset=0");
    expect(tree.find((el) => el.type === PortalShell)!.props.nav).toBe(PARTNERSHIP_HEAD_NAV);
    shell(tree);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["University", "Country", "Stage", "Expected date", "Owner", "Probability"]);
    const cells = within(table).getAllByRole("row")[1].textContent!;
    for (const text of ["ABC University", "United Kingdom", "Commercial Discussion", "Rahul", "75%"]) expect(cells).toContain(text);
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "No expected date (2)" })).toHaveAttribute("href", "/partnership/expected?window=undated");
    expect(screen.getByRole("link", { name: "Back to targets" })).toHaveClass("btn"); // QA23-02
  });

  it("marks an override, an overdue date and an unassigned owner", async () => {
    const items = [row({ probability: 90, stage_probability: 40, override_reason: "Board approved", expected_agreement_date: "2026-09-30", owner: null })];
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/expected": page({ items }) });
    shell(elements(await ExpectedPartnershipsPage({ searchParams: Promise.resolve({}) })));
    const cells = within(screen.getByRole("table")).getAllByRole("row")[1];
    expect(cells.textContent).toContain("90% (override; stage 40%)");
    expect(within(cells).getByText("Board approved")).toBeInTheDocument();
    expect(within(cells).getByText("Overdue")).toBeInTheDocument();
    expect(within(cells).getByText("Unassigned")).toBeInTheDocument();
  });

  it("says when a window is empty and when a page is past the end", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/expected": page({ window: "undated", items: [], total: 0 }) });
    shell(elements(await ExpectedPartnershipsPage({ searchParams: Promise.resolve({ window: "undated" }) })));
    expect(screen.getByText("Every university in progress has an expected agreement date.")).toBeInTheDocument();
    cleanup();
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/expected": page({ items: [], total: 3, offset: 50 }) });
    shell(elements(await ExpectedPartnershipsPage({ searchParams: Promise.resolve({ offset: "50" }) })));
    expect(screen.getByRole("link", { name: "Go to the first page" })).toHaveAttribute("href", "/partnership/expected");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("pages through a long window", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/expected": page({ total: 30, offset: 25, items: [row()] }) });
    shell(elements(await ExpectedPartnershipsPage({ searchParams: Promise.resolve({ offset: "25" }) })));
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/partnership/expected");
    expect(screen.getByText("26–26 of 30")).toBeInTheDocument();
  });

  it("another role is refused before the list is asked for", async () => {
    answer({ "/api/v1/auth/me": { id: "o1", full_name: "Omar", role: "overseas_admin" } });
    expect(message(await ExpectedPartnershipsPage({ searchParams: Promise.resolve({}) }))).toBe("Expected partnerships access required");
    expect(serverApi).toHaveBeenCalledTimes(1);
  });
});

describe("upc-023 forecast half of Targets & Forecast", () => {
  const team = { month: "2026-10", month_status: "current", editable: true, kpis: [], managers: [], team: [] };

  it("shows the forecast tiles and a link to the full list", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/targets": team, "/api/v1/partnership/expected": page() });
    shell(elements(await TargetsPage({ searchParams: Promise.resolve({}) })));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/expected?limit=1");
    expect(screen.getByRole("heading", { name: "Partnership forecast" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All expected partnerships" })).toHaveAttribute("href", "/partnership/expected");
  });

  it("keeps the targets when the forecast cannot load", async () => {
    answer({ "/api/v1/auth/me": head, "/api/v1/partnership/targets": team, "/api/v1/partnership/expected": new ApiError("down", 500) });
    shell(elements(await TargetsPage({ searchParams: Promise.resolve({}) })));
    expect(screen.getByText("Unable to load the partnership forecast. Reload the page to try again.")).toBeInTheDocument();
    expect(screen.getByText("No partnership managers report to you yet.")).toBeInTheDocument();
  });
});
