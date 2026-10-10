import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SearchPage from "@/app/partnership/search/page";
import { ApiError, serverApi } from "@/lib/api";
import { PARTNERSHIP_HEAD_NAV, PARTNERSHIP_MENU, PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { filterProblem, type SearchPage as Page, type SearchRow, searchHref, searchQuery, statusCounts } from "@/lib/universitySearch";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/partnership/search" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const SEARCH = "/api/v1/partnership/universities/search";
const head = { id: "h1", full_name: "Hema", role: "partnership_head" };
const admin = { id: "a1", full_name: "Asha", role: "overseas_admin" };
const perms = {
  can_edit: false, can_assign: false, can_publish: false, can_deactivate: false, can_edit_contacts: false, can_manage_documents: false, can_move_stage: false,
  can_reopen: false, can_manage_agreements: false, can_approve_agreements: false, can_edit_timeline: false,
};
const row = (over: Partial<SearchRow> = {}): SearchRow => ({
  id: "u1", university_code: "UNV-000001", slug: "abc", name: "ABC University", institution_type: "university",
  country: { id: "c1", name: "United Kingdom", iso2: "GB", region: "UK", catalogue_visible: true }, city: "London", priority: "A",
  partnership_potential: "high", relationship_strength: null, primary_manager: { id: "m1", full_name: "Rahul", active: true }, backup_manager: null,
  catalogue_visible: false, active: true, stage: "meeting_completed", stage_label: "Meeting Completed", lost: false, permissions: perms,
  ownership_type: "public", partner_status: "in_progress", target_partnership_date: "2027-03-31", ranking: "QS 2026: 145", matching_courses: null, ...over,
});
const facets = { partner_status: { partner: 4, in_progress: 3, target: 2, lost: 1 } };
const page = (over: Partial<Page> = {}): Page => ({ items: [row()], total: 1, limit: 50, offset: 0, facets, ...over });

function answer(user: unknown, result: unknown) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return user as never;
    if (path.startsWith(`${SEARCH}?`)) {
      if (result instanceof Error) throw result;
      return result as never;
    }
    throw new ApiError("unexpected", 500);
  });
}
const searched = () => vi.mocked(serverApi).mock.calls.map(([p]) => p as string).filter((p) => p.startsWith(SEARCH));

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(() => cleanup());

describe("upc-024 query helpers", () => {
  it("passes only the search keys, trimmed, and resets paging when a filter changes", () => {
    const filters = { q: " abc ", region: "UK", offset: "50", junk: "x" } as never;
    expect(searchQuery(filters, 50, 50)).toBe("q=abc&region=UK&limit=50&offset=50");
    expect(searchHref(filters, { partner_status: "in_progress" })).toBe("/partnership/search?q=abc&region=UK&partner_status=in_progress");
    expect(searchHref(filters, { region: "" }, 100)).toBe("/partnership/search?q=abc&offset=100");
    expect(searchHref({})).toBe("/partnership/search");
  });

  it("words the API's cross-field 422s (SR8, SR13)", () => {
    expect(filterProblem({ tuition_min: "100" })).toMatch(/currency/);
    expect(filterProblem({ tuition_min: "200", tuition_max: "100", tuition_currency: "GBP" })).toMatch(/lowest tuition/);
    expect(filterProblem({ expected_from: "2027-05-01", expected_to: "2027-04-01" })).toMatch(/ends before/);
    expect(filterProblem({ tuition_min: "100", tuition_max: "200", tuition_currency: "GBP" })).toBeNull();
  });

  it("counts Not partnered as target + in progress and Any as all four", () => {
    expect(statusCounts(facets)).toEqual([["", 10], ["partner", 4], ["in_progress", 3], ["target", 2], ["not_partnered", 5], ["lost", 1]]);
  });
});

