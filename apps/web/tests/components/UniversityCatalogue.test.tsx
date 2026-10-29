import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import UniversityCatalogue from "@/components/UniversityCatalogue";
import type { University } from "@/lib/types";

// nehn-035 (DEC-SCOPE-331 L7, L8): richer cards (country, city, programs, View details, Apply) and a country filter.
const base = { requirements: [], deadlines: [], scholarships: [], overview: "An overview.", eligibility: "65%" };
const UNIVERSITIES: University[] = [
  { ...base, id: "u1", country_id: "gb", slug: "oxford", name: "Oxford University", city: "Oxford", logo_url: "/api/v1/public/university-logos/abc.png", programs_count: 3, country_name: "United Kingdom", country_slug: "united-kingdom", country_iso2: "GB" },
  { ...base, id: "u2", country_id: "ca", slug: "toronto", name: "Toronto University", city: "Toronto", logo_url: null, programs_count: 1, country_name: "Canada", country_slug: "canada", country_iso2: "CA" },
  { ...base, id: "u3", country_id: "ca", slug: "empty", name: "Empty College", city: "Halifax", logo_url: null, programs_count: 0, country_name: "Canada", country_slug: "canada", country_iso2: null },
];

const card = (name: string) => screen.getByRole("heading", { name }).closest("article") as HTMLElement;

afterEach(cleanup);

describe("UniversityCatalogue cards", () => {
  it("shows logo, country, city, program count, View details and Apply", () => {
    render(<UniversityCatalogue universities={UNIVERSITIES} />);
    const oxford = within(card("Oxford University"));
    expect((oxford.getByRole("img", { name: "Oxford University logo" }) as HTMLImageElement).getAttribute("src")).toBe("/api/v1/public/university-logos/abc.png");
    expect(oxford.getByText("Oxford, United Kingdom")).toBeTruthy();
    expect(oxford.getByText("3 programs")).toBeTruthy();
    expect(oxford.getByRole("link", { name: "View details for Oxford University" }).getAttribute("href")).toBe("/overseas/universities/oxford");
    expect(oxford.getByRole("link", { name: "Apply to Oxford University" }).getAttribute("href")).toBe("/overseas/student/applications?university=oxford");
    expect(card("Oxford University").querySelector("img.country-flag")?.getAttribute("src")).toBe("/flags/gb.svg");
  });

  it("says 1 program in the singular and falls back to the monogram without a logo", () => {
    render(<UniversityCatalogue universities={UNIVERSITIES} />);
    const toronto = within(card("Toronto University"));
    expect(toronto.getByText("1 program")).toBeTruthy();
    expect(toronto.getByRole("img", { name: "Toronto University" }).textContent).toBe("TU");
  });

  it("hides Apply for a university with no programs", () => {
    render(<UniversityCatalogue universities={UNIVERSITIES} />);
    const empty = within(card("Empty College"));
    expect(empty.getByText("Programs coming soon")).toBeTruthy();
    expect(empty.queryByRole("link", { name: /Apply/ })).toBeNull();
    expect(empty.getByRole("link", { name: "View details for Empty College" })).toBeTruthy();
    expect(card("Empty College").querySelector("img.country-flag")).toBeNull();
  });
});

describe("UniversityCatalogue country filter", () => {
  it("filters the cards by country", () => {
    render(<UniversityCatalogue universities={UNIVERSITIES} />);
    const country = screen.getByLabelText("Country") as HTMLSelectElement;
    expect(Array.from(country.options).map((o) => o.textContent)).toEqual(["All countries", "Canada", "United Kingdom"]);
    fireEvent.change(country, { target: { value: "Canada" } });
    expect(screen.queryByRole("heading", { name: "Oxford University" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Toronto University" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Empty College" })).toBeTruthy();
  });
});
