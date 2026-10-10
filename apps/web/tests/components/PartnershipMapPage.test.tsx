import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MapPage from "@/app/partnership/map/page";
import SearchPage from "@/app/partnership/search/page";
import { ApiError, serverApi } from "@/lib/api";
import { PARTNERSHIP_HEAD_NAV, PARTNERSHIP_NAV, PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { colourOf, countryHref, type MapCountry, mapHref, type MapPage as Page, mapQuery } from "@/lib/partnershipMap";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/partnership/map" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const MAP = "/api/v1/partnership/universities/map";
const head = { id: "h1", full_name: "Hema", role: "partnership_head" };
const country = (iso2: string | null, name: string, partner: number, in_progress: number, target: number, lost: number): MapCountry => ({
  iso2, name, region: "UK", partner, in_progress, target, lost, total: partner + in_progress + target + lost,
});
const UK = country("GB", "United Kingdom", 15, 8, 12, 3); // the source's figures
const countries = [country("DE", "Germany", 8, 5, 20, 0), country("GI", "Gibraltar", 0, 0, 1, 0), country("SG", "Singapore", 0, 0, 0, 2), UK];
const page = (over: Partial<Page> = {}): Page => ({
  countries, totals: { partner: 23, in_progress: 13, target: 33, lost: 5, total: 74 },
  stages: [{ key: "target_university", label: "Target University" }, { key: "agreement_signed", label: "Agreement Signed" }], ...over,
});

function answer(result: unknown) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return head as never;
    if (path.startsWith(`${MAP}?`) || path.startsWith("/api/v1/partnership/universities/search?")) {
      if (result instanceof Error) throw result;
      return result as never;
    }
    throw new ApiError("unexpected", 500);
  });
}
const asked = () => vi.mocked(serverApi).mock.calls.map(([p]) => p as string).filter((p) => p.startsWith(MAP));
const links = (container: HTMLElement) => [...container.querySelectorAll("svg a")] as SVGAElement[];

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(() => cleanup());

describe("upc-025 map helpers", () => {
  it("passes only the map's §2 keys and keeps the view", () => {
    const filters = { region: " UK ", stage: "agreement_signed", q: "junk", view: "table" } as never;
    expect(mapQuery(filters)).toBe("region=UK&stage=agreement_signed");
    expect(mapHref(filters)).toBe("/partnership/map?region=UK&stage=agreement_signed&view=table");
    expect(mapHref(filters, { view: "" })).toBe("/partnership/map?region=UK&stage=agreement_signed");
    expect(mapHref({})).toBe("/partnership/map");
  });

  it("links a country to the search with the same filters and its exact code instead of the country text (MP3, MP4)", () => {
    expect(countryHref({ country: "United", partner_status: "partner", activity: "all", view: "table" }, "GB")).toBe("/partnership/search?partner_status=partner&activity=all&iso2=GB");
  });

  it("colours a country by its best status (Q-32, MP11)", () => {
    expect(colourOf(country("GB", "x", 1, 0, 0, 9))).toBe("partner");
    expect(colourOf(country("GB", "x", 0, 2, 5, 1))).toBe("in_progress");
    expect(colourOf(country("GB", "x", 0, 0, 5, 1))).toBe("target");
    expect(colourOf(country("GB", "x", 0, 0, 0, 1))).toBe("lost");
    expect(colourOf(country("GB", "x", 0, 0, 0, 0))).toBe("none");
  });
});

