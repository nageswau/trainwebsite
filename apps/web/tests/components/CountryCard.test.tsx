import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import CountryCard from "@/components/CountryCard";
import type { Country } from "@/lib/types";

// nehn-034 (DEC-SCOPE-284 C2-C5): the country card shared by the public destinations page and the student portal.
const country = (overrides: Partial<Country> = {}): Country => ({
  id: "c1", slug: "united-kingdom", name: "United Kingdom", iso2: "GB", overview: "Short, intensive degrees.", tuition: "GBP 15,000-30,000",
  living_expenses: "", visa_process: [], work_opportunities: "", post_study_work: "", pr_opportunities: "", faq: [], university_count: 3, ...overrides,
});

afterEach(cleanup);
describe("CountryCard", () => {
  it("shows the flag, name, description, count and a filtered View universities link", () => {
    const { container } = render(<CountryCard country={country()} />);
    expect(container.querySelector("img")!.getAttribute("src")).toBe("/flags/gb.svg");
    expect(screen.getByRole("heading", { name: "United Kingdom" })).toBeTruthy();
    expect(screen.getByText("Short, intensive degrees.")).toBeTruthy();
    expect(screen.getByText("3 universities")).toBeTruthy();
    const view = screen.getByRole("link", { name: "View universities in United Kingdom" });
    expect(view.getAttribute("href")).toBe("/overseas/universities?country=united-kingdom");
    expect(screen.getByRole("link", { name: "Country guide for United Kingdom" }).getAttribute("href")).toBe("/overseas/countries/united-kingdom");
    expect(screen.queryByRole("link", { name: /Apply/ })).toBeNull();
  });
  it("says 1 university in the singular", () => {
    render(<CountryCard country={country({ university_count: 1 })} />);
    expect(screen.getByText("1 university")).toBeTruthy();
  });
  it("shows Coming soon and no View universities or Apply link when it has no universities", () => {
    render(<CountryCard country={country({ university_count: 0 })} applyHref="/overseas/student/applications" />);
    expect(screen.getByText("Coming soon")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /View universities/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /Apply/ })).toBeNull();
    expect(screen.getByRole("link", { name: "Country guide for United Kingdom" })).toBeTruthy();
  });
  it("falls back to a globe icon without a valid iso2", () => {
    const { container } = render(<CountryCard country={country({ iso2: null })} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".icon-circle")!.textContent).toBe("🌍");
  });
  it("offers Apply with the country preselected in the portal", () => {
    render(<CountryCard country={country()} applyHref="/overseas/student/applications" />);
    expect(screen.getByRole("link", { name: "Apply in United Kingdom" }).getAttribute("href")).toBe("/overseas/student/applications?country=united-kingdom");
  });
  it("encodes the slug in links", () => {
    render(<CountryCard country={country({ slug: "a&b" })} />);
    expect(screen.getByRole("link", { name: /View universities/ }).getAttribute("href")).toBe("/overseas/universities?country=a%26b");
  });
});