describe("upc-024 Global University Database page", () => {
  it("searches with the URL's filters and lists the results with their partner status, ranking and manager", async () => {
    answer(head, page());
    render(await SearchPage({ searchParams: Promise.resolve({ region: "UK", course: "Business", partner_status: "in_progress" }) }));
    expect(searched()).toEqual([`${SEARCH}?region=UK&course=Business&partner_status=in_progress&limit=50&offset=0`]);
    expect(screen.getByRole("heading", { name: "Global University Database" })).toBeTruthy();
    expect((screen.getByLabelText("Region") as HTMLSelectElement).value).toBe("UK");
    const table = screen.getByRole("table");
    const cells = within(table).getAllByRole("cell").map((c) => c.textContent);
    expect(cells).toEqual(expect.arrayContaining(["ABC University UNV-000001", "United Kingdom London", "QS 2026: 145", "Partnership in progress Meeting Completed", "Rahul", "31 Mar 2027"]));
    expect(within(table).getByRole("link", { name: "ABC University" }).getAttribute("href")).toBe("/partnership/universities/u1");
  });

  it("shows the partner-status chips with counts, the active one marked", async () => {
    answer(head, page());
    render(await SearchPage({ searchParams: Promise.resolve({ partner_status: "in_progress" }) }));
    const chips = within(screen.getByRole("navigation", { name: "Partner status" })).getAllByRole("link");
    expect(chips.map((c) => c.textContent)).toEqual(["Any (10)", "Partner (4)", "Partnership in progress (3)", "Target (2)", "Not partnered (5)", "Lost / closed (1)"]);
    expect(chips[2].getAttribute("aria-current")).toBe("true");
    expect(chips[1].getAttribute("href")).toBe("/partnership/search?partner_status=partner");
  });

  it("offers the commission filter to commission roles only (U2)", async () => {
    answer(head, page());
    render(await SearchPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByLabelText("Commission at least (%)")).toBeTruthy();
    cleanup();
    answer(admin, page());
    render(await SearchPage({ searchParams: Promise.resolve({ commission_min: "15" }) }));
    expect(screen.queryByLabelText("Commission at least (%)")).toBeNull();
  });

  it("adds the matching-courses column only when a course filter is sent", async () => {
    answer(head, page({ items: [row({ matching_courses: 2 })] }));
    render(await SearchPage({ searchParams: Promise.resolve({ level: "PG" }) }));
    expect(screen.getByRole("columnheader", { name: "Matching courses" })).toBeTruthy();
    cleanup();
    answer(head, page());
    render(await SearchPage({ searchParams: Promise.resolve({}) }));
    expect(screen.queryByRole("columnheader", { name: "Matching courses" })).toBeNull();
  });

  it("says what to fix instead of searching when the URL's filters conflict", async () => {
    answer(head, page());
    render(await SearchPage({ searchParams: Promise.resolve({ tuition_min: "100" }) }));
    expect(searched()).toEqual([]);
    expect(screen.getByRole("alert").textContent).toMatch(/currency/);
  });

  it("explains a refused filter value (422) and keeps the form", async () => {
    answer(head, new ApiError("invalid", 422));
    render(await SearchPage({ searchParams: Promise.resolve({ region: "Mars" }) }));
    expect(screen.getByRole("alert").textContent).toMatch(/not valid/);
    expect(screen.getByRole("search", { name: "Search universities" })).toBeTruthy();
  });

  it("has empty, filtered-empty and past-the-end states, and pages with the filters kept", async () => {
    answer(head, page({ items: [], total: 0 }));
    render(await SearchPage({ searchParams: Promise.resolve({ q: "zzz" }) }));
    expect(screen.getByRole("status").textContent).toBe("No universities match these filters.");
    cleanup();
    answer(head, page({ items: [], total: 0 }));
    render(await SearchPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("status").textContent).toBe("No active universities yet.");
    cleanup();
    answer(head, page({ items: [], total: 3, offset: 50 }));
    render(await SearchPage({ searchParams: Promise.resolve({ offset: "50" }) }));
    expect(screen.getByRole("status").textContent).toBe("This page is past the end of the results.");
    cleanup();
    answer(head, page({ total: 120, offset: 50, items: Array.from({ length: 50 }, (_, i) => row({ id: `u${i}` })) }));
    render(await SearchPage({ searchParams: Promise.resolve({ region: "UK", offset: "50" }) }));
    const pager = screen.getByRole("navigation", { name: "Result pages" });
    expect(pager.textContent).toMatch(/Showing 51–100 of 120/);
    expect(within(pager).getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe("/partnership/search?region=UK");
    expect(within(pager).getByRole("link", { name: "Next page" }).getAttribute("href")).toBe("/partnership/search?region=UK&offset=100");
  });

  it("is a live §32 entry for managers and in the head, super admin and overseas admin menus", () => {
    expect(PARTNERSHIP_MENU.find((e) => e.label === "Global University Database")).toMatchObject({ href: "/partnership/search", live: true });
    expect(PARTNERSHIP_HEAD_NAV).toContainEqual({ label: "Global University Database", href: "/partnership/search" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership University Search", href: "/partnership/search" });
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "Global University Database", href: "/partnership/search" });
  });
});
