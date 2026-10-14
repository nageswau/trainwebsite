import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import CountryFlag from "@/components/CountryFlag";

afterEach(cleanup);
describe("CountryFlag", () => {
  it("renders a decorative inline flag by default", () => {
    const { container } = render(<CountryFlag iso2="GB" />);
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe("/flags/gb.svg");
    expect(img.getAttribute("alt")).toBe("");
    expect(img.getAttribute("aria-hidden")).toBe("true");
    expect(img.getAttribute("loading")).toBe("lazy");
    expect([img.getAttribute("width"), img.getAttribute("height")]).toEqual(["20", "15"]);
    expect(img.className).toBe("country-flag country-flag--inline");
  });
  it("renders the large size", () => {
    const img = render(<CountryFlag iso2="au" size="large" />).container.querySelector("img")!;
    expect([img.getAttribute("width"), img.getAttribute("height")]).toEqual(["40", "30"]);
  });
  it.each([null, undefined, "", "G1", "GBR", "../x"])("renders nothing for %j", (value) => {
    const { container } = render(<CountryFlag iso2={value as string | null | undefined} />);
    expect(container.innerHTML).toBe("");
  });
});
