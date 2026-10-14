import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import GlobalCounts from "@/components/GlobalCounts";

afterEach(cleanup);
describe("GlobalCounts", () => {
  it("draws a flag before a country row's label when the row has iso2 (PUB-023)", () => {
    const { container } = render(<GlobalCounts caption="Country-wise" rows={[{ key: "GB", label: "United Kingdom", count: 3, href: "/x", iso2: "GB" }]} />);
    expect(container.querySelector('th img.country-flag[src="/flags/gb.svg"]')).not.toBeNull();
    expect(screen.getByRole("link", { name: "United Kingdom" })).toBeTruthy();
  });
  it("leaves rows without iso2 unchanged (other dashboard tables)", () => {
    const { container } = render(<GlobalCounts caption="Stage" rows={[{ key: "s1", label: "Prospect", count: 2 }]} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("rowheader", { name: "Prospect" })).toBeTruthy();
  });
});