describe("Global Partnership Map page", () => {
  it("draws each counted country as a named link to its universities, coloured by its best status (AC2)", async () => {
    answer(page());
    const { container } = render(await MapPage({ searchParams: Promise.resolve({ region: "UK" }) }));
    expect(asked()).toEqual([`${MAP}?region=UK`]);
    expect(screen.getByRole("heading", { name: "Global Partnership Map" })).toBeTruthy();
    const drawn = links(container);
    expect(drawn.map((a) => a.getAttribute("aria-label"))).toEqual([
      "Germany: 8 partner, 5 in progress, 20 target, 0 lost", "Singapore: 0 partner, 0 in progress, 0 target, 2 lost",
      "United Kingdom: 15 partner, 8 in progress, 12 target, 3 lost",
    ]);
    const uk = drawn[2];
    expect(uk.getAttribute("href")).toBe("/partnership/search?region=UK&iso2=GB");
    expect(uk.getAttribute("class")).toContain("map-partner");
    expect(drawn[1].getAttribute("class")).toContain("map-lost");
    expect(drawn[1].querySelector("circle")).not.toBeNull(); // MP13: a small country gets a marker
    expect(uk.querySelector("circle")).toBeNull();
    expect(container.querySelectorAll("svg g[aria-hidden='true'] path").length).toBeGreaterThan(200); // the rest are decorative
    expect(screen.getByText(/Not drawn on the map: Gibraltar/)).toBeTruthy();
  });

  it("shows the hovered or focused country's four counts", async () => {
    answer(page());
    const { container } = render(await MapPage({ searchParams: Promise.resolve({}) }));
    const uk = links(container)[2];
    fireEvent.focus(uk.querySelector("path") as Element);
    expect(container.querySelector(".map-panel")?.textContent).toBe("United Kingdom 15 partner 8 in progress 12 target 3 lost / closed");
    fireEvent.blur(uk);
    expect(container.querySelector(".map-panel")?.textContent).toMatch(/tab to a country/);
  });

  it("shows the same countries, counts and totals in the table view (AC3)", async () => {
    answer(page());
    render(await MapPage({ searchParams: Promise.resolve({ view: "table" }) }));
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell").map((c) => c.textContent?.trim()));
    expect(rows[3]).toEqual(["United Kingdom", "UK", "15", "8", "12", "3", "38"]);
    expect(within(table).getByRole("rowheader", { name: "All countries" }).parentElement?.textContent).toContain("2313335");
    expect(within(table).getByRole("link", { name: "United Kingdom" }).getAttribute("href")).toBe("/partnership/search?iso2=GB");
    expect(within(table).getByRole("link", { name: "Gibraltar" }).getAttribute("href")).toBe("/partnership/search?iso2=GI"); // not drawn, still listed
    expect(screen.getByRole("link", { name: "Table" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Map" }).getAttribute("href")).toBe("/partnership/map");
  });

  it("offers the 12 §2 filter groups, the stages from the API, and keeps the URL's values", async () => {
    answer(page());
    render(await MapPage({ searchParams: Promise.resolve({ stage: "agreement_signed", activity: "inactive", exclusivity: "exclusive" }) }));
    const form = screen.getByRole("form", { name: "Map filters" });
    for (const name of ["Country", "Region", "Partner status", "Partnership stage", "University type", "Ranked in top", "Course", "Priority",
      "Partnership manager", "Expected partnership from", "Active / inactive", "Exclusive / non-exclusive"]) {
      expect(within(form).getByLabelText(name)).toBeTruthy();
    }
    expect((within(form).getByLabelText("Partnership stage") as HTMLSelectElement).value).toBe("agreement_signed");
    expect((within(form).getByLabelText("Active / inactive") as HTMLSelectElement).value).toBe("inactive");
    expect((within(form).getByLabelText("Exclusive / non-exclusive") as HTMLSelectElement).value).toBe("exclusive");
  });

  it("has an empty state and explains a refused value (422)", async () => {
    answer(page({ countries: [], totals: { partner: 0, in_progress: 0, target: 0, lost: 0, total: 0 } }));
    render(await MapPage({ searchParams: Promise.resolve({ region: "Asia" }) }));
    expect(screen.getByRole("status").textContent).toBe("No universities match these filters.");
    cleanup();
    answer(new ApiError("invalid", 422));
    render(await MapPage({ searchParams: Promise.resolve({ stage: "nope" }) }));
    expect(document.querySelector(".form-error")?.textContent).toMatch(/not valid/);
    expect(screen.getByRole("form", { name: "Map filters" })).toBeTruthy();
  });

  it("is a live §32 entry for managers and in the head, super admin and overseas admin menus", () => {
    expect(PARTNERSHIP_NAV).toContainEqual({ label: "Global Partnership Map", href: "/partnership/map" });
    expect(PARTNERSHIP_HEAD_NAV).toContainEqual({ label: "Global Partnership Map", href: "/partnership/map" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Partnership Map", href: "/partnership/map" });
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "Partnership Map", href: "/partnership/map" });
  });
});

describe("the search page with the map's filters", () => {
  it("sends iso2 and stage on, shows them as removable, and keeps them in the form", async () => {
    answer({ items: [], total: 0, limit: 50, offset: 0, facets: { partner_status: { partner: 0, in_progress: 0, target: 0, lost: 0 } } });
    render(await SearchPage({ searchParams: Promise.resolve({ iso2: "gb", stage: "agreement_signed", priority: "A", activity: "all" }) }));
    const searched = vi.mocked(serverApi).mock.calls.map(([p]) => p as string).filter((p) => p.includes("/search?"));
    expect(searched).toEqual(["/api/v1/partnership/universities/search?iso2=gb&stage=agreement_signed&priority=A&activity=all&limit=50&offset=0"]);
    expect(screen.getByRole("link", { name: "Remove Country: GB" }).getAttribute("href")).toBe("/partnership/search?stage=agreement_signed&priority=A&activity=all");
    const form = screen.getByRole("search", { name: "Search universities" });
    expect((form.querySelector("input[name=iso2]") as HTMLInputElement).value).toBe("gb");
    expect((within(form).getByLabelText("Priority") as HTMLSelectElement).value).toBe("A");
  });
});
